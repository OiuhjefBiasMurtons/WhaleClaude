#!/usr/bin/env python3
"""
🦈 POLYWHALE TRADER SCORE ANALYZER V2.2 - DEFINITIVE FIX
Sistema de análisis con linkeo correcto por marketSlug + debugging extensivo
"""

import requests
import sys
import os
import time
import re
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import math

# --- CONFIGURACIÓN ---
DATA_API = "https://data-api.polymarket.com"
OUTPUT_DIR = "TraderAnalysis"
MAX_ACTIVITY = 10000
DEBUG_MODE = False  # ✅ Desactivado para producción

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504, 429])
session.mount('https://', HTTPAdapter(max_retries=retries))

class TraderAnalyzer:
    def __init__(self, input_str):
        self.original_input = input_str
        self.wallet = self.resolve_input(input_str)
        self.username = None
        self.file_handle = None
        self.positions = []
        self.activity = []
        
        # Métricas comportamentales
        self.metrics = {
            'experience_score': 0,
            'discipline_score': 0,
            'specialization_score': 0,
            'current_performance_score': 0,
            'total_score': 0,
            'tier': 'UNKNOWN'
        }
        
        # PnL tracking
        self.market_pnl = {}  # Ahora dict normal, no defaultdict
        self.market_status = {}
        self.closed_markets = []
        
        # Debug tracking
        self.debug_info = []
        
        self.sectors = defaultdict(float)
        self.market_count = defaultdict(int)
        self.red_flags = []
        self.strengths = []
        
    def resolve_input(self, i):
        clean = i.strip()
        if "profile/" in clean:
            return clean.split("profile/")[-1].split("?")[0].replace("/","")
        if clean.startswith("@"):
            return clean.replace("@","")
        return clean.lower()

    def setup_file_logging(self):
        if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        
        if self.username:
            safe_name = self.username.replace(" ", "_")[:20]
        else:
            safe_name = self.original_input.replace("https://","").replace("/","_").replace("@","")[:20]
        
        self.filename = f"{OUTPUT_DIR}/{safe_name}_{timestamp}.txt"
        try:
            self.file_handle = open(self.filename, "w", encoding="utf-8")
        except: pass

    def report(self, msg, end="\n"):
        print(msg, end=end)
        if self.file_handle:
            self.file_handle.write(msg + end)
            self.file_handle.flush()

    def debug(self, msg):
        """Logging para debugging"""
        if DEBUG_MODE:
            print(f"   🔍 DEBUG: {msg}")
            self.debug_info.append(msg)

    def close_log(self):
        if self.file_handle: 
            self.file_handle.close()
            print(f"\n💾 Análisis guardado en: {self.filename}")

    # --- RECOLECCIÓN DE DATOS ---
    def get_positions(self):
        """Obtiene posiciones usando marketSlug como clave principal"""
        try:
            url = f"{DATA_API}/positions?user={self.wallet}"
            res = session.get(url, timeout=10)
            all_pos = res.json()
            
            self.positions = all_pos
            self.positions.sort(key=lambda x: float(x.get('currentValue', 0)), reverse=True)
            
            self.debug(f"Posiciones obtenidas: {len(self.positions)}")
            
            # Mapear posiciones por slug para debugging
            for p in self.positions:
                slug = p.get('marketSlug', 'NO_SLUG')
                title = p.get('title', 'NO_TITLE')
                current = float(p.get('currentValue', 0))
                size = float(p.get('size', 0))
                
                if current > 0 or size > 0:
                    self.debug(f"Posición: slug={slug[:30]}... | title={title[:40]}... | value=${current:.2f}")
            
            return len(self.positions)
        except Exception as e:
            print(f"⚠️ Error obteniendo posiciones: {e}")
            return 0

    def get_activity(self):
        """Obtiene historial de actividad"""
        print("🔹 Descargando historial de actividad...")
        try:
            offset = 0
            batch_count = 0
            while offset < MAX_ACTIVITY:
                url = f"{DATA_API}/activity"
                params = {"user": self.wallet, "limit": 500, "offset": offset}
                res = session.get(url, params=params, timeout=10)
                data = res.json()
                
                if not data or not isinstance(data, list):
                    break
                
                batch_count += 1
                
                if not self.username and data and len(data) > 0:
                    self.username = data[0].get('name') or data[0].get('pseudonym') or self.wallet[:10]
                    
                self.activity.extend(data)
                print(f"   ⚡ {len(self.activity)} eventos descargados (batch {batch_count})...", end='\r')
                
                if len(data) < 500:
                    break
                offset += 500
                
            self.activity.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            print(f"\n   ✅ {len(self.activity)} eventos procesados ({batch_count} batches)")
            
            # Debug: Mostrar tipos de eventos
            event_types = Counter(a.get('type') for a in self.activity)
            self.debug(f"Tipos de eventos: {dict(event_types)}")
            
            # ✅ NUEVO: Warning si llegamos al límite
            if len(self.activity) >= MAX_ACTIVITY * 0.9:
                print(f"   ⚠️  WARNING: Cerca del límite MAX_ACTIVITY ({MAX_ACTIVITY})")
                print(f"   ⚠️  Puede haber actividad más antigua no capturada")
            
            return len(self.activity)
        except Exception as e:
            print(f"⚠️ Error obteniendo actividad: {e}")
            return 0

    def normalize_title(self, title):
        """
        Normaliza títulos para capturar variaciones:
        - Lowercase
        - Quita puntuación final (?, !, .)
        - Trunca a 60 caracteres para capturar variaciones de longitud
        """
        if not title or title == 'Unknown':
            return 'unknown'
        
        normalized = title.strip().lower()
        # Quitar puntuación final
        normalized = normalized.rstrip('?.!')
        # Truncar a 60 chars (captura mercados cortados)
        normalized = normalized[:60]
        return normalized
    
    def get_market_key(self, item):
        """
        ✅ CLAVE ÚNICA POR POSICIÓN:
        - Usa assetId (ID único de cada token/posición)
        - Fallback a marketSlug + outcomeIndex
        - Último fallback: title normalizado (sin outcome para evitar duplicados)
        """
        # Mejor opción: assetId es único por posición
        asset_id = item.get('assetId') or item.get('asset_id')
        if asset_id:
            return ('asset', asset_id)
        
        # Segunda opción: marketSlug + market
        slug = item.get('marketSlug')
        market = item.get('market', '')  # ID del mercado específico
        if slug and market:
            return ('slug_market', f"{slug}:{market}")
        
        # Tercera opción: solo slug (puede causar duplicados pero mejor que nada)
        if slug:
            return ('slug', slug)
        
        # Fallback: título normalizado SIN outcome
        # (outcome puede cambiar entre eventos, no es confiable para agrupar)
        title = item.get('title', 'Unknown')
        normalized = self.normalize_title(title)
        return ('title', normalized)
    
    def calculate_market_pnl(self):
        """
        ✅ VERSIÓN DEFINITIVA CON FALLBACK: Usa marketSlug O title normalizado
        """
        print("🔹 Calculando PnL con linkeo híbrido + fuzzy matching...")
        
        # Estructura: (tipo, key) -> {invested, returned, title, ...}
        market_flows = {}
        
        # 1. PRIMERO: Mapear posiciones actuales (incluyendo liquidadas)
        position_map = {}
        for p in self.positions:
            key = self.get_market_key(p)
            
            title = p.get('title', 'Unknown')
            current_val = float(p.get('currentValue', 0))
            initial_val = float(p.get('initialValue', 0))
            cash_pnl = float(p.get('cashPnl', 0))
            size = float(p.get('size', 0))
            
            position_map[key] = {
                'title': title,
                'current_value': current_val,
                'initial_value': initial_val,
                'cash_pnl': cash_pnl,
                'size': size
            }
            
            # Inicializar flujos
            if key not in market_flows:
                market_flows[key] = {
                    'invested': 0,
                    'returned': 0,
                    'title': title
                }
            
            key_type, key_val = key
            self.debug(f"Posición: {key_type}={str(key_val)[:40]}... | title={title[:40]}... | ${current_val:.2f}")
        
        # 2. Procesar actividad histórica
        event_count = defaultdict(int)
        for activity in self.activity:
            key = self.get_market_key(activity)
            
            tipo = activity.get('type')
            usdc = float(activity.get('usdcSize', 0))
            title = activity.get('title', 'Unknown')
            
            # Contar eventos por mercado para debug
            event_count[key] += 1
            
            # Inicializar si no existe
            if key not in market_flows:
                market_flows[key] = {
                    'invested': 0,
                    'returned': 0,
                    'title': title
                }
            
            # Actualizar título si es mejor (más largo = más descriptivo)
            if len(title) > len(market_flows[key]['title']):
                market_flows[key]['title'] = title
            
            # Contabilizar flujos
            if tipo == 'TRADE':
                side_action = activity.get('side')
                if side_action == 'BUY':
                    market_flows[key]['invested'] += usdc
                elif side_action == 'SELL':
                    market_flows[key]['returned'] += usdc
            elif tipo == 'REDEEM':
                market_flows[key]['returned'] += usdc
            elif tipo == 'MERGE':
                market_flows[key]['returned'] += usdc
            elif tipo == 'SPLIT':
                market_flows[key]['invested'] += usdc
        
        # Debug: Mostrar mercados con más actividad
        top_markets_activity = sorted(event_count.items(), key=lambda x: x[1], reverse=True)[:5]
        for key, count in top_markets_activity:
            key_type, key_val = key
            self.debug(f"Mercado activo: {key_val[:40]}... | {count} eventos")
        
        # ✅ DEBUG ESPECIAL: Buscar mercados de Eintracht Frankfurt
        eintracht_markets = {k: v for k, v in market_flows.items() if 'eintracht' in v['title'].lower()}
        if eintracht_markets:
            self.debug(f"EINTRACHT MARKETS ENCONTRADOS: {len(eintracht_markets)}")
            for key, data in eintracht_markets.items():
                self.debug(f"  Key: {key}")
                self.debug(f"  Title: {data['title']}")
                self.debug(f"  Invested: ${data['invested']:.2f} | Returned: ${data['returned']:.2f}")
        
        # 3. Calcular PnL por mercado
        # ESTRATEGIA: Procesar posiciones primero, luego actividad residual
        processed_keys = set()
        
        # 3A. Procesar posiciones CON cashPnl (datos más confiables)
        for key, pos in position_map.items():
            if key in market_flows:
                flows = market_flows[key]
                title = flows['title']
                invested = flows['invested']
                returned = flows['returned']
                
                # ✅ Usar cashPnl de la posición (incluye TODO el PnL histórico)
                if pos['size'] > 0:
                    # Posición abierta: cashPnl realizado + valor actual no realizado
                    pnl = pos['cash_pnl'] + pos['current_value']
                    self.debug(f"{title[:50]}: OPEN | cashPnl=${pos['cash_pnl']:.2f} + current=${pos['current_value']:.2f} = ${pnl:.2f}")
                    self.market_status[title] = 'OPEN'
                else:
                    # Posición cerrada/liquidada (size=0)
                    pnl = pos['cash_pnl'] if pos['cash_pnl'] != 0 else (returned - invested)
                    self.debug(f"{title[:50]}: CLOSED/LIQUIDATED | cashPnl=${pos['cash_pnl']:.2f}")
                    self.market_status[title] = 'CLOSED'
                
                self.market_pnl[title] = pnl
                processed_keys.add(key)
                
                # ✅ DETECTAR FLUJOS RESIDUALES (más actividad de la que explica esta posición)
                # Si invested > initialValue, hay OTRA posición cerrada no reportada
                expected_investment = pos['initial_value'] if pos['initial_value'] > 0 else invested
                residual_invested = invested - expected_investment
                residual_returned = returned - pos['cash_pnl'] if pos['cash_pnl'] < 0 else returned
                
                if residual_invested > 100:  # Hay inversión significativa no explicada
                    residual_pnl = residual_returned - residual_invested
                    # Marcar como posición cerrada adicional
                    residual_title = f"{title} [cerrada]"
                    self.debug(f"{residual_title[:50]}: RESIDUAL | invested=${residual_invested:.2f} - returned=${residual_returned:.2f} = ${residual_pnl:.2f}")
                    self.market_pnl[residual_title] = residual_pnl
                    self.market_status[residual_title] = 'CLOSED'
        
        # 3B. Procesar mercados SOLO en actividad (no en positions)
        for key, flows in market_flows.items():
            if key in processed_keys:
                continue
                
            title = flows['title']
            invested = flows['invested']
            returned = flows['returned']
            pnl = returned - invested
            
            if returned == 0 and invested > 0:
                self.debug(f"{title[:50]}: LOST (activity only) | invested=${invested:.2f} with no returns = ${pnl:.2f}")
            elif abs(pnl) > 100:
                self.debug(f"{title[:50]}: CLOSED (activity only) | returned=${returned:.2f} - invested=${invested:.2f} = ${pnl:.2f}")
            
            self.market_status[title] = 'CLOSED'
            self.market_pnl[title] = pnl
        
        # 4. CASO ESPECIAL: Posiciones sin historial O liquidadas sin actividad visible
        for key, pos in position_map.items():
            title = pos['title']
            
            # Si no está en market_flows, agregar
            if key not in market_flows:
                # ✅ Posición liquidada sin historial de actividad
                if pos['size'] == 0 and pos['current_value'] == 0 and pos['initial_value'] > 0:
                    pnl = pos['cash_pnl'] if pos['cash_pnl'] != 0 else -pos['initial_value']
                    self.market_pnl[title] = pnl
                    self.market_status[title] = 'CLOSED'
                    self.debug(f"{title[:50]}: Liquidada sin historial | PnL=${pnl:.2f}")
                # Posición abierta sin historial
                elif pos['cash_pnl'] != 0 or pos['current_value'] > 0:
                    pnl = pos['cash_pnl'] + pos['current_value']
                    self.market_pnl[title] = pnl
                    self.market_status[title] = 'OPEN'
                    self.debug(f"{title[:50]}: Sin historial | cashPnl=${pos['cash_pnl']:.2f}")
        
        self.closed_markets.sort(key=lambda x: x['pnl'], reverse=True)
        
        total_markets = len(self.market_pnl)
        closed_count = len([s for s in self.market_status.values() if s == 'CLOSED'])
        open_count = len([s for s in self.market_status.values() if s == 'OPEN'])
        
        print(f"   ✅ {total_markets} mercados totales analizados")
        print(f"   ✅ {closed_count} mercados cerrados | {open_count} posiciones abiertas")
        
        # Debug: Verificación de totales
        total_pnl = sum(self.market_pnl.values())
        self.debug(f"PnL Total Calculado: ${total_pnl:,.2f}")

    # --- DETECCIÓN DE SECTORES ---
    def detect_sector(self, title):
        t = title.lower()
        def has_word(keywords, text):
            pattern = r'\b(' + '|'.join(map(re.escape, keywords)) + r')\b'
            return bool(re.search(pattern, text))

        pol_kw = ['trump', 'biden', 'harris', 'election', 'senate', 'vote', 'president', 'republican', 'democrat', 'cabinet', 'nominee', 'poll', 'politics', 'vance', 'presidency']
        if has_word(pol_kw, t): return "Política"
        
        eco_kw = ['fed', 'rates', 'interest', 'inflation', 'cpi', 'gdp', 'recession', 'bank', 'spx', 'stocks', 'ipo', 'market', 'nasdaq', 'dow', 'rate', 'bps']
        if has_word(eco_kw, t): return "Economía"

        cry_kw = ['bitcoin', 'ethereum', 'solana', 'price', 'etf', 'btc', 'eth', 'crypto', 'token', 'nft', 'airdrop', 'doge', 'memecoin', 'chain', 'wallet']
        if has_word(cry_kw, t): return "Crypto"

        geo_kw = ['war', 'israel', 'iran', 'ukraine', 'russia', 'china', 'military', 'strike', 'border', 'ceasefire', 'gaza', 'hamas', 'weapon', 'nuclear', 'missile']
        if has_word(geo_kw, t): return "Geopolítica"

        spt_kw = ['nfl', 'nba', 'soccer', 'football', 'league', 'cup', 'winner', 'vs', 'score', 'champions', 'premier', 'ufc', 'game', 'win', 'lose', 'points', 'goals', 'season', 'mvp', 'fc', 'club', 'real', 'barcelona', 'madrid', 'city', 'utd', 'united', 'spread', 'handicap', 'over', 'under']
        if has_word(spt_kw, t) or 'vs.' in t: return "Deportes"
        
        sci_kw = ['spacex', 'nasa', 'mars', 'ai', 'chatgpt', 'openai', 'apple', 'google', 'fda', 'temperature', 'covid', 'launch', 'tech', 'tesla']
        if has_word(sci_kw, t): return "Ciencia/Tech"

        pop_kw = ['movie', 'song', 'spotify', 'grammy', 'oscar', 'taylor', 'swift', 'box', 'office', 'actor', 'music', 'album', 'award']
        if has_word(pop_kw, t): return "Pop Culture"
            
        return "Otros"

    # --- CÁLCULO DE MÉTRICAS ---
    def calculate_experience_score(self):
        """EXPERIENCIA (15 puntos)"""
        score = 0
        
        if self.activity:
            timestamps = [a.get('timestamp', 0) for a in self.activity if a.get('timestamp')]
            if timestamps:
                first_trade = min(timestamps)
                days_active = (time.time() - first_trade) / 86400
                
                if days_active > 365: score += 5
                elif days_active > 180: score += 4
                elif days_active > 90: score += 3
                elif days_active > 30: score += 2
                elif days_active > 1: score += 1
                
                self.days_active = max(1, int(days_active))
        
        # ✅ Análisis detallado del volumen
        buy_volume = 0
        sell_volume = 0
        trade_count = 0
        
        for a in self.activity:
            if a.get('type') == 'TRADE':
                usdc = float(a.get('usdcSize', 0))
                side = a.get('side')
                trade_count += 1
                
                if side == 'BUY':
                    buy_volume += usdc
                elif side == 'SELL':
                    sell_volume += usdc
        
        # Polymarket parece contar BUY + SELL
        total_volume = buy_volume + sell_volume
        self.total_volume = total_volume
        
        # Debug volumen
        self.debug(f"Volume breakdown: {trade_count} trades | BUY=${buy_volume:,.2f} + SELL=${sell_volume:,.2f} = TOTAL=${total_volume:,.2f}")
        
        if hasattr(self, 'days_active') and self.days_active > 0:
            volume_per_day = total_volume / self.days_active
            
            if volume_per_day > 100000: 
                score += 7
                self.strengths.append(f"✓ Actividad intensa (${volume_per_day:,.0f}/día)")
            elif volume_per_day > 50000: score += 6
            elif volume_per_day > 20000: score += 5
            elif volume_per_day > 10000: score += 4
            elif volume_per_day > 5000: score += 3
            elif volume_per_day > 1000: score += 2
            elif volume_per_day > 100: score += 1
            
            self.volume_per_day = volume_per_day
        
        unique_markets = len(set(a.get('title', '') for a in self.activity))
        if unique_markets > 50: score += 3
        elif unique_markets > 20: score += 2
        elif unique_markets > 5: score += 1
        
        self.unique_markets = unique_markets
        
        self.metrics['experience_score'] = score
        return score

    def calculate_discipline_score(self):
        """DISCIPLINA (20 puntos)"""
        score = 0
        
        if self.positions:
            active_positions = [p for p in self.positions if float(p.get('currentValue', 0)) > 0]
            
            if active_positions:
                total_value = sum(float(p.get('currentValue', 0)) for p in active_positions)
                if total_value > 0:
                    squares = sum((float(p.get('currentValue', 0)) / total_value) ** 2 for p in active_positions)
                    diversification = 1 - squares
                    
                    if diversification > 0.8: score += 10
                    elif diversification > 0.6: score += 8
                    elif diversification > 0.4: score += 6
                    elif diversification > 0.2: score += 4
                    elif diversification > 0: score += 2
                    
                    self.diversification_index = diversification
                    top_concentration = (float(active_positions[0].get('currentValue', 0)) / total_value * 100)
                    self.top_concentration = top_concentration
                    
                    if top_concentration > 80:
                        self.red_flags.append("⚠️ Concentración extrema (>80% en 1 posición)")
                    elif top_concentration < 30:
                        self.strengths.append("✓ Portfolio bien diversificado")
            else:
                if self.total_volume > 100000:
                    score += 5
        
        trade_sizes = [float(a.get('usdcSize', 0)) for a in self.activity 
                       if a.get('type') == 'TRADE' and a.get('side') == 'BUY']
        
        if len(trade_sizes) > 5:
            avg_size = sum(trade_sizes) / len(trade_sizes)
            std_dev = (sum((x - avg_size) ** 2 for x in trade_sizes) / len(trade_sizes)) ** 0.5
            cv = std_dev / avg_size if avg_size > 0 else 999
            
            if cv < 0.5: score += 6
            elif cv < 1.0: score += 5
            elif cv < 1.5: score += 3
            elif cv < 2.0: score += 2
            elif cv < 3.0: score += 1
            
            self.position_consistency = 1 / (1 + cv)
            self.avg_position_size = avg_size
        
        buys = sum(1 for a in self.activity if a.get('type') == 'TRADE' and a.get('side') == 'BUY')
        sells = sum(1 for a in self.activity if a.get('type') == 'TRADE' and a.get('side') == 'SELL')
        
        if buys > 0:
            sell_ratio = sells / buys
            if 0.3 <= sell_ratio <= 0.9: score += 4
            elif 0.2 <= sell_ratio < 1.2: score += 2
            elif sell_ratio < 0.1:
                self.red_flags.append("⚠️ Nunca cierra posiciones (acumulador)")
            
            self.sell_buy_ratio = sell_ratio
        
        self.metrics['discipline_score'] = score
        return score

    def calculate_specialization_score(self):
        """ESPECIALIZACIÓN (25 puntos)"""
        score = 0
        
        for activity in self.activity:
            if activity.get('type') == 'TRADE':
                title = activity.get('title', '')
                sector = self.detect_sector(title)
                self.sectors[sector] += float(activity.get('usdcSize', 0))
                self.market_count[title] += 1
        
        if self.sectors:
            total_sector_volume = sum(self.sectors.values())
            top_sector = max(self.sectors, key=self.sectors.get)
            top_sector_pct = (self.sectors[top_sector] / total_sector_volume * 100) if total_sector_volume > 0 else 0
            
            self.dominant_sector = top_sector
            self.sector_concentration = top_sector_pct
            
            if top_sector_pct > 80: 
                score += 15
                self.strengths.append(f"✓ Especialista en {top_sector}")
            elif top_sector_pct > 60: score += 12
            elif top_sector_pct > 40: score += 8
            elif top_sector_pct > 20: score += 4
        
        if self.market_count:
            deep_markets = sum(1 for count in self.market_count.values() if count >= 3)
            depth_ratio = deep_markets / len(self.market_count)
            
            if depth_ratio > 0.3: score += 10
            elif depth_ratio > 0.2: score += 7
            elif depth_ratio > 0.1: score += 4
            elif depth_ratio > 0.05: score += 2
            
            self.depth_ratio = depth_ratio
        
        self.metrics['specialization_score'] = score
        return score

    def calculate_current_performance_score(self):
        """RENDIMIENTO (40 puntos)"""
        score = 0
        
        if self.market_pnl:
            self.total_gain = sum(pnl for pnl in self.market_pnl.values() if pnl > 0)
            self.total_loss = sum(pnl for pnl in self.market_pnl.values() if pnl < 0)
            self.net_total = self.total_gain + self.total_loss
            self.total_winners = sum(1 for pnl in self.market_pnl.values() if pnl > 0)
            self.total_losers = sum(1 for pnl in self.market_pnl.values() if pnl < 0)
        
        if hasattr(self, 'net_total') and hasattr(self, 'total_volume') and self.total_volume > 0:
            roi_pct = (self.net_total / self.total_volume * 100)
            
            if roi_pct > 20: 
                score += 20
                self.strengths.append(f"✓ ROI excepcional ({roi_pct:.1f}%)")
            elif roi_pct > 12: score += 19
            elif roi_pct > 8: 
                score += 18
                self.strengths.append(f"✓ ROI sólido ({roi_pct:.1f}%)")
            elif roi_pct > 5: score += 15
            elif roi_pct > 3: score += 12
            elif roi_pct > 1: score += 9
            elif roi_pct > 0: score += 6
            elif roi_pct > -5: score += 3
            elif roi_pct <= -10:
                self.red_flags.append(f"⚠️ ROI negativo ({roi_pct:.1f}%)")
            
            self.roi = roi_pct
        
        if self.market_pnl:
            total_markets = len(self.market_pnl)
            winning_markets = sum(1 for pnl in self.market_pnl.values() if pnl > 0)
            overall_win_rate = winning_markets / total_markets if total_markets > 0 else 0
            
            if overall_win_rate > 0.75: 
                score += 15
                self.strengths.append(f"✓ Win rate excepcional ({overall_win_rate*100:.0f}%)")
            elif overall_win_rate > 0.65: 
                score += 14
                if "Win rate" not in str(self.strengths):
                    self.strengths.append(f"✓ Win rate excelente ({overall_win_rate*100:.0f}%)")
            elif overall_win_rate > 0.55: score += 12
            elif overall_win_rate > 0.50: score += 10
            elif overall_win_rate > 0.45: score += 8
            elif overall_win_rate > 0.40: score += 6
            elif overall_win_rate > 0.30: score += 4
            elif overall_win_rate > 0.20: score += 2
            
            self.overall_win_rate = overall_win_rate
        
        now = time.time()
        recent_activity = [a for a in self.activity if now - a.get('timestamp', 0) < 30*86400]
        
        if len(recent_activity) > 20: score += 5
        elif len(recent_activity) > 10: score += 4
        elif len(recent_activity) > 5: score += 3
        elif len(recent_activity) > 0: score += 2
        else:
            self.red_flags.append("⚠️ Sin actividad en último mes")
        
        self.recent_trades = len(recent_activity)
        
        self.metrics['current_performance_score'] = score
        return score

    def detect_red_flags(self):
        """Detecta patrones sospechosos"""
        merges = sum(1 for a in self.activity if a.get('type') == 'MERGE')
        trades = sum(1 for a in self.activity if a.get('type') == 'TRADE')
        
        if merges > 20 or (trades > 0 and merges / trades > 0.3):
            self.red_flags.append("🤖 Posible Market Maker / Bot")
        
        if self.activity:
            timestamps = sorted([a.get('timestamp', 0) for a in self.activity if a.get('timestamp')])
            if len(timestamps) > 1:
                duration_days = (timestamps[-1] - timestamps[0]) / 86400
                daily_trades = len(self.activity) / duration_days if duration_days > 0 else 0
                
                if daily_trades > 100:
                    self.red_flags.append("⚡ Frecuencia de bot (>100 ops/día)")

    def calculate_final_score(self):
        """Calcula score final y tier"""
        total = (self.metrics['experience_score'] + 
                self.metrics['discipline_score'] + 
                self.metrics['specialization_score'] + 
                self.metrics['current_performance_score'])
        
        self.metrics['total_score'] = total
        
        if any("bot" in flag.lower() for flag in self.red_flags):
            self.metrics['tier'] = "⛔ BOT/MM - NO COPIABLE"
        elif total >= 85:
            self.metrics['tier'] = "💎 DIAMOND"
        elif total >= 70:
            self.metrics['tier'] = "🥇 GOLD"
        elif total >= 50:
            self.metrics['tier'] = "🥈 SILVER"
        elif total >= 30:
            self.metrics['tier'] = "🥉 BRONZE"
        else:
            self.metrics['tier'] = "💀 ALTO RIESGO"
        
        return total

    def generate_recommendation(self):
        """Genera recomendación final"""
        score = self.metrics['total_score']
        
        if "BOT" in self.metrics['tier']:
            return "❌ NO COPIABLE - Entidad algorítmica"
        elif score >= 85:
            return "✅ ALTAMENTE COPIABLE - Trader excepcional con resultados probados"
        elif score >= 70:
            return "✅ COPIABLE CON CONFIANZA - Muy buen perfil de riesgo/retorno"
        elif score >= 60:
            return "✓ COPIABLE - Buen balance entre rendimiento y consistencia"
        elif score >= 50:
            return "⚠️ COPIABLE CON PRECAUCIÓN - Revisar especialización y riesgos"
        elif score >= 30:
            return "⚠️ RIESGO MEDIO - Solo para seguimiento y aprendizaje"
        else:
            return "❌ NO COPIABLE - Alto riesgo o resultados negativos"

    # --- REPORTE ---
    def generate_report(self):
        print("\n" + "="*70)
        print(f"🦈 POLYMARKET TRADER SCORE ANALYZER V2.2 (DEFINITIVE)")
        print(f"Analizando: {self.original_input}")
        print("="*70 + "\n")
        
        self.get_positions()
        self.get_activity()
        
        self.setup_file_logging()
        
        if not self.activity:
            print("❌ No se encontró actividad para este usuario")
            return
        
        if self.username:
            print(f"User: {self.username}\n")
        
        self.calculate_market_pnl()
        
        print("\n🔹 Calculando métricas de comportamiento...")
        
        self.calculate_experience_score()
        self.calculate_discipline_score()
        self.calculate_specialization_score()
        self.calculate_current_performance_score()
        self.detect_red_flags()
        self.calculate_final_score()
        
        # Generar reporte
        sep = "═"*70
        self.report("\n" + sep)
        self.report(f"🦈 POLYMARKET TRADER ANALYSIS V2.2 (DEFINITIVE)")
        if self.username:
            self.report(f"User: {self.username}")
        self.report(f"Wallet: {self.wallet}")
        self.report(f"Perfil: https://polymarket.com/profile/{self.wallet}")
        self.report(sep)
        
        self.report(f"\n📊 TRADER SCORE: {self.metrics['total_score']}/100 ({self.metrics['tier']})")
        self.report(f"\n🎯 RECOMENDACIÓN: {self.generate_recommendation()}")
        
        self.report(f"\n📈 DESGLOSE DE PUNTUACIÓN")
        self.report(f"   • Rendimiento:        {self.metrics['current_performance_score']}/40  ← Prioridad")
        self.report(f"   • Especialización:    {self.metrics['specialization_score']}/25")
        self.report(f"   • Disciplina:         {self.metrics['discipline_score']}/20")
        self.report(f"   • Experiencia:        {self.metrics['experience_score']}/15")
        
        if self.strengths:
            self.report(f"\n✅ FORTALEZAS")
            for strength in self.strengths:
                self.report(f"   {strength}")
        
        if self.red_flags:
            self.report(f"\n⚠️ RED FLAGS")
            for flag in self.red_flags:
                self.report(f"   {flag}")
        
        self.report(f"\n🎭 PERFIL DE TRADER")
        self.report(f"   • Días Activo:        {getattr(self, 'days_active', 'N/A')}")
        self.report(f"   • Mercados Únicos:    {getattr(self, 'unique_markets', 'N/A')}")
        self.report(f"   • Volumen Total:      ${getattr(self, 'total_volume', 0):,.2f}")
        self.report(f"   • Posiciones Abiertas: {len([p for p in self.positions if float(p.get('size', 0)) > 0])}")
        self.report(f"   • Mercados Cerrados:  {len([m for m in self.market_status.values() if m == 'CLOSED'])}")
        self.report(f"   • Trades Recientes:   {getattr(self, 'recent_trades', 'N/A')} (último mes)")
        
        # ⚠️ DISCLAIMER sobre limitaciones de la API
        if len(self.activity) < 1000:
            self.report(f"\n   ⚠️  NOTA: Análisis basado en {len(self.activity)} eventos de la API pública.")
            self.report(f"   ⚠️  Polymarket puede mostrar más volumen/historial en su interfaz.")
            self.report(f"   ⚠️  Verifica datos completos en: https://polymarket.com/profile/{self.wallet}")
        
        if hasattr(self, 'net_total'):
            self.report(f"\n💰 PERFORMANCE HISTÓRICO")
            self.report(f"   • Volume Traded:      ${self.total_volume:,.2f}")
            self.report(f"   • Gain:               +${getattr(self, 'total_gain', 0):,.2f}")
            self.report(f"   • Loss:               ${getattr(self, 'total_loss', 0):,.2f}")
            net_color = "🟢" if self.net_total >= 0 else "🔴"
            self.report(f"   • Net Total:          {net_color} ${self.net_total:,.2f}")
            
            if hasattr(self, 'roi'):
                roi_color = "🟢" if self.roi > 0 else "🔴"
                self.report(f"   • ROI:                {roi_color} {self.roi:.2f}%")
            
            self.report(f"   • Win Rate:           {getattr(self, 'overall_win_rate', 0)*100:.1f}%")
            self.report(f"   • Mercados Operados:  {len(self.market_pnl)}")
            self.report(f"   • Mercados Ganadores: {getattr(self, 'total_winners', 0)}")
            self.report(f"   • Mercados Perdedores: {getattr(self, 'total_losers', 0)}")
        
        self.report(f"\n🎲 GESTIÓN DE RIESGO")
        self.report(f"   • Diversificación:    {getattr(self, 'diversification_index', 0)*10:.1f}/10")
        self.report(f"   • Concentración Top:  {getattr(self, 'top_concentration', 0):.1f}%")
        self.report(f"   • Tamaño Promedio:    ${getattr(self, 'avg_position_size', 0):,.2f}")
        self.report(f"   • Consistencia:       {getattr(self, 'position_consistency', 0)*10:.1f}/10")
        
        if hasattr(self, 'dominant_sector'):
            self.report(f"\n🧠 ESPECIALIZACIÓN")
            self.report(f"   • Sector Dominante:   {self.dominant_sector} ({self.sector_concentration:.1f}%)")
            self.report(f"   • Profundidad:        {getattr(self, 'depth_ratio', 0)*100:.1f}% mercados con 3+ trades")
            
            self.report(f"\n   📊 Distribución por Sector:")
            sorted_sectors = sorted(self.sectors.items(), key=lambda x: x[1], reverse=True)
            for sector, volume in sorted_sectors[:5]:
                pct = (volume / sum(self.sectors.values()) * 100) if sum(self.sectors.values()) > 0 else 0
                self.report(f"      • {sector:<15} {pct:>5.1f}%")
        
        active_pos = [p for p in self.positions if float(p.get('size', 0)) > 0]
        if active_pos:
            self.report(f"\n🏦 POSICIONES ABIERTAS (Top 5)")
            self.report(f"   {'Mercado':<40} {'Valor':>12} {'PnL':>10}")
            self.report("   " + "-"*65)
            for p in active_pos[:5]:
                title = p.get('title', 'N/A')[:38] + ".."
                val = float(p.get('currentValue', 0))
                pnl = float(p.get('cashPnl', 0))
                pnl_indicator = "🟢" if pnl >= 0 else "🔴"
                self.report(f"   {title:<40} ${val:>10,.2f} {pnl_indicator} ${pnl:>7,.0f}")
        
        if self.market_pnl:
            all_markets = list(self.market_pnl.items())
            all_markets.sort(key=lambda x: x[1], reverse=True)
            
            self.report(f"\n💎 TOP MERCADOS POR PnL")
            self.report(f"   {'Mercado':<40} {'Estado':>8} {'PnL':>12}")
            self.report("   " + "-"*68)
            
            winners = [(t, p) for t, p in all_markets if p > 0][:5]
            if winners:
                self.report(f"\n   🏆 TOP 5 GANADORES:")
                for title, pnl in winners:
                    short_title = title[:40] + ".." if len(title) > 40 else title
                    status = self.market_status.get(title, 'UNKNOWN')
                    status_icon = "✅" if status == "CLOSED" else "📊"
                    self.report(f"   {short_title:<40} {status_icon:>8}     ${pnl:>10,.0f}")
            
            # ✅ FIXED: Top 5 perdedores ordenados de peor a menor (descendente por valor absoluto)
            losers = [(t, p) for t, p in all_markets if p < 0]
            losers.sort(key=lambda x: x[1])  # Ascendente = más negativo primero
            losers = losers[:5]
            
            if losers:
                self.report(f"\n   💀 TOP 5 PERDEDORES:")
                for title, pnl in losers:
                    short_title = title[:40] + ".." if len(title) > 40 else title
                    status = self.market_status.get(title, 'UNKNOWN')
                    status_icon = "🔴" if status == "OPEN" else "❌"
                    self.report(f"   {short_title:<40} {status_icon:>8}     ${pnl:>10,.0f}")
        
        self.report(f"\n💡 VEREDICTO FINAL")
        score = self.metrics['total_score']
        
        if score >= 85:
            verdict = "Este trader muestra resultados excepcionales con alta rentabilidad y win rate superior. Perfil elite para seguir."
        elif score >= 70:
            verdict = "Trader con excelente balance riesgo/retorno. Especialización clara y resultados consistentemente positivos."
        elif score >= 60:
            verdict = "Trader rentable con buen rendimiento. Puede tener edge en su nicho. Revisar gestión de riesgo antes de copiar."
        elif score >= 50:
            verdict = "Perfil moderado con resultados mixtos. Especialización visible pero requiere más consistencia."
        elif score >= 30:
            verdict = "Trader con riesgo significativo. Solo recomendable para seguimiento y aprendizaje, no para copiar."
        else:
            verdict = "Alto riesgo o trader novato con resultados negativos. No recomendable para copiar estrategias."
        
        self.report(f"   {verdict}")
        
        self.report(f"\n🎯 VERIFICACIÓN")
        self.report(f"   Compara con Polymarket: https://polymarket.com/profile/{self.wallet}")
        
        # Debug info al final
        if DEBUG_MODE and self.debug_info:
            self.report(f"\n🔧 DEBUG INFO (primeras 10 entradas):")
            for i, msg in enumerate(self.debug_info[:10]):
                self.report(f"   {i+1}. {msg}")
        
        self.report("\n" + sep + "\n")
        self.close_log()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        inp = sys.argv[1]
    else:
        print("\n🦈 POLYWHALE TRADER SCORE ANALYZER V2.2 (DEFINITIVE)")
        print("Usa marketSlug + cashPnl API + debugging extensivo\n")
        inp = input("👉 Address/Usuario/URL: ")
    
    analyzer = TraderAnalyzer(inp)
    analyzer.generate_report()