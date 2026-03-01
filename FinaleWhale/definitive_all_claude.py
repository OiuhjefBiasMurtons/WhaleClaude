#!/usr/bin/env python3
"""
Polymarket Definitive All Markets Whale Detector (Robust Version)
Implementación mejorada con manejo de errores, retries, logging y gestión de memoria.
"""

import requests
import json
import time
import signal
import sys
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from whale_scorer import WHALE_TIERS
from sports_edge_detector import SportsEdgeDetector
from supabase import create_client, Client

load_dotenv()

# Configuración de Telegram
TELEGRAM_TOKEN = os.getenv('API_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')
TELEGRAM_ENABLED = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)

# Configuración de Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)

# --- CONFIGURACIÓN ---
GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
LIMIT_TRADES = 1000  # Optimizado: balance entre cobertura y velocidad
INTERVALO_NORMAL = 3 # Segundos
MAX_CACHE_SIZE = 5000 # Limite de mercados en memoria
VENTANA_TIEMPO = 1800  # Segundos (30 minutos) - Captura más trades al reiniciar

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("whale_detector.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class TradeFilter:
    """Filtro de calidad de apuesta para descartar trades no copiables"""
    def __init__(self, session):
        self.session = session
        self.markets_cache = {}

    def is_worth_copying(self, trade, valor) -> tuple:
        price = float(trade.get('price', 0))
        side = trade.get('side', '').upper()

        # Filtro 1: Precio fuera de rango +EV
        if price < 0.15 or price > 0.82:
            return False, "Precio fuera de rango (+EV)"

        # Filtro 2: Volumen del mercado (usar slug del mercado específico, no eventSlug)
        slug = trade.get('slug', '')  # slug específico del mercado (ej: ucl-qar1-new-2026-02-18-spread-away-1pt5)
        cache_key = slug or trade.get('conditionId', trade.get('market', ''))
        if cache_key and cache_key not in self.markets_cache:
            try:
                url = f"{GAMMA_API}/markets"
                if slug:
                    res = self.session.get(url, timeout=10, params={'slug': slug})
                    data = res.json()
                    if isinstance(data, list) and data:
                        self.markets_cache[cache_key] = float(data[0].get('volume', 0))
                    else:
                        self.markets_cache[cache_key] = 0
                else:
                    self.markets_cache[cache_key] = 0
            except Exception as e:
                logger.warning(f"Error obteniendo volumen para {cache_key}: {e}")
                self.markets_cache[cache_key] = 100_000

        market_volume = self.markets_cache.get(cache_key, 100_000)
        if market_volume < 25_000:
            return False, f"Mercado sin liquidez (${market_volume:,.0f})"

        # Filtro 3: Retorno potencial (COMENTADO - permite capturar más trades)
        # potential_return_pct = ((1 / price) - 1) * 100 if price > 0 else 0
        # if potential_return_pct < 40:
        #     return False, "Retorno insuficiente para capital bajo"

        # Filtro 4: Ventas en mercados deportivos (posible farming de liquidez)
        title = trade.get('title', '').lower()
        # Keywords específicos de deportes (sin 'win' que es demasiado genérico)
        sports_kw = ['vs', ' fc', 'nba', 'nfl', 'liga', 'premier', 'serie a',
                      'bundesliga', 'ligue', 'ufc', 'nhl', 'mlb', 'tennis', 'cup',
                      'match', 'game', 'championship', 'tournament']
        is_sports = any(kw in title for kw in sports_kw)
        if is_sports and side == 'SELL':
            return False, "Venta en mercado deportivo (posible farming)"

        # Filtro 5: Orden agresiva vs pasiva (solo deportes)
        if is_sports:
            es_agresiva, movimiento_pct = self._detectar_agresividad(trade, market_volume)
            if not es_agresiva:
                return False, f"Orden pasiva en deporte (farming de liquidez, movimiento {movimiento_pct:.1f}%)"

        return True, "✅ Trade válido"

    def _detectar_agresividad(self, trade: dict, market_volume: float) -> tuple:
        """
        Determina si el trade fue una orden agresiva (tomó liquidez) o pasiva (puso liquidez).

        Retorna: (es_agresiva: bool, precio_movimiento_pct: float)

        Método de detección:
        1. Consultar precio actual del mercado via GAMMA_API
        2. Comparar con precio del trade
        3. Si la diferencia es > 1.5%, fue agresiva (movió el mercado)
        4. Si feeRateBps == 0, es maker (pasiva) — las órdenes agresivas siempre pagan fee
        """
        # Señal 1: feeRateBps
        fee_rate = int(trade.get('feeRateBps', -1))
        if fee_rate == 0:
            return False, 0.0  # Maker order = pasiva

        # Señal 2: diferencia de precio con el mercado actual
        try:
            condition_id = trade.get('conditionId', trade.get('market', ''))
            slug = trade.get('marketSlug', trade.get('slug', ''))

            url = f"{GAMMA_API}/markets?slug={slug}" if slug else f"{GAMMA_API}/markets?id={condition_id}"
            res = self.session.get(url, timeout=8)
            data = res.json()

            if isinstance(data, list) and data:
                market_data = data[0]
            elif isinstance(data, dict):
                market_data = data
            else:
                return True, 0.0  # Sin datos, asumir agresiva (fail-safe)

            # Precio actual del token YES/NO según outcome del trade
            outcome = trade.get('outcome', 'Yes')
            if outcome.lower() == 'yes':
                current_price = float(market_data.get('bestAsk', market_data.get('lastTradePrice', 0)))
            else:
                current_price = 1 - float(market_data.get('bestAsk', market_data.get('lastTradePrice', 0)))

            trade_price = float(trade.get('price', 0))

            if current_price > 0:
                movimiento_pct = abs(trade_price - current_price) / current_price * 100
                es_agresiva = movimiento_pct > 1.5
                return es_agresiva, movimiento_pct

            return True, 0.0  # Sin precio actual, asumir agresiva

        except Exception:
            return True, 0.0  # Fail-safe: si falla, no bloquear


def send_telegram_notification(mensaje):
    """Envía notificación por Telegram"""
    if not TELEGRAM_ENABLED:
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': mensaje,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"Error enviando notificación Telegram: {e}")
        return False


class ConsensusTracker:
    """Rastrea consenso multi-ballena por mercado en ventana de 30 minutos"""
    def __init__(self, window_minutes=30):
        self.window = window_minutes * 60
        self.trades = {}  # market_id -> list of (timestamp, side, value, wallet)

    def add(self, market_id, side, value, wallet=''):
        if market_id not in self.trades:
            self.trades[market_id] = []
        self.trades[market_id].append((time.time(), side, value, wallet))
        self._cleanup(market_id)

    def _cleanup(self, market_id):
        now = time.time()
        self.trades[market_id] = [
            (ts, s, v, w) for ts, s, v, w in self.trades[market_id]
            if now - ts <= self.window
        ]

    def get_signal(self, market_id):
        self._cleanup(market_id)
        entries = self.trades.get(market_id, [])

        side_counts = {}
        side_values = {}
        for _ts, side, value, _w in entries:
            side_counts[side] = side_counts.get(side, 0) + 1
            side_values[side] = side_values.get(side, 0) + value

        best_side = None
        best_count = 0
        for side, count in side_counts.items():
            if count >= 2 and count > best_count:
                best_count = count
                best_side = side

        if best_side:
            return True, best_count, best_side, side_values[best_side]
        return False, 0, '', 0


class CoordinationDetector:
    """
    Detecta ballenas coordinadas operando juntas
    Analiza timing y patrones de grupo
    """
    def __init__(self, coordination_window=300):  # 5 minutos por defecto
        self.coordination_window = coordination_window  # segundos
        self.market_trades = {}  # market_id -> list of (timestamp, wallet, side, value)

    def add_trade(self, market_id, wallet, side, value):
        """Registra un trade de ballena"""
        if market_id not in self.market_trades:
            self.market_trades[market_id] = []

        self.market_trades[market_id].append({
            'timestamp': time.time(),
            'wallet': wallet,
            'side': side,
            'value': value
        })

        # Limpiar trades antiguos (> 1 hora)
        self._cleanup(market_id)

    def _cleanup(self, market_id):
        """Elimina trades con más de 1 hora de antigüedad"""
        now = time.time()
        one_hour = 3600

        self.market_trades[market_id] = [
            t for t in self.market_trades[market_id]
            if now - t['timestamp'] <= one_hour
        ]

    def detect_coordination(self, market_id, current_wallet, current_side):
        """
        Detecta si hay coordinación sospechosa

        Returns:
            tuple: (is_coordinated, count, description, wallets_involved)
        """
        if market_id not in self.market_trades:
            return False, 0, "", []

        trades = self.market_trades[market_id]
        now = time.time()

        # Filtrar trades recientes en ventana de coordinación
        recent_trades = [
            t for t in trades
            if now - t['timestamp'] <= self.coordination_window
            and t['side'] == current_side  # Mismo lado
        ]

        if len(recent_trades) < 3:  # Necesita al menos 3 ballenas (incluyendo la actual)
            return False, 0, "", []

        # Contar wallets únicas
        unique_wallets = set(t['wallet'] for t in recent_trades if t['wallet'])

        # Si hay 3+ wallets diferentes apostando el mismo lado en <5 min
        if len(unique_wallets) >= 3:
            total_value = sum(t['value'] for t in recent_trades)
            time_spread = now - min(t['timestamp'] for t in recent_trades)

            description = f"{len(unique_wallets)} wallets → {current_side} en {time_spread/60:.1f} min"

            return True, len(unique_wallets), description, list(unique_wallets)

        return False, 0, "", []


class AllMarketsWhaleDetector:
    def __init__(self, umbral):
        self.umbral = umbral
        
        # MEJORA DE MEMORIA (Gemini Rec): 
        # Usamos deque con maxlen para auto-limpieza de memoria.
        # Guardamos IDs para búsqueda rápida (O(1)) y Deque para orden (FIFO)
        self.trades_vistos_ids = set()
        self.trades_vistos_deque = deque(maxlen=5000)
        
        self.ballenas_detectadas = 0
        self.ballenas_capturadas = 0  # Ballenas que pasaron el filtro
        self.ballenas_ignoradas = 0   # Ballenas rechazadas por filtro
        self.running = True
        self.markets_cache = {} # Cache de info de mercados
        self.ballenas_por_mercado = {} # Contador de ballenas por mercado
        self.suma_valores_ballenas = 0.0  # Para calcular promedio
        self.ballena_maxima = {'valor': 0, 'mercado': 'N/A', 'wallet': 'N/A'}  # Tracking de ballena más grande
        self.tiempo_inicio = time.time()  # Para uptime
        
        # Configuración de sesión robusta (Claude Rec #2)
        self.session = self._crear_session_con_retry()

        # Filtro de calidad y consenso
        self.trade_filter = TradeFilter(self.session)
        self.consensus = ConsensusTracker(window_minutes=30)
        self.coordination = CoordinationDetector(coordination_window=300)  # 5 minutos

        # Detector de edge deportivo (Polymarket vs Pinnacle)
        odds_api_key = os.getenv("ODDS_API_KEY", "")
        self.sports_edge = SportsEdgeDetector(odds_api_key, self.session)

        # ThreadPool para análisis paralelos (max 2 simultáneos para evitar saturación)
        self.analysis_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="trader_analysis")
        self.scrape_semaphore = threading.Semaphore(1)  # Solo 1 Chrome activo a la vez

        # Cache de análisis de traders para incluir tier en mensaje inicial
        self.analysis_cache = {}

        # Cliente de Supabase para tracking de ballenas deportivas
        self.supabase: Client | None = None
        if SUPABASE_ENABLED and SUPABASE_URL and SUPABASE_KEY:
            try:
                self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                logger.info("✅ Supabase conectado para tracking de ballenas deportivas")
            except Exception as e:
                logger.warning(f"⚠️ Error conectando a Supabase: {e}")

        # Archivos
        trades_live_dir = Path("trades_live")
        trades_live_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename_log = trades_live_dir / f"whales_{timestamp}.txt"
        self.historial_path = trades_live_dir / "historial_trades.json"
        
        # Cargar historial previo
        self._cargar_historial()
        
        # Signals
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        logger.info(f"🚀 Monitor iniciado. Umbral: ${self.umbral:,.2f}")

    def _crear_session_con_retry(self):
        """Crea una sesión HTTP con política de reintentos robusta"""
        session = requests.Session()
        # Backoff factor 1: espera 1s, 2s, 4s...
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _es_ballena(self, valor: float, market_volume: float) -> tuple:
        """
        Umbral dinámico: alerta si cumple CUALQUIERA de estas condiciones:
        1. Valor absoluto >= umbral configurado por el usuario (default 2500)
        2. Valor representa >= 3% del volumen total del mercado

        Returns:
            (es_ballena: bool, mostrar_concentracion: bool, pct_mercado: float)
            - mostrar_concentracion: True si representa ≥3% del mercado (muestra etiqueta NICHO)
        """
        es_ballena_absoluta = valor >= self.umbral
        es_ballena_relativa = (
            market_volume > 0 and
            (valor / market_volume) >= 0.03 and
            valor >= 500  # mínimo absoluto para evitar micro-trades
        )

        pct_mercado = (valor / market_volume * 100) if market_volume > 0 else 0

        # Mostrar etiqueta NICHO si cumple criterio relativo (independiente del absoluto)
        # Si representa ≥3% del mercado, SIEMPRE es información relevante
        mostrar_concentracion = es_ballena_relativa

        return (es_ballena_absoluta or es_ballena_relativa), mostrar_concentracion, pct_mercado

    def _cargar_historial(self):
        """Carga el historial de trades vistos de ejecuciones anteriores"""
        if self.historial_path.exists():
            try:
                with open(self.historial_path, 'r') as f:
                    data = json.load(f)
                    
                    # Verificar antigüedad del historial
                    ultima_act = data.get('ultima_actualizacion')
                    if ultima_act:
                        try:
                            fecha_hist = datetime.fromisoformat(ultima_act)
                            horas_desde_actualizacion = (datetime.now() - fecha_hist).total_seconds() / 3600
                            
                            # Si el historial tiene más de 2 horas, empezar fresco
                            if horas_desde_actualizacion > 2:
                                logger.info(f"🔄 Historial antiguo ({horas_desde_actualizacion:.1f}h). Empezando fresco...")
                                return
                        except:
                            pass
                    
                    # Cargar solo los últimos 5000 para no saturar memoria
                    trades_previos = data.get('trades_vistos', [])
                    self.trades_vistos_ids = set(trades_previos[-5000:])
                    for tid in list(self.trades_vistos_ids):
                        self.trades_vistos_deque.append(tid)
                    logger.info(f"📂 Historial cargado: {len(self.trades_vistos_ids)} trades previos")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo cargar historial: {e}")
    
    def _guardar_historial(self):
        """Guarda el historial de trades para persistencia entre ejecuciones"""
        try:
            with open(self.historial_path, 'w') as f:
                json.dump({
                    'trades_vistos': list(self.trades_vistos_ids),
                    'ultima_actualizacion': datetime.now().isoformat()
                }, f)
            logger.info(f"💾 Historial guardado: {len(self.trades_vistos_ids)} trades")
        except Exception as e:
            logger.error(f"⚠️ Error al guardar historial: {e}")

    def signal_handler(self, sig, frame):
        print("\n\n👋 Deteniendo monitor...")
        self.running = False
        
        # Calcular uptime
        uptime_segundos = int(time.time() - self.tiempo_inicio)
        horas = uptime_segundos // 3600
        minutos = (uptime_segundos % 3600) // 60
        segundos = uptime_segundos % 60
        
        # Guardar historial
        self._guardar_historial()
        
        # Construir resumen de estadísticas
        resumen = f"\n{'='*80}\n"
        resumen += "📊 RESUMEN DE SESIÓN\n"
        resumen += f"{'='*80}\n"
        resumen += f"⏱️  Tiempo de monitoreo:     {horas}h {minutos}m {segundos}s\n"
        resumen += f"🐋 Total de ballenas:       {self.ballenas_detectadas}\n"
        resumen += f"✅ Ballenas capturadas:     {self.ballenas_capturadas}\n"
        resumen += f"⛔ Ballenas ignoradas:      {self.ballenas_ignoradas}\n"

        if self.ballenas_detectadas > 0:
            promedio = self.suma_valores_ballenas / self.ballenas_detectadas
            resumen += f"💰 Valor promedio:          ${promedio:,.2f} USD\n"
            resumen += f"💎 Ballena más grande:      ${self.ballena_maxima['valor']:,.2f} USD\n"
            resumen += f"   └─ Mercado: {self.ballena_maxima['mercado'][:50]}...\n"
            resumen += f"   └─ Wallet: {self.ballena_maxima['wallet'][:20]}...\n"
        
        resumen += f"📊 Mercados monitoreados:   {len(self.markets_cache)}\n"
        resumen += f"\n💾 Archivos guardados:\n"
        resumen += f"   - {self.filename_log} (log formateado)\n"
        resumen += f"   - {self.historial_path} (historial de trades)\n"
        
        # Top 5 mercados con más ballenas
        if self.ballenas_por_mercado:
            resumen += f"\n🏆 TOP 5 MERCADOS CON MÁS BALLENAS:\n"
            top_mercados = sorted(self.ballenas_por_mercado.items(), key=lambda x: x[1], reverse=True)[:5]
            for i, (mercado, count) in enumerate(top_mercados, 1):
                resumen += f"   {i}. {mercado[:60]}... ({count} ballenas)\n"
        
        resumen += f"\n{'='*80}\n"
        
        # Mostrar en consola
        print(resumen)
        
        # Guardar en archivo
        try:
            with open(self.filename_log, "a", encoding="utf-8") as f:
                f.write("\n" + resumen)
        except Exception as e:
            logger.error(f"⚠️ Error al escribir resumen final: {e}")
        
        print("\n¡Hasta luego!")
        sys.exit(0)

    def _limpiar_cache_mercados(self):
        """Evita que la memoria crezca infinitamente (Claude Rec #3)"""
        if len(self.markets_cache) > MAX_CACHE_SIZE:
            logger.info("🧹 Limpiando caché de mercados antigua...")
            # Borrar el 20% más antiguo (simulado convirtiendo a lista, no es LRU puro pero sirve)
            keys_to_remove = list(self.markets_cache.keys())[:int(MAX_CACHE_SIZE * 0.2)]
            for k in keys_to_remove:
                del self.markets_cache[k]

    def _parsear_timestamp(self, ts):
        """Parsea timestamp de forma robusta (Claude Rec #7)"""
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts)
        
        if isinstance(ts, str):
            formatos = [
                '%Y-%m-%dT%H:%M:%S.%fZ', 
                '%Y-%m-%d %H:%M:%S', 
                '%Y-%m-%dT%H:%M:%SZ'
            ]
            ts_clean = ts.replace('Z', '')
            for fmt in formatos:
                try:
                    return datetime.strptime(ts_clean, fmt)
                except ValueError:
                    continue
        
        return datetime.now() # Fallback

    def obtener_trades(self):
        """Obtiene trades con manejo de errores y session (Claude Rec #2)"""
        try:
            url = f"{DATA_API}/trades"
            params = {"limit": LIMIT_TRADES}
            
            # Usamos la sesión con retry automático
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"⚠️ Error de red/API: {e}")
            return []
        except json.JSONDecodeError:
            logger.error("⚠️ Error decodificando JSON de la respuesta")
            return []

    def _registrar_en_supabase(self, trade, valor, price, wallet, display_name, edge_result, es_nicho):
        """Registra ballena en Supabase para tracking automático de resultados"""
        if not self.supabase:
            return

        try:
            # Obtener tier del caché si existe
            cached_analysis = self.analysis_cache.get(wallet, None)
            tier = cached_analysis.get('tier', '') if cached_analysis else None

            # Para mercados no deportivos, edge_pct será 0
            edge_pct = float(edge_result.get('edge_pct', 0)) if edge_result.get('is_sports', False) else 0

            # Preparar datos para inserción
            data = {
                'detected_at': datetime.now().isoformat(),
                'market_title': trade.get('title', ''),
                'condition_id': trade.get('conditionId', trade.get('market', '')),
                'side': trade.get('side', '').upper(),
                'poly_price': float(price),
                'valor_usd': float(valor),
                'display_name': display_name,  # Nombre de usuario en lugar de wallet
                'tier': tier,
                'edge_pct': edge_pct,  # 0 para no deportivos, valor real para deportivos
                'is_nicho': es_nicho,
                'outcome': trade.get('outcome', ''),
                # Campos de resultado se dejan NULL para llenarse después
                'resolved_at': None,
                'result': None,
                'pnl_teorico': None
            }

            # Insertar en Supabase
            self.supabase.table('whale_signals').insert(data).execute()

            market_type = "deportiva" if edge_result.get('is_sports', False) else "general"
            logger.info(f"📊 Ballena {market_type} registrada en Supabase: {data['market_title'][:50]}")

        except Exception as e:
            logger.warning(f"⚠️ Error registrando en Supabase: {e}")

    def _obtener_info_mercado(self, trade):
        """Obtiene información del mercado desde los datos del trade (con caché)"""
        condition_id = trade.get('conditionId', trade.get('market', 'N/A'))
        
        # Check cache
        if condition_id in self.markets_cache:
            return self.markets_cache[condition_id]
        
        # Usar info del trade directamente
        info = {
            'question': trade.get('title', 'N/A'),
            'slug': trade.get('slug', 'N/A'),
            'market_slug': trade.get('eventSlug', trade.get('slug', 'N/A'))
        }
        
        # Guardar en cache
        self.markets_cache[condition_id] = info
        self._limpiar_cache_mercados()
        return info

    def _log_ballena(self, trade, valor, es_nicho=False, pct_mercado=0.0):
        # Trackear estadísticas
        self.suma_valores_ballenas += valor
        if valor > self.ballena_maxima['valor']:
            self.ballena_maxima = {
                'valor': valor,
                'mercado': trade.get('title', 'N/A'),
                'wallet': trade.get('proxyWallet', 'N/A')
            }

        # Determinar categoría
        emoji, categoria = "🦈", "TIBURÓN"
        for tier_val, tier_emoji, tier_cat in WHALE_TIERS:
            if valor >= tier_val:
                emoji, categoria = tier_emoji, tier_cat
                break

        # Filtro de calidad de apuesta
        is_valid, reason = self.trade_filter.is_worth_copying(trade, valor)

        # Obtener volumen del mercado para mostrar (misma key que el filtro)
        slug = trade.get('slug', '')
        cache_key = slug or trade.get('conditionId', trade.get('market', ''))
        market_volume = self.trade_filter.markets_cache.get(cache_key, 0)

        if not is_valid:
            self.ballenas_ignoradas += 1
            hora = datetime.now().strftime('%H:%M:%S')
            print(f"⛔ [{hora}] BALLENA IGNORADA — {categoria} ${valor:,.0f} — Razón: {reason} | Volumen: ${market_volume:,.0f}")
            return

        market_info = self._obtener_info_mercado(trade)
        ts = self._parsear_timestamp(trade.get('timestamp') or trade.get('createdAt'))
        side = trade.get('side', 'N/A').upper()
        price = float(trade.get('price', 0))
        outcome = trade.get('outcome', 'N/A')

        # Análisis de edge deportivo (Polymarket vs Pinnacle)
        edge_result = self.sports_edge.check_edge(
            market_title=trade.get('title', ''),
            poly_price=price,
            side=side
        )

        # Ballena capturada (incluso si es sucker bet, solo advertir)
        self.ballenas_capturadas += 1

        # Contar ballena para este mercado
        mercado_nombre = market_info.get('question', 'Desconocido')
        self.ballenas_por_mercado[mercado_nombre] = self.ballenas_por_mercado.get(mercado_nombre, 0) + 1

        # Información del usuario
        wallet = trade.get('proxyWallet', 'N/A')
        username = trade.get('name', '')
        pseudonym = trade.get('pseudonym', '')
        tx_hash = trade.get('transactionHash', 'N/A')

        # Determinar el nombre a mostrar
        if username and username != '':
            display_name = username
        elif pseudonym and pseudonym != '':
            display_name = pseudonym
        else:
            display_name = 'Anónimo'

        # Consenso multi-ballena
        # NOTA: El registro en Supabase se hará DESPUÉS del análisis, solo si tier es bueno
        condition_id = trade.get('conditionId', trade.get('market', ''))
        self.consensus.add(condition_id, side, valor, wallet)
        is_consensus, count, consensus_side, total_value = self.consensus.get_signal(condition_id)

        # Detección de coordinación (grupos)
        self.coordination.add_trade(condition_id, wallet, side, valor)
        is_coordinated, coord_count, coord_desc, coord_wallets = self.coordination.detect_coordination(
            condition_id, wallet, side
        )

        # URLs
        profile_url = f"https://polymarket.com/profile/{wallet}" if wallet != 'N/A' else 'N/A'
        tx_url = f"https://polygonscan.com/tx/{tx_hash}" if tx_hash != 'N/A' else 'N/A'

        # URL del mercado
        market_slug = market_info.get('market_slug', 'N/A')
        if market_slug != 'N/A':
            market_url = f"https://polymarket.com/event/{market_slug}"
        else:
            market_url = 'N/A'

        # TX Hash truncado
        if tx_hash != 'N/A' and len(tx_hash) > 30:
            tx_hash_display = f"{tx_hash[:20]}...{tx_hash[-10:]}"
        else:
            tx_hash_display = tx_hash

        # Etiqueta de nicho si fue detectada por umbral relativo
        nicho_tag = f"  ⚡ NICHO ({pct_mercado:.1f}% del mercado)" if es_nicho else ""

        msg = f"""
{'='*80}
{emoji} {categoria} DETECTADA {emoji}
{'='*80}
💰 Valor: ${valor:,.2f} USD{nicho_tag}
📊 Mercado: {market_info.get('question', 'N/A')}
🔗 URL: {market_url}
🎯 Outcome: {outcome}
📈 Lado: {'COMPRA' if side == 'BUY' else 'VENTA'}
💵 Precio: {price:.4f} ({price*100:.2f}%)
📦 Volumen: ${market_volume:,.2f}
🕐 Hora: {ts.strftime('%Y-%m-%d %H:%M:%S')}

👤 INFORMACIÓN DEL USUARIO:
   Nombre: {display_name}
   Wallet: {wallet}
   Perfil: {profile_url}
   TX Hash: {tx_hash_display}
   TX URL: {tx_url}
{'='*80}
"""

        # Señal de consenso multi-ballena
        if is_consensus:
            msg += f"🔥 SEÑAL CONSENSO: {count} ballenas → {consensus_side} | Total: ${total_value:,.0f}\n"

        # Alerta de coordinación (grupos)
        if is_coordinated:
            msg += f"⚠️ GRUPO COORDINADO: {coord_desc} | Wallets: {coord_count}\n"

        # Info de edge deportivo
        edge_msg = ""
        if edge_result['is_sports'] and edge_result['pinnacle_price'] > 0:
            pp = edge_result['pinnacle_price']
            ep = edge_result['edge_pct']
            edge_icon = "✅" if ep > 3 else "⚠️" if ep > 0 else "❌"
            edge_msg = f"""📊 ANÁLISIS DE ODDS:
   Pinnacle:     {pp:.2f} ({pp*100:.1f}%)
   Polymarket:   {price:.2f} ({price*100:.1f}%)
   Edge:         {ep:+.1f}% {edge_icon}
"""
            msg += edge_msg

            # Warning adicional si es sucker bet
            if edge_result.get('is_sucker_bet', False):
                msg += f"⚠️⚠️ WARNING: SUCKER BET - Ballena pagando {abs(ep):.1f}% MÁS que Pinnacle\n"

        # Imprimir en consola y guardar en archivo
        print(msg)
        with open(self.filename_log, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

        # Notificación por Telegram
        if TELEGRAM_ENABLED:
            lado_texto = 'COMPRA' if side == 'BUY' else 'VENTA'

            # Alerta de nicho al inicio si aplica
            telegram_msg = ""
            if es_nicho:
                telegram_msg += f"⚡ <b>ALERTA NICHO</b> — Alta concentración en mercado pequeño\n\n"

            telegram_msg += f"<b>{emoji} {categoria} CAPTURADA {emoji}</b>\n\n"

            # Valor con etiqueta de nicho
            nicho_tag_tg = f"  ⚡ <b>NICHO</b> ({pct_mercado:.1f}% del mercado)" if es_nicho else ""
            telegram_msg += f"💰 <b>Valor:</b> ${valor:,.2f}{nicho_tag_tg}\n"
            telegram_msg += f"📊 <b>Mercado:</b> {market_info.get('question', 'N/A')[:80]}\n"
            telegram_msg += f"🎯 <b>Outcome:</b> {outcome}\n"
            telegram_msg += f"📈 <b>Lado:</b> {lado_texto}\n"
            telegram_msg += f"💵 <b>Precio:</b> {price:.4f} ({price*100:.2f}%)\n"
            telegram_msg += f"📦 <b>Volumen:</b> ${market_volume:,.0f}\n"

            # Información del trader con tier si está en caché
            cached_analysis = self.analysis_cache.get(wallet, None)
            if cached_analysis:
                tier = cached_analysis.get('tier', '')
                score = cached_analysis.get('score', 0)
                sports_pnl = cached_analysis.get('sports_pnl', None)

                telegram_msg += f"\n👤 <b>TRADER:</b> {display_name}\n"
                telegram_msg += f"   🏆 <b>Tier:</b> {tier} (Score: {score}/100)\n"

                if sports_pnl is not None:
                    sports_emoji = "🟢" if sports_pnl > 0 else "🔴"
                    telegram_msg += f"   ⚽ <b>PnL Deportes:</b> {sports_emoji} ${sports_pnl:,.0f}\n"

                telegram_msg += f"   🔗 <a href='{profile_url}'>Ver perfil</a>\n"
            else:
                # No mostrar "Analizando perfil..." si el análisis ya está en progreso
                # (evita confusión cuando hay múltiples ballenas del mismo wallet)
                telegram_msg += f"\n👤 <b>TRADER:</b> {display_name}\n"
                telegram_msg += f"   🔗 <a href='{profile_url}'>Ver perfil</a>\n"

            if edge_result['is_sports'] and edge_result['pinnacle_price'] > 0:
                pp = edge_result['pinnacle_price']
                ep = edge_result['edge_pct']
                edge_icon = "✅" if ep > 3 else "⚠️" if ep > 0 else "❌"
                telegram_msg += f"\n📊 <b>Odds Pinnacle:</b> {pp:.2f} ({pp*100:.1f}%)\n"
                telegram_msg += f"📊 <b>Edge:</b> {ep:+.1f}% {edge_icon}\n"

                # Warning si es sucker bet
                if edge_result.get('is_sucker_bet', False):
                    telegram_msg += f"⚠️⚠️ <b>SUCKER BET</b> - Pagando {abs(ep):.1f}% MÁS que Pinnacle\n"

            if is_consensus:
                telegram_msg += f"\n🔥 <b>CONSENSO:</b> {count} ballenas → {consensus_side}\n"

            if is_coordinated:
                telegram_msg += f"⚠️ <b>COORDINACIÓN:</b> {coord_count} wallets en {coord_desc.split('en')[1]}\n"

            telegram_msg += f"\n🔗 <a href='{market_url}'>Ver mercado</a>"

            # Iniciar análisis del trader (espera hasta 20s antes de enviar Telegram)
            # Pasar datos del trade para registro en Supabase solo si tier es bueno
            self._analizar_trader_async(
                wallet, display_name, trade.get('title', '').lower(),
                esperar_resultado=True,
                trade_data=trade,
                valor=valor,
                price=price,
                edge_result=edge_result,
                es_nicho=es_nicho
            )

            # Revisar si el análisis completó y actualizar mensaje si hay tier
            cached_analysis = self.analysis_cache.get(wallet, None)
            if cached_analysis and not 'TRADER:' in telegram_msg:  # Si no se incluyó antes
                tier = cached_analysis.get('tier', '')
                score = cached_analysis.get('score', 0)
                sports_pnl = cached_analysis.get('sports_pnl', None)

                # Insertar info de tier antes del edge/consenso
                trader_info = f"\n👤 <b>TRADER:</b> {display_name}\n"
                trader_info += f"   🏆 <b>Tier:</b> {tier} (Score: {score}/100)\n"
                if sports_pnl is not None:
                    sports_emoji = "🟢" if sports_pnl > 0 else "🔴"
                    trader_info += f"   ⚽ <b>PnL Deportes:</b> {sports_emoji} ${sports_pnl:,.0f}\n"
                trader_info += f"   🔗 <a href='{profile_url}'>Ver perfil</a>\n"

                # Reemplazar la línea de trader simple por la completa
                telegram_msg = telegram_msg.replace(
                    f"\n👤 <b>TRADER:</b> {display_name}\n   🔗 <a href='{profile_url}'>Ver perfil</a>\n",
                    trader_info
                )

            send_telegram_notification(telegram_msg)

    def _analizar_trader_async(self, wallet, display_name, title_lower, esperar_resultado=False,
                               trade_data=None, valor=0.0, price=0.0, edge_result=None, es_nicho=False):
        """
        Ejecuta polywhale_v5 en un hilo paralelo.
        - Si tier es bueno (SILVER/GOLD/DIAMOND/BOT/MM): registra en Supabase + envía análisis completo
        - Si tier es malo (BRONZE/RISKY/STANDARD): envía mensaje simple + NO registra en Supabase

        Args:
            esperar_resultado: Si True, espera hasta 20 segundos a que termine el análisis
            trade_data: Datos del trade para registro en Supabase
            valor: Valor del trade en USD
            price: Precio de la apuesta
            edge_result: Resultado del análisis de edge deportivo
            es_nicho: Si el trade es un mercado nicho
        """
        if wallet == 'N/A':
            return None

        # No analizar la misma wallet dos veces en la misma sesión
        if not hasattr(self, '_wallets_analizadas'):
            self._wallets_analizadas = set()

        if wallet in self._wallets_analizadas:
            return None
        self._wallets_analizadas.add(wallet)

        def _run_analysis():
            try:
                from polywhale_v5_adjusted import TraderAnalyzer

                # Serializar scrapers: solo 1 Chrome activo a la vez (evita conflictos Xvfb)
                with self.scrape_semaphore:
                    analyzer = TraderAnalyzer(wallet)
                    scrape_ok = analyzer.scrape_polymarketanalytics()
                    if not scrape_ok:
                        # Reintentar una vez por si fue un error de red transitorio
                        logger.info(f"⚠️ Scrape fallido para {display_name}, reintentando en 10s...")
                        time.sleep(10)
                        analyzer2 = TraderAnalyzer(wallet)
                        scrape_ok = analyzer2.scrape_polymarketanalytics()
                        if scrape_ok:
                            analyzer = analyzer2
                if not scrape_ok:
                    # Fix: enviar aviso solo si ambos intentos fallaron (caso Wickier)
                    msg_sin_perfil = f"ℹ️ <b>SIN DATOS DE TRADER</b>\n\n"
                    msg_sin_perfil += f"👤 <b>{display_name}</b> (<code>{wallet[:10]}...</code>)\n"
                    msg_sin_perfil += f"📭 No se encontró perfil en PolymarketAnalytics.\n"
                    msg_sin_perfil += f"💡 Trader nuevo o sin historial registrado.\n"
                    msg_sin_perfil += f"🔗 <a href='https://polymarket.com/profile/{wallet}'>Ver perfil</a>"
                    send_telegram_notification(msg_sin_perfil)
                    logger.info(f"⚠️ Sin perfil en analytics para {display_name} ({wallet[:10]}...)")
                    return

                analyzer.calculate_profitability_score()
                analyzer.calculate_consistency_score()
                analyzer.calculate_risk_management_score()
                analyzer.calculate_experience_score()
                analyzer.calculate_final_score()

                tier = analyzer.scores.get('tier', '')
                total = analyzer.scores.get('total', 0)
                d = analyzer.scraped_data

                # Fix: detectar perfil vacío (caso betwick — score 0, trades 0, PnL 0)
                is_empty_profile = (
                    d.get('total_trades', 0) == 0 and
                    abs(d.get('pnl', 0)) == 0 and
                    d.get('win_rate', 0) == 0.0 and
                    total == 0
                )
                if is_empty_profile:
                    msg_vacio = f"⚠️ <b>TRADER SIN HISTORIAL</b>\n\n"
                    msg_vacio += f"👤 <b>{display_name}</b> (<code>{wallet[:10]}...</code>)\n"
                    msg_vacio += f"📊 Perfil encontrado pero sin trades registrados.\n"
                    msg_vacio += f"💡 Trader nuevo — WR histórico no disponible todavía.\n"
                    msg_vacio += f"🔗 <a href='https://polymarket.com/profile/{wallet}'>Ver perfil</a>"
                    msg_vacio += f" | <a href='https://polymarketanalytics.com/traders/{wallet}'>Analytics</a>"
                    send_telegram_notification(msg_vacio)
                    logger.info(f"⚠️ Perfil vacío para {display_name} ({wallet[:10]}...)")
                    return

                # Calcular PnL deportivo total para caché
                sports_pnl = None
                if hasattr(analyzer, '_detect_sport_subtypes'):
                    sport_subtypes = analyzer._detect_sport_subtypes(d)
                    sports_pnl = sum(info['pnl'] for info in sport_subtypes.values()) if sport_subtypes else None

                # Guardar en caché para uso en mensaje inicial de ballena
                self.analysis_cache[wallet] = {
                    'tier': tier,
                    'score': total,
                    'sports_pnl': sports_pnl
                }

                # Solo enviar a Telegram si es silver, gold, diamond o bot/mm
                tiers_buenos = ['SILVER', 'GOLD', 'DIAMOND', 'BRONZE', 'RISKY', 'STANDARD', 'HIGH RISK']
                tiers_advertencia = ['BOT', 'MM']

                es_tier_bueno = any(t in tier.upper() for t in tiers_buenos)
                es_bot_mm = any(t in tier.upper() for t in tiers_advertencia)

                # Si tier es malo, enviar mensaje simple y NO registrar en Supabase
                if not (es_tier_bueno or es_bot_mm):
                    mensaje_simple = f"⚠️ <b>TRADER NO RECOMENDADO</b>\n\n"
                    mensaje_simple += f"👤 <b>{display_name}</b> ({wallet[:10]}...)\n"
                    mensaje_simple += f"📊 <b>Tier:</b> {tier} (Score: {total}/100)\n"
                    mensaje_simple += f"💡 <b>Recomendación:</b> NO copiar este trade\n"
                    send_telegram_notification(mensaje_simple)
                    logger.info(f"🔍 Trader {display_name} ({wallet[:10]}...) → {tier} (score: {total}) — Mensaje simple enviado")
                    return

                # Si tier es bueno, registrar en Supabase (TODOS los mercados)
                if trade_data and edge_result:
                    self._registrar_en_supabase(trade_data, valor, price, wallet, display_name, edge_result, es_nicho)

                logger.info(f"🔍 Trader {display_name} ({wallet[:10]}...) → {tier} (score: {total}) — Enviando análisis completo")

                # Construir mensaje de Telegram
                rec = analyzer.generate_recommendation()

                # Encabezado especial para BOT/MM
                if es_bot_mm and not es_tier_bueno:
                    tg = f"<b>⚠️ ANÁLISIS DE TRADER - BOT/MARKET MAKER</b>\n\n"
                    tg += f"⚠️ <b>ADVERTENCIA:</b> Este trader muestra patrones de bot o market maker\n"
                    tg += f"💡 <b>Recomendación:</b> No copiar - posible farming de liquidez o arbitraje automatizado\n\n"
                else:
                    tg = f"<b>🔍 ANÁLISIS DE TRADER</b>\n\n"

                tg += f"👤 <b>{display_name}</b> | {tier}\n"
                tg += f"📊 <b>Score:</b> {total}/100\n"
                tg += f"📈 <b>PnL:</b> ${d.get('pnl', 0):,.0f}\n"
                tg += f"🎯 <b>Win Rate:</b> {d.get('win_rate', 0):.1f}%\n"
                tg += f"📊 <b>Trades:</b> {d.get('total_trades', 0):,}\n"
                tg += f"🏆 <b>Ranking:</b> #{d.get('rank', 'N/A')}\n"

                # Especialización con detalle
                categories = d.get('categories', [])
                if categories:
                    tg += f"\n<b>🧠 ESPECIALIZACIÓN:</b>\n"
                    # Detectar si el mercado actual matchea una categoría
                    sports_kw = ['win', 'vs', ' fc', 'nba', 'nfl', 'liga', 'premier',
                                 'serie a', 'bundesliga', 'ligue', 'ufc', 'nhl', 'mlb', 'tennis', 'cup']
                    is_current_sports = any(kw in title_lower for kw in sports_kw)

                    for cat in categories[:5]:
                        pnl = cat['pnl']
                        pnl_icon = "🟢" if pnl > 0 else "🔴"
                        pnl_str = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
                        cat_name = cat['name']
                        tg += f"  {pnl_icon} #{cat['rank']} {cat_name}: {pnl_str}\n"

                        # Detectar si es especialista en el mercado actual
                        if is_current_sports and pnl > 0:
                            cat_lower = cat_name.lower()
                            if any(kw in cat_lower for kw in ['sport', 'football', 'soccer', 'basket', 'baseball',
                                                               'hockey', 'tennis', 'mma', 'boxing', 'cricket']):
                                tg += f"  ⭐ <b>ESPECIALISTA en {cat_name} con {pnl_str}</b>\n"

                # Sub-especialización deportiva
                sport_subtypes = analyzer._detect_sport_subtypes(d)
                if sport_subtypes:
                    tg += f"\n<b>⚽ DETALLE DEPORTIVO:</b>\n"
                    for sport, info in sorted(sport_subtypes.items(), key=lambda x: x[1]['pnl'], reverse=True):
                        spnl = info['pnl']
                        icon = "🟢" if spnl > 0 else "🔴"
                        spnl_str = f"+${spnl:,.0f}" if spnl >= 0 else f"-${abs(spnl):,.0f}"
                        tg += f"  {icon} {sport}: {spnl_str} ({info['count']} trades)\n"

                # Biggest wins relevantes
                wins = d.get('biggest_wins', [])
                if wins:
                    tg += f"\n<b>🏆 Top Wins:</b>\n"
                    for w in wins[:3]:
                        tg += f"  +${w['amount']:,.0f} — {w['market'][:40]}\n"

                tg += f"\n💡 <b>{rec[:100]}</b>\n"
                tg += f"\n🔗 <a href='https://polymarket.com/profile/{wallet}'>Ver perfil</a>"
                tg += f" | <a href='https://polymarketanalytics.com/traders/{wallet}'>Analytics</a>"

                send_telegram_notification(tg)

            except Exception as e:
                logger.error(f"❌ Error en análisis de {wallet[:10]}...: {e}", exc_info=True)

        # Usar ThreadPoolExecutor para limitar concurrencia (max 2 análisis simultáneos)
        future = self.analysis_executor.submit(_run_analysis)

        # Si se solicita, esperar hasta 20 segundos a que termine
        if esperar_resultado:
            try:
                future.result(timeout=20)
                logger.info(f"✅ Análisis completado en <20s para {wallet[:10]}...")
            except:
                logger.info(f"⏱️ Análisis tomando >20s para {wallet[:10]}... (continuará en background)")

        return future

    def ejecutar(self):
        # Mostrar resumen de configuración al iniciar
        telegram_status = "✅ ACTIVO" if TELEGRAM_ENABLED else "⛔ DESACTIVADO"
        resumen = f"""\n{'='*80}
🚀 MONITOR INICIADO
{'='*80}
💵 Umbral de ballena:        ${self.umbral:,.2f} USD
⏱️  Intervalo de polling:     {INTERVALO_NORMAL} segundos
📊 Límite de trades/ciclo:   {LIMIT_TRADES}
⏰ Ventana de tiempo:        {VENTANA_TIEMPO//60} minutos (solo trades recientes)
💾 Archivo de log:           {self.filename_log}
📂 Trades en memoria:        {len(self.trades_vistos_ids)}
📱 Notificaciones Telegram:  {telegram_status}
🔄 Esperando trades...
{'='*80}\n"""
        
        print(resumen)
        
        # Escribir resumen también en el archivo de log
        try:
            with open(self.filename_log, "w", encoding="utf-8") as f:
                f.write(resumen + "\n")
        except Exception as e:
            logger.error(f"⚠️ Error al escribir resumen inicial: {e}")
        
        ciclo = 0
        while self.running:
            start_time = time.time()
            ciclo += 1
            
            trades = self.obtener_trades()
            
            nuevos = 0
            ballenas_ciclo = 0
            trades_sobre_umbral = 0
            
            if trades:
                for trade in trades:
                    # Generar ID único usando el id interno de Polymarket
                    # Esto previene duplicados cuando transactionHash llega tarde
                    trade_internal_id = trade.get('id', '')
                    outcome = trade.get('outcome', '')
                    
                    # Fallback a transactionHash solo si no existe id (muy raro)
                    if not trade_internal_id:
                        trade_internal_id = trade.get('transactionHash', str(time.time()))
                    
                    trade_id = f"{trade_internal_id}_{outcome}"
                    
                    # Si ya lo vimos, saltar
                    if trade_id in self.trades_vistos_ids:
                        continue
                    
                    # Filtrar trades antiguos (solo procesar últimos 5 minutos)
                    ts = self._parsear_timestamp(trade.get('timestamp') or trade.get('createdAt'))
                    edad_trade = (datetime.now() - ts).total_seconds()
                    
                    if edad_trade > VENTANA_TIEMPO:
                        # Trade muy antiguo, agregarlo a memoria pero no procesarlo
                        if len(self.trades_vistos_deque) >= self.trades_vistos_deque.maxlen:
                            oldest_id = self.trades_vistos_deque[0]
                            self.trades_vistos_ids.discard(oldest_id)
                        self.trades_vistos_ids.add(trade_id)
                        self.trades_vistos_deque.append(trade_id)
                        continue
                    
                    # Es un trade nuevo y reciente
                    nuevos += 1
                    
                    # Calcular valor
                    try:
                        size = float(trade.get('size', 0))
                        price = float(trade.get('price', 0))
                        valor = size * price
                    except (ValueError, TypeError):
                        continue
                    
                    # Agregar a memoria
                    if len(self.trades_vistos_deque) >= self.trades_vistos_deque.maxlen:
                        oldest_id = self.trades_vistos_deque[0]
                        self.trades_vistos_ids.discard(oldest_id)
                    
                    self.trades_vistos_ids.add(trade_id)
                    self.trades_vistos_deque.append(trade_id)

                    # Obtener volumen del mercado para umbral dinámico (misma key que el filtro)
                    slug = trade.get('slug', '')
                    cache_key = slug or trade.get('conditionId', trade.get('market', ''))
                    market_volume = self.trade_filter.markets_cache.get(cache_key, 0)

                    # Verificar si es ballena (umbral dinámico)
                    es_ballena, es_nicho, pct_mercado = self._es_ballena(valor, market_volume)
                    if es_ballena:
                        trades_sobre_umbral += 1
                        self._log_ballena(trade, valor, es_nicho, pct_mercado)
                        ballenas_ciclo += 1
                        self.ballenas_detectadas += 1
            
            # Logging de información de ciclo cada vez
            hora_actual = datetime.now().strftime("%H:%M:%S")
            print(f"📊 [{hora_actual}] Ciclo #{ciclo} | Trades: {len(trades)} | Nuevos: {nuevos} | Sobre umbral: {trades_sobre_umbral} | Totales: {self.ballenas_detectadas} | Capturadas: {self.ballenas_capturadas} | Ignoradas: {self.ballenas_ignoradas}")
            
            # Auto-guardar historial cada 50 ciclos (2.5 minutos)
            if ciclo % 50 == 0:
                self._guardar_historial()
            
            # Logging de salud periódico (Heartbeat menos frecuente)
            if ciclo % 100 == 0:
                logger.info(f"💓 Heartbeat: {len(self.trades_vistos_ids)} trades en memoria. Cache: {len(self.markets_cache)} | Capturadas: {self.ballenas_capturadas} | Ignoradas: {self.ballenas_ignoradas}")

            # Control de tiempo inteligente
            elapsed = time.time() - start_time
            sleep_time = max(0.5, INTERVALO_NORMAL - elapsed)
            time.sleep(sleep_time)

def main():
    print("\n🐋 POLYMARKET WHALE DETECTOR - DEFINITIVE EDITION")

    while True:
        try:
            val = input("💰 Umbral (USD) [Enter para 2500]: ").strip()
            umbral = float(val) if val else 2500.0
            if umbral > 0: break
        except ValueError:
            print("❌ Número inválido")

    detector = AllMarketsWhaleDetector(umbral)
    detector.ejecutar()

if __name__ == "__main__":
    main()