#!/usr/bin/env python3
"""
resolved_gold.py - Mantenimiento de la tabla whale_signals (Gold).

Dos tareas principales:
  1. Asignar tier a traders que lo tienen vacío → usa polywhale_v5_adjusted
  2. Resolver trades sin resultado → consulta Polymarket CLOB API

Uso:
    python resolved_gold.py               # Ambas tareas
    python resolved_gold.py --solo-tiers  # Solo asignar tiers
    python resolved_gold.py --solo-trades # Solo resolver trades
    python resolved_gold.py --stats       # Mostrar estadísticas y salir
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
        logging.FileHandler('resolved_gold.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv('SUPA_GOLD_URL')
SUPABASE_KEY = os.getenv('SUPA_GOLD_KEY')
CLOB_API     = "https://clob.polymarket.com"
GAMMA_API    = "https://gamma-api.polymarket.com"


class GoldTableResolver:

    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPA_GOLD_URL y SUPA_GOLD_KEY no están definidas en .env")

        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        # Un solo Chrome activo a la vez (igual que gold_all_claude.py)
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
        Corre TraderAnalyzer con el display_name como identificador.
        polymarketanalytics.com acepta tanto wallet address como username slug.
        Devuelve {'tier': str, 'score': int} o None si falla.
        """
        try:
            from polywhale_v5_adjusted import TraderAnalyzer

            with self.scrape_semaphore:
                def _try_scrape(name):
                    a = TraderAnalyzer(name)
                    return a, a.scrape_polymarketanalytics()

                analyzer, ok = _try_scrape(display_name)

                if not ok:
                    logger.info(f"   Reintento 1 para {display_name} (10s)...")
                    time.sleep(10)
                    analyzer, ok = _try_scrape(display_name)

                if not ok:
                    logger.info(f"   Reintento 2 para {display_name} (20s)...")
                    time.sleep(20)
                    analyzer, ok = _try_scrape(display_name)

                if not ok:
                    logger.warning(f"   Scrape fallido tras 3 intentos: {display_name}")
                    return None

                analyzer._enrich_from_api()
                analyzer.calculate_profitability_score()
                analyzer.calculate_consistency_score()
                analyzer.calculate_risk_management_score()
                analyzer.calculate_experience_score()
                analyzer.calculate_final_score()

                tier  = analyzer.scores.get('tier', '')
                score = analyzer.scores.get('total', 0)
                d     = analyzer.scraped_data

                logger.info(
                    f"   Scraped → PnL={d.get('pnl', 'N/A')}  WR={d.get('win_rate', 'N/A')}  "
                    f"Trades={d.get('total_trades', 'N/A')}  Score={score}  Tier={tier or '(vacío)'}"
                )

                if not tier:
                    logger.warning(f"   Tier vacío tras análisis: {display_name}")
                    return None

                return {'tier': tier, 'score': score}

        except Exception as e:
            logger.error(f"   Error analizando {display_name}: {e}", exc_info=True)
            return None

    def asignar_tiers_faltantes(self):
        """Busca traders sin tier, los analiza y actualiza todas sus filas."""
        logger.info("=" * 70)
        logger.info("TAREA 1 — ASIGNAR TIERS FALTANTES")
        logger.info("=" * 70)

        rows = self._obtener_rows_sin_tier()
        if not rows:
            logger.info("No hay traders sin tier. Nada que hacer.")
            return

        # Agrupar IDs por display_name (analizar una vez por trader)
        name_to_ids: dict[str, list] = {}
        for row in rows:
            name = (row.get('display_name') or '').strip()
            if name and name.lower() not in ('anonimo', 'anónimo', ''):
                name_to_ids.setdefault(name, []).append(row['id'])

        logger.info(f"Traders únicos a analizar: {len(name_to_ids)} ({len(rows)} filas en total)")

        for display_name, ids in name_to_ids.items():
            logger.info(f"\n👤 {display_name}  ({len(ids)} fila/s) ...")
            resultado = self._analizar_trader(display_name)

            if resultado:
                tier = resultado['tier']
                for row_id in ids:
                    try:
                        self.supabase.table('whale_signals') \
                            .update({'tier': tier}) \
                            .eq('id', row_id) \
                            .execute()
                    except Exception as e:
                        logger.error(f"   Error actualizando fila {row_id}: {e}")
                        self.stats['errores'] += 1

                logger.info(f"   ✅ Tier asignado: {tier} (score={resultado['score']}) → {len(ids)} fila/s")
                self.stats['tiers_asignados'] += len(ids)
            else:
                logger.warning(f"   ⚠️  No se pudo obtener tier")
                self.stats['tiers_fallidos'] += 1

            time.sleep(2)  # Pausa entre traders

    # =========================================================================
    # TAREA 2: RESOLVER TRADES PENDIENTES
    # =========================================================================

    def _obtener_trades_pendientes(self):
        """Trades sin resolved_at con al menos 1 hora de antigüedad."""
        try:
            hace_1h = (datetime.now() - timedelta(hours=1)).isoformat()
            resp = (
                self.supabase.table('whale_signals')
                .select('*')
                .is_('resolved_at', 'null')
                .lt('detected_at', hace_1h)
                .order('detected_at', desc=False)
                .execute()
            )
            trades = resp.data or []
            logger.info(f"Trades pendientes de resolución: {len(trades)}")
            return trades
        except Exception as e:
            logger.error(f"Error obteniendo trades pendientes: {e}")
            return []

    def _buscar_condition_id(self, trade: dict) -> str | None:
        """
        Obtiene el conditionId del mercado. Orden de prioridad:
          1. condition_id directo del registro (gold_all_claude v5+).
          2. market_slug directo → Gamma API slug lookup (gold_all_claude v5+).
          3. Búsqueda por texto en Gamma API /events?q= (funciona para registros viejos).
        """
        cid = trade.get('condition_id') or ''
        if cid:
            return cid

        # Slug directo del registro (mucho más fiable que slug generado del título)
        market_slug = trade.get('market_slug') or ''
        if market_slug:
            cid = self._gamma_buscar_por_slug(market_slug)
            if cid:
                return cid

        market_title = trade.get('market_title', '')
        if not market_title:
            return None

        return self._gamma_buscar_por_titulo(market_title)

    def _gamma_buscar_por_slug(self, slug: str) -> str | None:
        """Búsqueda directa por slug real (más fiable). Intenta markets y events."""
        for url, params in [
            (f"{GAMMA_API}/markets", {'slug': slug, 'limit': 1}),
            (f"{GAMMA_API}/events",  {'slug': slug, 'limit': 1}),
        ]:
            try:
                resp = self.session.get(url, params=params, timeout=10)
                if resp.status_code != 200:
                    continue
                payload = resp.json()
                items = payload if isinstance(payload, list) else payload.get('data', [])
                for item in items:
                    for market in item.get('markets', [item]):
                        cid = market.get('conditionId') or market.get('condition_id')
                        if cid:
                            logger.info(f"   conditionId via slug directo: {cid[:20]}...")
                            return cid
            except Exception as e:
                logger.debug(f"Error slug directo ({url}): {e}")
        return None

    def _gamma_buscar_por_titulo(self, market_title: str) -> str | None:
        """
        Último recurso para registros sin condition_id ni slug almacenado.
        Gamma API no soporta búsqueda de texto libre (?q= ignora el parámetro),
        por lo que solo intentamos un slug generado automáticamente del título.
        Tasa de éxito baja para títulos antiguos.
        """
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
                logger.debug(f"Error slug generado ({url}): {e}")

        logger.info(f"   Sin conditionId (slug generado no coincidió): {market_title[:50]}")
        return None

    @staticmethod
    def _titulos_coinciden(a: str, b: str) -> bool:
        """Comparación flexible de títulos de mercado."""
        if not a or not b:
            return False
        a, b = a.lower().strip(), b.lower().strip()
        if a == b:
            return True
        # Prefijo de 40 chars
        prefix = min(40, len(a), len(b))
        if a[:prefix] == b[:prefix]:
            return True
        # Containment bidireccional (mínimo 20 chars)
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
                return None  # Aún abierto

            winning_outcome = None
            for token in market.get('tokens', []):
                if token.get('winner', False):
                    winning_outcome = token.get('outcome')
                    break

            if not winning_outcome:
                logger.debug(f"Cerrado pero sin ganador declarado: {condition_id[:20]}...")
                return None

            return {
                'winning_outcome': winning_outcome,
                'market_title':    market.get('question', ''),
            }

        except Exception as e:
            logger.error(f"Error consultando CLOB ({condition_id[:20]}...): {e}")
            return None

    @staticmethod
    def _calcular_resultado(trade: dict, winning_outcome: str) -> tuple[str, float]:
        """
        Devuelve (result, pnl_teorico) basado en el outcome ganador.
        PnL expresado en % sobre base $100.
        """
        side         = trade['side'].upper()
        whale_out    = (trade.get('outcome') or '').upper()
        winner_norm  = (winning_outcome or '').upper()
        poly_price   = float(trade['poly_price'])

        if side == 'BUY':
            if whale_out == winner_norm:
                return 'WIN', 100 * (1 / poly_price - 1)
            return 'LOSS', -100.0
        else:  # SELL
            if whale_out != winner_norm:
                return 'WIN', 100 * poly_price
            return 'LOSS', -(100 - 100 * poly_price)

    def resolver_trades_pendientes(self):
        """Itera trades sin resultado, busca resolución en Polymarket y actualiza."""
        logger.info("=" * 70)
        logger.info("TAREA 2 — RESOLVER TRADES PENDIENTES")
        logger.info("=" * 70)

        trades = self._obtener_trades_pendientes()
        if not trades:
            logger.info("No hay trades pendientes. Nada que hacer.")
            return

        for trade in trades:
            trade_id     = trade['id']
            market_title = trade.get('market_title', 'N/A')
            display_name = trade.get('display_name', 'Anónimo')

            logger.info(f"\n🔍 #{trade_id} | {display_name} | {market_title[:55]}")

            # 1. Obtener condition_id
            condition_id = self._buscar_condition_id(trade)
            if not condition_id:
                logger.info("   ⏭️  Sin conditionId — no se puede consultar Polymarket")
                self.stats['trades_sin_condition_id'] += 1
                time.sleep(0.3)
                continue

            # 2. Consultar resultado
            resultado = self._consultar_resultado_mercado(condition_id)
            if not resultado:
                logger.info("   ⏳ Mercado aún no resuelto")
                self.stats['trades_abiertos'] += 1
                time.sleep(0.3)
                continue

            # 3. Calcular y guardar
            winning_outcome = resultado['winning_outcome']
            result, pnl     = self._calcular_resultado(trade, winning_outcome)

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
                logger.error(f"   Error guardando resultado en Supabase: {e}")
                self.stats['errores'] += 1

            time.sleep(0.5)

    # =========================================================================
    # ESTADÍSTICAS
    # =========================================================================

    def mostrar_estadisticas(self):
        """Muestra estadísticas generales de whale_signals."""
        logger.info("=" * 70)
        logger.info("ESTADÍSTICAS — whale_signals Gold")
        logger.info("=" * 70)
        try:
            resp = self.supabase.table('whale_signals').select('*').execute()
            trades = resp.data or []

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
                tiers = sorted(set(t.get('tier', 'N/A') for t in resueltos))
                for tier in tiers:
                    tt    = [t for t in resueltos if t.get('tier') == tier]
                    tw    = sum(1 for t in tt if t['result'] == 'WIN')
                    twr   = tw / len(tt) * 100 if tt else 0
                    tpnl  = sum(float(t.get('pnl_teorico', 0) or 0) for t in tt)
                    label = (tier or 'Sin tier')[:22]
                    logger.info(f"    {label:<22} N={len(tt):>3}  WR={twr:>5.1f}%  PnL=${tpnl:>8.2f}")

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
        description='Mantenimiento de whale_signals (Gold): tiers + resolución de trades'
    )
    parser.add_argument('--solo-tiers',  action='store_true', help='Solo asignar tiers faltantes')
    parser.add_argument('--solo-trades', action='store_true', help='Solo resolver trades pendientes')
    parser.add_argument('--stats',       action='store_true', help='Mostrar estadísticas y salir')
    args = parser.parse_args()

    try:
        resolver = GoldTableResolver()
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

    # Refrescar tablas dinámicas solo cuando se resolvieron trades (no en --solo-tiers ni --stats)
    if args.solo_trades or run_all:
        try:
            resolver.supabase.rpc('refresh_signal_stats').execute()
            resolver.supabase.rpc('refresh_trader_stats').execute()
            logger.info("Tablas signal_stats y trader_stats actualizadas")
        except Exception as e:
            logger.warning(f"Error al refrescar tablas dinámicas: {e}")

    if run_all:
        resolver.mostrar_estadisticas()


if __name__ == '__main__':
    main()
