#!/usr/bin/env python3
"""
Script de validación automática de resultados de ballenas deportivas.
Ejecutar cada hora con cron job para actualizar resultados de trades registrados.
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('whale_validation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
CLOB_API = "https://clob.polymarket.com"

class WhaleResultValidator:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL y SUPABASE_KEY deben estar en .env")

        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.session = requests.Session()
        self.validaciones = 0
        self.actualizaciones = 0
        self.errores = 0

    def obtener_trades_pendientes(self):
        """Obtiene trades que aún no han sido validados"""
        try:
            # Buscar trades sin resolved_at que tengan al menos 1 hora de antigüedad
            hace_1_hora = (datetime.now() - timedelta(hours=1)).isoformat()

            response = self.supabase.table('whale_signals')\
                .select('*')\
                .is_('resolved_at', 'null')\
                .lt('detected_at', hace_1_hora)\
                .execute()

            trades = response.data
            logger.info(f"📊 Encontrados {len(trades)} trades pendientes de validación")
            return trades

        except Exception as e:
            logger.error(f"❌ Error obteniendo trades pendientes: {e}")
            return []

    def consultar_resultado_mercado(self, condition_id):
        """
        Consulta Polymarket CLOB API para obtener el resultado del mercado.

        Returns:
            dict con 'closed', 'winning_outcome' si está resuelto, None si no
        """
        try:
            # Consultar mercado directamente por condition_id usando CLOB API
            url = f"{CLOB_API}/markets/{condition_id}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 404:
                logger.warning(f"⚠️ No se encontró mercado para condition_id: {condition_id[:20]}...")
                return None

            if response.status_code != 200:
                logger.error(f"❌ Error HTTP {response.status_code} para condition_id: {condition_id[:20]}...")
                return None

            market = response.json()

            # Verificar si el mercado está cerrado
            closed = market.get('closed', False)
            if not closed:
                return None  # Aún no se resolvió

            # Obtener outcome ganador usando tokens
            tokens = market.get('tokens', [])
            if not tokens:
                logger.warning(f"⚠️ Mercado sin tokens: {condition_id[:20]}...")
                return None

            # Buscar el token con winner=true
            winning_outcome = None
            for token in tokens:
                if token.get('winner', False):
                    winning_outcome = token.get('outcome')
                    break

            # Si no hay ganador definido, el mercado está cerrado pero no resuelto
            if not winning_outcome:
                logger.info(f"⏳ Mercado cerrado pero aún sin ganador declarado: {condition_id[:20]}...")
                return None

            return {
                'closed': True,
                'winning_outcome': winning_outcome,
                'market_title': market.get('question', 'N/A')
            }

        except Exception as e:
            logger.error(f"❌ Error consultando resultado de {condition_id[:20]}...: {e}")
            return None

    def calcular_resultado(self, trade, winning_outcome):
        """
        Calcula si la ballena ganó o perdió.

        Returns:
            tuple (result, pnl_teorico)
        """
        side = trade['side'].upper()
        whale_outcome = trade['outcome']
        poly_price = float(trade['poly_price'])

        # Normalizar outcomes (YES/Yes/yes → YES, NO/No/no → NO)
        whale_outcome_norm = whale_outcome.upper() if whale_outcome else ''
        winning_outcome_norm = winning_outcome.upper() if winning_outcome else ''

        # Determinar resultado
        if side == 'BUY':
            # Si compró, ganó si su outcome coincide con el ganador
            if whale_outcome_norm == winning_outcome_norm:
                result = 'WIN'
                # PnL teórico con $100 de capital
                pnl_teorico = 100 * (1 / poly_price - 1)
            else:
                result = 'LOSS'
                pnl_teorico = -100.0
        else:  # SELL
            # Si vendió, ganó si su outcome NO coincide con el ganador
            if whale_outcome_norm != winning_outcome_norm:
                result = 'WIN'
                # Al vender (short), si gana se queda con lo que recibió
                pnl_teorico = 100 * poly_price
            else:
                result = 'LOSS'
                # Al vender, si pierde, pierde lo que NO recibió (el complemento)
                pnl_teorico = -(100 - 100 * poly_price)

        return result, pnl_teorico

    def actualizar_trade(self, trade_id, result, pnl_teorico):
        """Actualiza el registro en Supabase con el resultado"""
        try:
            self.supabase.table('whale_signals')\
                .update({
                    'resolved_at': datetime.now().isoformat(),
                    'result': result,
                    'pnl_teorico': pnl_teorico
                })\
                .eq('id', trade_id)\
                .execute()

            self.actualizaciones += 1
            logger.info(f"✅ Trade {trade_id} actualizado: {result} | PnL: ${pnl_teorico:.2f}")

        except Exception as e:
            logger.error(f"❌ Error actualizando trade {trade_id}: {e}")
            self.errores += 1

    def validar_trades(self):
        """Proceso principal de validación"""
        logger.info("="*80)
        logger.info("🔍 INICIANDO VALIDACIÓN DE RESULTADOS")
        logger.info("="*80)

        trades = self.obtener_trades_pendientes()

        for trade in trades:
            self.validaciones += 1

            trade_id = trade['id']
            condition_id = trade['condition_id']
            market_title = trade['market_title']
            display_name = trade.get('display_name', 'Anónimo')

            logger.info(f"🔍 Validando trade #{trade_id}: {market_title[:50]} (Trader: {display_name})")

            # Consultar resultado del mercado
            resultado = self.consultar_resultado_mercado(condition_id)

            if not resultado:
                logger.info(f"⏳ Mercado aún no resuelto")
                continue

            # Calcular resultado
            winning_outcome = resultado['winning_outcome']
            result, pnl_teorico = self.calcular_resultado(trade, winning_outcome)

            logger.info(f"📊 Ganador: {winning_outcome} | Ballena apostó: {trade['outcome']} ({trade['side']})")
            logger.info(f"💰 Resultado: {result} | PnL teórico: ${pnl_teorico:.2f}")

            # Actualizar en Supabase
            self.actualizar_trade(trade_id, result, pnl_teorico)

            # Rate limiting
            time.sleep(0.5)

        # Resumen
        logger.info("="*80)
        logger.info("📊 RESUMEN DE VALIDACIÓN")
        logger.info("="*80)
        logger.info(f"✅ Trades validados:     {self.validaciones}")
        logger.info(f"✅ Trades actualizados:  {self.actualizaciones}")
        logger.info(f"❌ Errores:              {self.errores}")
        logger.info("="*80)

    def generar_estadisticas(self):
        """Genera estadísticas de precisión de ballenas"""
        try:
            # Obtener todos los trades resueltos
            response = self.supabase.table('whale_signals')\
                .select('*')\
                .not_.is_('result', 'null')\
                .execute()

            trades = response.data
            total = len(trades)

            if total == 0:
                logger.info("📊 No hay trades resueltos aún para generar estadísticas")
                return

            wins = sum(1 for t in trades if t['result'] == 'WIN')
            losses = sum(1 for t in trades if t['result'] == 'LOSS')
            win_rate = (wins / total * 100) if total > 0 else 0

            total_pnl = sum(float(t['pnl_teorico'] or 0) for t in trades)
            avg_pnl = total_pnl / total if total > 0 else 0

            logger.info("="*80)
            logger.info("📊 ESTADÍSTICAS GLOBALES")
            logger.info("="*80)
            logger.info(f"📈 Total trades resueltos: {total}")
            logger.info(f"✅ Victorias:              {wins} ({win_rate:.1f}%)")
            logger.info(f"❌ Derrotas:               {losses}")
            logger.info(f"💰 PnL teórico total:      ${total_pnl:.2f}")
            logger.info(f"💰 PnL promedio por trade: ${avg_pnl:.2f}")
            logger.info("="*80)

            # Estadísticas por tier
            logger.info("\n📊 ESTADÍSTICAS POR TIER")
            logger.info("-"*80)

            tiers = set(t['tier'] for t in trades if t['tier'])
            for tier in sorted(tiers):
                tier_trades = [t for t in trades if t['tier'] == tier]
                tier_total = len(tier_trades)
                tier_wins = sum(1 for t in tier_trades if t['result'] == 'WIN')
                tier_win_rate = (tier_wins / tier_total * 100) if tier_total > 0 else 0
                tier_pnl = sum(float(t['pnl_teorico'] or 0) for t in tier_trades)

                logger.info(f"{tier:<20} | Trades: {tier_total:>4} | Win Rate: {tier_win_rate:>5.1f}% | PnL: ${tier_pnl:>8.2f}")

            # Estadísticas por edge
            logger.info("\n📊 ESTADÍSTICAS POR EDGE")
            logger.info("-"*80)

            edge_categories = {
                'Edge Real (>3%)': [t for t in trades if float(t.get('edge_pct', 0)) > 3],
                'Edge Marginal (0-3%)': [t for t in trades if 0 < float(t.get('edge_pct', 0)) <= 3],
                'Sucker Bet (<0%)': [t for t in trades if float(t.get('edge_pct', 0)) < 0]
            }

            for cat_name, cat_trades in edge_categories.items():
                cat_total = len(cat_trades)
                if cat_total == 0:
                    continue
                cat_wins = sum(1 for t in cat_trades if t['result'] == 'WIN')
                cat_win_rate = (cat_wins / cat_total * 100) if cat_total > 0 else 0
                cat_pnl = sum(float(t['pnl_teorico'] or 0) for t in cat_trades)

                logger.info(f"{cat_name:<25} | Trades: {cat_total:>4} | Win Rate: {cat_win_rate:>5.1f}% | PnL: ${cat_pnl:>8.2f}")

            logger.info("="*80)

        except Exception as e:
            logger.error(f"❌ Error generando estadísticas: {e}")


def main():
    try:
        validator = WhaleResultValidator()
        validator.validar_trades()
        validator.generar_estadisticas()

    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
