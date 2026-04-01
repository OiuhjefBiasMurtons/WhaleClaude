#!/usr/bin/env python3
"""
resolved_definitive.py - Mantenimiento de la tabla whale_signals (Definitive/Whales DB).

Dos tareas principales:
  1. Asignar tier a traders que lo tienen vacío → usa polywhale_v5_adjusted
  2. Resolver trades sin resultado → consulta Polymarket CLOB API

Tras resolver, refresca signal_stats y trader_stats vía RPC.

Uso:
    python resolved_definitive.py               # Ambas tareas
    python resolved_definitive.py --solo-tiers  # Solo asignar tiers
    python resolved_definitive.py --solo-trades # Solo resolver trades
    python resolved_definitive.py --stats       # Mostrar estadísticas y salir
"""

import os
import sys
import re
import time
import logging
import argparse
import threading
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('resolved_definitive.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
CLOB_API     = "https://clob.polymarket.com"
GAMMA_API    = "https://gamma-api.polymarket.com"


class DefinitiveTableResolver:

    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL y SUPABASE_KEY no están definidas en .env")

        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.scrape_semaphore = threading.Semaphore(1)

        self.stats = {
            'tiers_asignados': 0,
            'tiers_fallidos': 0,
            'trades_resueltos': 0,
            'trades_abiertos': 0,
            'trades_sin_condition_id': 0,
            'errores': 0,
        }

    # =========================================================================
    # TAREA 1: ASIGNAR TIERS FALTANTES
    # =========================================================================

    def _obtener_rows_sin_tier(self):
        """Devuelve filas con tier NULL o vacío, ordenadas por más reciente."""
        try:
            r_null = (
                self.supabase.table('whale_signals')
                .select('id, display_name, detected_at')
                .is_('tier', 'null')
                .order('detected_at', desc=True)
                .execute()
            )
            r_empty = (
                self.supabase.table('whale_signals')
                .select('id, display_name, detected_at')
                .eq('tier', '')
                .order('detected_at', desc=True)
                .execute()
            )
            return (r_null.data or []) + (r_empty.data or [])
        except Exception as e:
            logger.error(f"Error consultando traders sin tier: {e}")
            return []

    def _analizar_trader(self, display_name: str) -> dict | None:
        """
        Corre TraderAnalyzer con el display_name.
        Devuelve {'tier': str, 'score': int} o None si falla.
        """
        try:
            from polywhale_v5_adjusted import TraderAnalyzer
            with self.scrape_semaphore:
                analyzer = TraderAnalyzer(display_name)
                ok = analyzer.scrape_polymarketanalytics()
                if not ok:
                    time.sleep(2)
                    analyzer2 = TraderAnalyzer(display_name)
                    ok = analyzer2.scrape_polymarketanalytics()
                    if not ok:
                        return None
                    analyzer = analyzer2

            tier  = analyzer.scores.get('tier', '')
            score = analyzer.scores.get('total', 0)
            if not tier:
                return None
            return {'tier': tier, 'score': score}

        except ImportError:
            logger.warning("polywhale_v5_adjusted no disponible — omitiendo asignación de tiers")
            return None
        except Exception as e:
            logger.warning(f"Error analizando {display_name}: {e}")
            return None

    def asignar_tiers_faltantes(self):
        logger.info("=" * 70)
        logger.info("TAREA 1 — ASIGNAR TIERS FALTANTES")
        logger.info("=" * 70)

        rows = self._obtener_rows_sin_tier()
        logger.info(f"Registros sin tier: {len(rows)}")

        # Deduplicar por display_name (no scrapar el mismo trader dos veces)
        seen: set[str] = set()
        for row in rows:
            name = row.get('display_name', '')
            if not name or name in seen:
                continue
            seen.add(name)

            logger.info(f"\n🔍 Analizando: {name}")
            result = self._analizar_trader(name)

            if not result:
                logger.info(f"   ⚠️  Sin tier obtenido")
                self.stats['tiers_fallidos'] += 1
                time.sleep(1)
                continue

            tier  = result['tier']
            score = result['score']
            logger.info(f"   ✅ Tier: {tier} (Score: {score})")

            try:
                self.supabase.table('whale_signals').update(
                    {'tier': tier}
                ).eq('display_name', name).is_('tier', 'null').execute()

                self.supabase.table('whale_signals').update(
                    {'tier': tier}
                ).eq('display_name', name).eq('tier', '').execute()

                self.stats['tiers_asignados'] += 1
            except Exception as e:
                logger.error(f"   Error guardando tier en Supabase: {e}")
                self.stats['errores'] += 1

            time.sleep(2)

    # =========================================================================
    # TAREA 2: RESOLVER TRADES PENDIENTES
    # =========================================================================

    def _obtener_trades_pendientes(self):
        """Trades sin resultado con más de 1 hora de antigüedad (paginado)."""
        try:
            hace_1h = (datetime.now() - timedelta(hours=1)).isoformat()
            PAGE = 1000
            all_trades: list = []
            offset = 0
            while True:
                resp = (
                    self.supabase.table('whale_signals')
                    .select('*')
                    .is_('resolved_at', 'null')
                    .lt('detected_at', hace_1h)
                    .order('detected_at', desc=False)
                    .range(offset, offset + PAGE - 1)
                    .execute()
                )
                batch = resp.data or []
                all_trades.extend(batch)
                if len(batch) < PAGE:
                    break
                offset += PAGE
            logger.info(f"Trades pendientes de resolución: {len(all_trades)}")
            return all_trades
        except Exception as e:
            logger.error(f"Error obteniendo trades pendientes: {e}")
            return []

    def _buscar_condition_id(self, trade: dict) -> str | None:
        """
        Obtiene el conditionId del mercado. Prioridad:
          1. condition_id directo del registro.
          2. Búsqueda por texto en Gamma API (último recurso).
        """
        cid = trade.get('condition_id') or ''
        if cid:
            return cid

        market_title = trade.get('market_title', '')
        if not market_title:
            return None

        return self._gamma_buscar_por_titulo(market_title)

    def _gamma_buscar_por_titulo(self, market_title: str) -> str | None:
        """Intenta encontrar el conditionId generando un slug desde el título."""
        slug = re.sub(r"[^\w\s-]", "", market_title.lower()).strip()
        slug = re.sub(r"[\s_]+", "-", slug)[:120]

        for url, params in [
            (f"{GAMMA_API}/markets", {'slug': slug, 'limit': 5}),
            (f"{GAMMA_API}/events",  {'slug': slug, 'limit': 5}),
        ]:
            try:
                resp = self.session.get(url, params=params, timeout=10)
                if resp.status_code != 200:
                    continue
                payload = resp.json()
                items = payload if isinstance(payload, list) else payload.get('data', [])
                for item in items:
                    for market in item.get('markets', [item]):
                        q = market.get('question', '')
                        if self._titulos_coinciden(q, market_title):
                            cid = market.get('conditionId') or market.get('condition_id')
                            if cid:
                                logger.info(f"   conditionId via slug generado: {cid[:20]}...")
                                return cid
            except Exception as e:
                logger.debug(f"Error buscando slug ({url}): {e}")

        logger.info(f"   Sin conditionId: {market_title[:50]}")
        return None

    @staticmethod
    def _titulos_coinciden(a: str, b: str) -> bool:
        if not a or not b:
            return False
        a, b = a.lower().strip(), b.lower().strip()
        if a == b:
            return True
        prefix = min(40, len(a), len(b))
        if a[:prefix] == b[:prefix]:
            return True
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if len(shorter) >= 20 and shorter in longer:
            return True
        return False

    def _consultar_resultado_mercado(self, condition_id: str) -> dict | None:
        """Consulta CLOB API. Devuelve dict con winning_outcome si ya resolvió."""
        try:
            resp = self.session.get(f"{CLOB_API}/markets/{condition_id}", timeout=10)

            if resp.status_code == 404:
                logger.debug(f"Mercado no encontrado: {condition_id[:20]}...")
                return None
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} para {condition_id[:20]}...")
                return None

            market = resp.json()
            if not market.get('closed', False):
                return None

            winning_outcome = None
            for token in market.get('tokens', []):
                if token.get('winner', False):
                    winning_outcome = token.get('outcome')
                    break

            if not winning_outcome:
                logger.debug(f"Cerrado pero sin ganador: {condition_id[:20]}...")
                return None

            return {'winning_outcome': winning_outcome}

        except Exception as e:
            logger.error(f"Error consultando CLOB ({condition_id[:20]}...): {e}")
            return None

    @staticmethod
    def _calcular_resultado(trade: dict, winning_outcome: str) -> tuple[str, float]:
        """
        Devuelve (result, pnl_teorico).
        PnL expresado en % sobre base $100.
        """
        side      = trade['side'].upper()
        whale_out = (trade.get('outcome') or '').upper()
        winner    = (winning_outcome or '').upper()
        price     = float(trade['poly_price'])

        if side == 'BUY':
            if whale_out == winner:
                return 'WIN', 100 * (1 / price - 1)
            return 'LOSS', -100.0
        else:  # SELL
            if whale_out != winner:
                return 'WIN', 100 * price
            return 'LOSS', -(100 - 100 * price)

    def resolver_trades_pendientes(self):
        logger.info("=" * 70)
        logger.info("TAREA 2 — RESOLVER TRADES PENDIENTES")
        logger.info("=" * 70)

        trades = self._obtener_trades_pendientes()
        if not trades:
            logger.info("No hay trades pendientes.")
            return

        for trade in trades:
            trade_id     = trade['id']
            market_title = trade.get('market_title', 'N/A')
            display_name = trade.get('display_name', 'Anónimo')

            logger.info(f"\n🔍 #{trade_id} | {display_name} | {market_title[:55]}")

            condition_id = self._buscar_condition_id(trade)
            if not condition_id:
                logger.info("   ⏭️  Sin conditionId — no se puede consultar Polymarket")
                self.stats['trades_sin_condition_id'] += 1
                time.sleep(0.3)
                continue

            resultado = self._consultar_resultado_mercado(condition_id)
            if not resultado:
                logger.info("   ⏳ Mercado aún no resuelto")
                self.stats['trades_abiertos'] += 1
                time.sleep(0.3)
                continue

            winning_outcome = resultado['winning_outcome']
            result, pnl = self._calcular_resultado(trade, winning_outcome)

            try:
                self.supabase.table('whale_signals').update({
                    'resolved_at': datetime.now().isoformat(),
                    'result':      result,
                    'pnl_teorico': round(pnl, 4),
                }).eq('id', trade_id).execute()

                icon = '✅' if result == 'WIN' else '❌'
                logger.info(
                    f"   {icon} {result} | Ganó: {winning_outcome} "
                    f"| Ballena apostó: {trade.get('outcome','')} ({trade['side']}) "
                    f"| PnL: ${pnl:+.2f}"
                )
                self.stats['trades_resueltos'] += 1

            except Exception as e:
                logger.error(f"   Error guardando resultado: {e}")
                self.stats['errores'] += 1

            time.sleep(0.5)

    # =========================================================================
    # ESTADÍSTICAS
    # =========================================================================

    def _fetch_all_signals(self) -> list:
        """Pagina sobre whale_signals para traer todos los registros (sin límite de 1000)."""
        PAGE = 1000
        all_rows: list = []
        offset = 0
        while True:
            resp = (
                self.supabase.table('whale_signals')
                .select('result, tier, valor_usd, pnl_teorico')
                .range(offset, offset + PAGE - 1)
                .execute()
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) < PAGE:
                break
            offset += PAGE
        return all_rows

    def mostrar_estadisticas(self):
        logger.info("=" * 70)
        logger.info("ESTADÍSTICAS — whale_signals Definitive")
        logger.info("=" * 70)
        try:
            trades = self._fetch_all_signals()

            total     = len(trades)
            resueltos = [t for t in trades if t.get('result')]
            abiertos  = [t for t in trades if not t.get('result')]
            sin_tier  = [t for t in trades if not t.get('tier')]
            wins      = [t for t in resueltos if t['result'] == 'WIN']
            losses    = [t for t in resueltos if t['result'] == 'LOSS']
            wr        = (len(wins) / len(resueltos) * 100) if resueltos else 0
            pnl_total = sum(float(t.get('pnl_teorico', 0) or 0) for t in resueltos)

            logger.info(f"  Total registros:    {total}")
            logger.info(f"  Resueltos:          {len(resueltos)}  (Wins={len(wins)}, Losses={len(losses)}, WR={wr:.1f}%)")
            logger.info(f"  Abiertos:           {len(abiertos)}")
            logger.info(f"  Sin tier:           {len(sin_tier)}")
            logger.info(f"  PnL teórico total:  ${pnl_total:+.2f}")

            if resueltos:
                logger.info("\n  Por tier (resueltos):")
                tiers = sorted(set(t.get('tier', 'N/A') or 'N/A' for t in resueltos))
                for tier in tiers:
                    tt   = [t for t in resueltos if (t.get('tier') or 'N/A') == tier]
                    tw   = sum(1 for t in tt if t['result'] == 'WIN')
                    twr  = tw / len(tt) * 100 if tt else 0
                    tpnl = sum(float(t.get('pnl_teorico', 0) or 0) for t in tt)
                    logger.info(f"    {(tier or 'Sin tier'):<22} N={len(tt):>3}  WR={twr:>5.1f}%  PnL=${tpnl:>8.2f}")

                logger.info("\n  Por rango de valor (resueltos):")
                def rango(v):
                    v = float(v or 0)
                    if v >= 20000: return '$20K+'
                    if v >= 5000:  return '$5K-$20K'
                    if v >= 1000:  return '$1K-$5K'
                    return '$500-$1K'

                rangos = ['$500-$1K', '$1K-$5K', '$5K-$20K', '$20K+']
                for r in rangos:
                    rt   = [t for t in resueltos if rango(t.get('valor_usd', 0)) == r]
                    if not rt:
                        continue
                    rw   = sum(1 for t in rt if t['result'] == 'WIN')
                    rwr  = rw / len(rt) * 100
                    rpnl = sum(float(t.get('pnl_teorico', 0) or 0) for t in rt)
                    logger.info(f"    {r:<12} N={len(rt):>3}  WR={rwr:>5.1f}%  PnL=${rpnl:>8.2f}")

        except Exception as e:
            logger.error(f"Error generando estadísticas: {e}")

        logger.info("=" * 70)

    def imprimir_resumen_sesion(self):
        s = self.stats
        logger.info("=" * 70)
        logger.info("RESUMEN DE SESIÓN")
        logger.info("=" * 70)
        logger.info(f"  Tiers asignados:         {s['tiers_asignados']}")
        logger.info(f"  Tiers fallidos:          {s['tiers_fallidos']}")
        logger.info(f"  Trades resueltos hoy:    {s['trades_resueltos']}")
        logger.info(f"  Trades aún abiertos:     {s['trades_abiertos']}")
        logger.info(f"  Sin conditionId:         {s['trades_sin_condition_id']}")
        logger.info(f"  Errores:                 {s['errores']}")
        logger.info("=" * 70)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Mantenimiento de whale_signals (Definitive): tiers + resolución + stats'
    )
    parser.add_argument('--solo-tiers',  action='store_true', help='Solo asignar tiers faltantes')
    parser.add_argument('--solo-trades', action='store_true', help='Solo resolver trades pendientes')
    parser.add_argument('--stats',       action='store_true', help='Mostrar estadísticas y salir')
    args = parser.parse_args()

    try:
        resolver = DefinitiveTableResolver()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    if args.stats:
        resolver.mostrar_estadisticas()
        return

    run_all = not args.solo_tiers and not args.solo_trades

    if args.solo_tiers or run_all:
        resolver.asignar_tiers_faltantes()

    if args.solo_trades or run_all:
        resolver.resolver_trades_pendientes()

    resolver.imprimir_resumen_sesion()

    # Refrescar tablas de stats solo cuando se resolvieron trades
    if args.solo_trades or run_all:
        try:
            resolver.supabase.rpc('refresh_signal_stats').execute()
            resolver.supabase.rpc('refresh_trader_stats').execute()
            logger.info("Tablas signal_stats y trader_stats actualizadas")
        except Exception as e:
            logger.warning(f"Error al refrescar tablas de stats: {e}")

    if run_all:
        resolver.mostrar_estadisticas()


if __name__ == '__main__':
    main()
