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
from datetime import datetime
from pathlib import Path
from collections import deque
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

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

# Niveles de Ballenas Configurables
WHALE_TIERS = [
    (40000, "🐋🐋🐋🐋🐋", "TITAN BALLENA"),
    (20000, "🐋🐋🐋🐋", "ULTRA BALLENA"),
    (10000, "🐋🐋🐋", "MEGA BALLENA"),
    (5000, "🐋🐋", "BALLENA GRANDE"),
    (2000, "🐋", "BALLENA"),
    (0, "🦈", "TIBURÓN")
]

class AllMarketsWhaleDetector:
    def __init__(self, umbral):
        self.umbral = umbral
        
        # MEJORA DE MEMORIA (Gemini Rec): 
        # Usamos deque con maxlen para auto-limpieza de memoria.
        # Guardamos IDs para búsqueda rápida (O(1)) y Deque para orden (FIFO)
        self.trades_vistos_ids = set()
        self.trades_vistos_deque = deque(maxlen=5000)
        
        self.ballenas_detectadas = 0
        self.running = True
        self.markets_cache = {} # Cache de info de mercados
        self.ballenas_por_mercado = {} # Contador de ballenas por mercado
        self.suma_valores_ballenas = 0.0  # Para calcular promedio
        self.ballena_maxima = {'valor': 0, 'mercado': 'N/A', 'wallet': 'N/A'}  # Tracking de ballena más grande
        self.tiempo_inicio = time.time()  # Para uptime
        
        # Configuración de sesión robusta (Claude Rec #2)
        self.session = self._crear_session_con_retry()
        
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

    def _log_ballena(self, trade, valor):
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

        market_info = self._obtener_info_mercado(trade)
        ts = self._parsear_timestamp(trade.get('timestamp') or trade.get('createdAt'))
        side = trade.get('side', 'N/A').upper()
        price = float(trade.get('price', 0))
        outcome = trade.get('outcome', 'N/A')
        
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
        
        msg = f"""
{'='*80}
{emoji} {categoria} DETECTADA {emoji}
{'='*80}
💰 Valor: ${valor:,.2f} USD
📊 Mercado: {market_info.get('question', 'N/A')}
🔗 URL: {market_url}
🎯 Outcome: {outcome}
📈 Lado: {'COMPRA' if side == 'BUY' else 'VENTA'}
💵 Precio: {price:.4f} ({price*100:.2f}%)
🕐 Hora: {ts.strftime('%Y-%m-%d %H:%M:%S')}

👤 INFORMACIÓN DEL USUARIO:
   Nombre: {display_name}
   Wallet: {wallet}
   Perfil: {profile_url}
   TX Hash: {tx_hash_display}
   TX URL: {tx_url}
{'='*80}
"""
        
        # Imprimir en consola y guardar en archivo
        print(msg)
        with open(self.filename_log, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    def ejecutar(self):
        # Mostrar resumen de configuración al iniciar
        resumen = f"""\n{'='*80}
🚀 MONITOR INICIADO
{'='*80}
💵 Umbral de ballena:        ${self.umbral:,.2f} USD
⏱️  Intervalo de polling:     {INTERVALO_NORMAL} segundos
📊 Límite de trades/ciclo:   {LIMIT_TRADES}
⏰ Ventana de tiempo:        {VENTANA_TIEMPO//60} minutos (solo trades recientes)
💾 Archivo de log:           {self.filename_log}
📂 Trades en memoria:        {len(self.trades_vistos_ids)}
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
                    
                    # Verificar si es ballena
                    if valor >= self.umbral:
                        trades_sobre_umbral += 1
                        self._log_ballena(trade, valor)
                        ballenas_ciclo += 1
                        self.ballenas_detectadas += 1
            
            # Logging de información de ciclo cada vez
            hora_actual = datetime.now().strftime("%H:%M:%S")
            print(f"📊 [{hora_actual}] Ciclo #{ciclo} | Trades obtenidos: {len(trades)} | Nuevos: {nuevos} | Sobre umbral: {trades_sobre_umbral} | Ballenas totales: {self.ballenas_detectadas}")
            
            # Auto-guardar historial cada 50 ciclos (2.5 minutos)
            if ciclo % 50 == 0:
                self._guardar_historial()
            
            # Logging de salud periódico (Heartbeat menos frecuente)
            if ciclo % 100 == 0:
                logger.info(f"💓 Heartbeat: {len(self.trades_vistos_ids)} trades en memoria. Cache mercados: {len(self.markets_cache)}")

            # Control de tiempo inteligente
            elapsed = time.time() - start_time
            sleep_time = max(0.5, INTERVALO_NORMAL - elapsed)
            time.sleep(sleep_time)

def main():
    print("\n🐋 POLYMARKET WHALE DETECTOR - DEFINITIVE EDITION")
    
    while True:
        try:
            val = input("💰 Umbral (USD) [Enter para 1000]: ").strip()
            umbral = float(val) if val else 1000.0
            if umbral > 0: break
        except ValueError:
            print("❌ Número inválido")

    detector = AllMarketsWhaleDetector(umbral)
    detector.ejecutar()

if __name__ == "__main__":
    main()