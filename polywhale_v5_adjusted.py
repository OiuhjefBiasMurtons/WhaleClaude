#!/usr/bin/env python3
"""
🦈 POLYWHALE TRADER ANALYZER V5.0 - ADJUSTED
Sistema de análisis de FIABILIDAD y EFECTIVIDAD de traders de Polymarket
Scraping directo de polymarketanalytics.com para métricas verificadas

SISTEMA DE SCORING AJUSTADO (100 puntos):
- Rentabilidad (35 pts): ROI, Profit Factor, PnL absoluto [+5 pts]
- Consistencia (25 pts): Win Rate, ratio ganancia/pérdida promedio
- Gestión de Riesgo (20 pts): Drawdown máximo, diversificación [-5 pts]
- Experiencia (20 pts): Antigüedad, volumen, ranking global

AJUSTES vs V5.0 original:
- Rentabilidad aumentada de 30 a 35 puntos (más peso al rendimiento)
- Gestión de Riesgo reducida de 25 a 20 puntos (menos penalización)
- Umbrales suavizados: ROI >25% (era >30%), Win Rate >70% (era >75%)
"""

import requests
import sys
import os
import time
import re
import subprocess
import json
from datetime import datetime
from collections import defaultdict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Verificar dependencias
XVFB_AVAILABLE = subprocess.run(['which', 'xvfb-run'], capture_output=True).returncode == 0
SELENIUM_AVAILABLE = False
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except ImportError:
    pass

# --- CONFIGURACIÓN ---
DATA_API = "https://data-api.polymarket.com"
ANALYTICS_URL = "https://polymarketanalytics.com/traders"
CHROME_PATH = os.path.expanduser("~/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome")
OUTPUT_DIR = "TraderAnalysis"
SCRAPE_TIMEOUT = 25  # Aumentado para capturar datos dinámicos (trades/markets)

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504, 429])
session.mount('https://', HTTPAdapter(max_retries=retries))


class TraderAnalyzer:
    def __init__(self, input_str):
        self.original_input = input_str
        self.wallet = self.resolve_input(input_str)
        self.username = None
        self.file_handle = None

        # Datos scrapeados de polymarketanalytics
        self.scraped_data = {}

        # Sistema de scoring V5.0 AJUSTADO
        self.scores = {
            'profitability': 0,      # 35 puntos max (+5)
            'consistency': 0,         # 25 puntos max (igual)
            'risk_management': 0,     # 20 puntos max (-5)
            'experience': 0,          # 20 puntos max (igual)
            'total': 0,
            'tier': 'UNKNOWN',
            'reliability_grade': 'F'
        }

        self.red_flags = []
        self.strengths = []

    def resolve_input(self, i):
        clean = i.strip()
        if "profile/" in clean:
            return clean.split("profile/")[-1].split("?")[0].replace("/","")
        if "traders/" in clean:
            return clean.split("traders/")[-1].split("#")[0].split("?")[0]
        if clean.startswith("@"):
            return clean.replace("@","")
        return clean.lower()

    def setup_file_logging(self):
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        
        # Usar username limpio si está disponible
        if self.scraped_data.get('username_clean'):
            safe_name = self.scraped_data['username_clean'][:30]
        elif self.username:
            safe_name = re.sub(r'[^\w\-]', '_', self.username)[:30]
        else:
            safe_name = self.wallet[:12]
        
        self.filename = f"{OUTPUT_DIR}/{safe_name}_{timestamp}.txt"
        try:
            self.file_handle = open(self.filename, "w", encoding="utf-8")
        except:
            pass

    def report(self, msg, end="\n"):
        print(msg, end=end)
        if self.file_handle:
            self.file_handle.write(msg + end)
            self.file_handle.flush()

    def close_log(self):
        if self.file_handle:
            self.file_handle.close()
            print(f"\n💾 Análisis guardado en: {self.filename}")

    # --- SCRAPING DE POLYMARKETANALYTICS ---
    def scrape_polymarketanalytics(self):
        """Extrae TODOS los datos disponibles de polymarketanalytics.com"""
        if not SELENIUM_AVAILABLE or not XVFB_AVAILABLE or not os.path.exists(CHROME_PATH):
            print("   ⚠️  Scraping no disponible. Verificar dependencias.")
            return False

        print("🔹 Scraping polymarketanalytics.com...")

        script_content = f'''
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import json
import re

chrome_path = "{CHROME_PATH}"
wallet = "{self.wallet}"

options = uc.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.binary_location = chrome_path

try:
    driver = uc.Chrome(options=options, version_main=143)

    # Cargar página principal
    url = f"https://polymarketanalytics.com/traders/{{wallet}}"
    driver.get(url)
    time.sleep({SCRAPE_TIMEOUT})

    page_text = driver.find_element(By.TAG_NAME, "body").text
    data = {{"success": True}}

    # === USERNAME ===
    # Intentar extraer username del título de la página primero
    try:
        page_title = driver.title
        if '|' in page_title:
            username_raw = page_title.split('|')[0].strip()
            # Limpiar username (remover caracteres especiales para filename)
            data['username'] = username_raw
            data['username_clean'] = re.sub(r'[^\w\-]', '_', username_raw)
    except:
        pass
    
    # Fallback: buscar @username en el texto
    if 'username' not in data:
        username_match = re.search(r'@([A-Za-z0-9_-]+)', page_text)
        if username_match:
            data['username'] = username_match.group(1)
            data['username_clean'] = username_match.group(1)
    
    # === MÉTRICAS PRINCIPALES ===
    rank_match = re.search(r'Rank#([\\d,]+)', page_text)
    if rank_match:
        data['rank'] = int(rank_match.group(1).replace(',', ''))

    pnl_match = re.search(r'Polymarket PnL\\s*[-+]?\\$?([\\d,.-]+)', page_text)
    if pnl_match:
        pnl_str = pnl_match.group(1).replace(',', '')
        # Buscar si hay un signo negativo antes del símbolo de dólar
        negative_match = re.search(r'Polymarket PnL\\s*-', page_text)
        data['pnl'] = -float(pnl_str) if negative_match else float(pnl_str)

    gains_match = re.search(r'Total Gains\\s*\\+?\\$?([\\d,.-]+)', page_text)
    if gains_match:
        data['total_gains'] = float(gains_match.group(1).replace(',', ''))

    losses_match = re.search(r'Total Losses\\s*[-]?\\$?([\\d,.-]+)', page_text)
    if losses_match:
        losses_str = losses_match.group(1).replace(',', '')
        # Las pérdidas ya vienen como número positivo, convertirlo
        data['total_losses'] = abs(float(losses_str))

    winrate_match = re.search(r'Win Rate\\s*([\\d.]+)%', page_text)
    if winrate_match:
        data['win_rate'] = float(winrate_match.group(1))

    # === NÚMERO DE TRADES TOTALES ===
    # Intentar múltiples patrones
    trades_match = re.search(r'Total Trades\\s*([\\d,]+)', page_text)
    if not trades_match:
        trades_match = re.search(r'Trades\\s*([\\d,]+)', page_text)
    if not trades_match:
        # Buscar en formato alternativo
        trades_match = re.search(r'([\\d,]+)\\s*trades', page_text, re.IGNORECASE)
    if trades_match:
        data['total_trades'] = int(trades_match.group(1).replace(',', ''))
    
    # === NÚMERO DE MARKETS ===
    markets_match = re.search(r'Markets Traded\\s*([\\d,]+)', page_text)
    if not markets_match:
        markets_match = re.search(r'Markets\\s*([\\d,]+)', page_text)
    if not markets_match:
        # Buscar en formato alternativo
        markets_match = re.search(r'([\\d,]+)\\s*markets', page_text, re.IGNORECASE)
    if markets_match:
        data['markets_traded'] = int(markets_match.group(1).replace(',', ''))
    
    # === Si no encontramos trades/markets, intentar scroll y espera adicional ===
    if 'total_trades' not in data or 'markets_traded' not in data:
        try:
            # Múltiples scrolls para asegurar carga de datos dinámicos
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(4)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)
            
            # Re-extraer texto completo
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Reintentar extracción con patrones más amplios
            if 'total_trades' not in data:
                # Intentar múltiples patrones
                patterns = [
                    r'([\\d,]+)\\s*[Tt]rades',
                    r'[Tt]rades[:\\s]*([\\d,]+)',
                    r'Total\\s+[Tt]rades[:\\s]*([\\d,]+)',
                    r'#\\s*of\\s+[Tt]rades[:\\s]*([\\d,]+)',
                ]
                for pattern in patterns:
                    trades_match = re.search(pattern, page_text)
                    if trades_match:
                        data['total_trades'] = int(trades_match.group(1).replace(',', ''))
                        break
            
            if 'markets_traded' not in data:
                # Intentar múltiples patrones
                patterns = [
                    r'([\\d,]+)\\s*[Mm]arkets',
                    r'[Mm]arkets[:\\s]*([\\d,]+)',
                    r'Markets\\s+[Tt]raded[:\\s]*([\\d,]+)',
                    r'#\\s*of\\s+[Mm]arkets[:\\s]*([\\d,]+)',
                ]
                for pattern in patterns:
                    markets_match = re.search(pattern, page_text)
                    if markets_match:
                        data['markets_traded'] = int(markets_match.group(1).replace(',', ''))
                        break
        except:
            pass

    value_match = re.search(r'Total Value\\s*\\$?([\\d,.-]+)', page_text)
    if value_match:
        data['total_value'] = float(value_match.group(1).replace(',', ''))

    positions_match = re.search(r'Polymarket Positions\\s*\\$?([\\d,.-]+)', page_text)
    if positions_match:
        data['positions_value'] = float(positions_match.group(1).replace(',', ''))

    # === BADGES ===
    badges = []
    if 'Overall PnL > $100k' in page_text:
        badges.append('pnl_100k')
    elif 'Overall PnL > $10k' in page_text:
        badges.append('pnl_10k')
    if '> 1 year old' in page_text:
        badges.append('veteran')
    if 'Overall Win Rate > 67%' in page_text:
        badges.append('high_winrate')
    elif 'Overall Win Rate > 60%' in page_text:
        badges.append('good_winrate')
    data['badges'] = badges

    # === BIGGEST WINS ===
    wins_pattern = r'#(\\d+)\\s+([^\\n]+?)\\s+\\+\\$([\\d,]+)'
    wins = re.findall(wins_pattern, page_text)
    data['biggest_wins'] = [{{'rank': int(w[0]), 'market': w[1].strip(), 'amount': float(w[2].replace(',', ''))}} for w in wins[:15]]

    # === BIGGEST LOSSES (click en tab) ===
    try:
        losses_tab = driver.find_element(By.XPATH, "//*[contains(text(), 'Biggest Losses')]")
        losses_tab.click()
        time.sleep(2)
        page_text_losses = driver.find_element(By.TAG_NAME, "body").text
        losses_pattern = r'#(\\d+)\\s+([^\\n]+?)\\s+-\\$([\\d,]+)'
        losses = re.findall(losses_pattern, page_text_losses)
        data['biggest_losses'] = [{{'rank': int(l[0]), 'market': l[1].strip(), 'amount': float(l[2].replace(',', ''))}} for l in losses[:15]]
    except:
        data['biggest_losses'] = []

    # === CATEGORIES ===
    if 'Category Performance' in page_text:
        cat_section = page_text.split('Category Performance')[-1].split('Polymarket Analytics')[0]
        cat_pattern = r'#(\\d+)\\s+([A-Za-z\\s]+?)\\s+\\+?\\$?([\\d,.-]+)'
        categories = re.findall(cat_pattern, cat_section)
        data['categories'] = [{{'rank': int(c[0]), 'name': c[1].strip(), 'pnl': float(c[2].replace(',', ''))}} for c in categories[:10]]
    else:
        data['categories'] = []

    # === MÉTRICAS DERIVADAS ===
    if 'total_gains' in data and 'total_losses' in data and data['total_losses'] > 0:
        data['profit_factor'] = data['total_gains'] / data['total_losses']

    if data.get('biggest_wins'):
        data['avg_win'] = sum(w['amount'] for w in data['biggest_wins']) / len(data['biggest_wins'])
        data['max_win'] = max(w['amount'] for w in data['biggest_wins'])

    if data.get('biggest_losses'):
        data['avg_loss'] = sum(l['amount'] for l in data['biggest_losses']) / len(data['biggest_losses'])
        data['max_loss'] = max(l['amount'] for l in data['biggest_losses'])

    print(json.dumps(data))
    driver.quit()

except Exception as e:
    print(json.dumps({{"success": False, "error": str(e)}}))
    try:
        driver.quit()
    except:
        pass
'''

        script_path = "/tmp/polywhale_scraper_v5_adj.py"
        with open(script_path, "w") as f:
            f.write(script_content)

        try:
            result = subprocess.run(
                ["xvfb-run", "-a", sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=90
            )

            lines = result.stdout.strip().split('\n')
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                    if data.get('success'):
                        self.scraped_data = data
                        # Guardar username real si existe
                        if data.get('username'):
                            self.username = data['username']
                        else:
                            self.username = f"Rank #{data.get('rank', '?')}"
                        print(f"   ✅ Datos obtenidos de polymarketanalytics.com")
                        return True
                    elif 'error' in data:
                        print(f"   ⚠️  Error: {data['error']}")
                        return False
                except json.JSONDecodeError:
                    continue

            print("   ⚠️  No se pudieron extraer datos")
            return False

        except subprocess.TimeoutExpired:
            print("   ⚠️  Timeout en scraping")
            return False
        except Exception as e:
            print(f"   ⚠️  Error: {e}")
            return False
        finally:
            try:
                os.remove(script_path)
            except:
                pass

    # --- CÁLCULO DE SCORES (AJUSTADOS) ---
    def calculate_profitability_score(self):
        """
        RENTABILIDAD (35 puntos) - AJUSTADO [+5 pts]
        - ROI efectivo (15 pts) [+3]
        - Profit Factor (12 pts) [+2]
        - PnL absoluto (8 pts) [igual]
        """
        score = 0
        d = self.scraped_data

        # 1. ROI = PnL / (Gains + Losses) * 100
        pnl = d.get('pnl', 0)
        total_traded = d.get('total_gains', 0) + d.get('total_losses', 0)

        if total_traded > 0:
            roi = (pnl / total_traded) * 100
            self.roi = roi

            # ✅ AJUSTE: Umbrales más realistas + bonificación a rango 10-25%
            if roi > 25:  # Era >30
                score += 15  # Era 12
                self.strengths.append(f"✓ ROI excepcional: {roi:.1f}%")
            elif roi > 18:  # Era >20
                score += 13  # Era 10
                self.strengths.append(f"✓ ROI excelente: {roi:.1f}%")
            elif roi > 13:  # Era >15
                score += 11  # Era 8, ahora 11 (+3)
                self.strengths.append(f"✓ ROI muy bueno: {roi:.1f}%")
            elif roi > 10:  # NUEVO: reconocer ROI >10%
                score += 9  # Era 8, ahora 9 (+1)
                self.strengths.append(f"✓ ROI sólido: {roi:.1f}%")
            elif roi > 7:  # Era >9
                score += 7  # Era 8, ahora 7 (-1)
            elif roi > 5:
                score += 5  # Igual
            elif roi > 2:  # Era >0
                score += 3  # Era 2
            elif roi > 0:
                score += 1
            elif roi < -10:
                self.red_flags.append(f"⚠️ ROI negativo: {roi:.1f}%")

        # 2. Profit Factor = Gains / Losses
        profit_factor = d.get('profit_factor', 0)
        self.profit_factor = profit_factor

        # ✅ AJUSTE: Umbrales más alcanzables + bonificación al rango 1.2-2.0x
        if profit_factor > 2.8:  # Era >3.0
            score += 12  # Era 10
            self.strengths.append(f"✓ Profit Factor elite: {profit_factor:.2f}")
        elif profit_factor > 2.3:  # Era >2.5
            score += 10  # Era 9
            self.strengths.append(f"✓ Profit Factor excelente: {profit_factor:.2f}")
        elif profit_factor > 1.9:  # Era >2.0
            score += 8  # Era 7
        elif profit_factor > 1.5:
            score += 7  # Era 5, ahora 7 (+2)
        elif profit_factor > 1.2:
            score += 5  # Era 3, ahora 5 (+2) ← Aquí entra Predictoor99
            self.strengths.append(f"✓ Profit Factor positivo: {profit_factor:.2f}")
        elif profit_factor > 1.0:
            score += 2  # Era 1
            score += 2  # Era 1
        elif profit_factor < 1.0:
            self.red_flags.append(f"⚠️ Profit Factor < 1: {profit_factor:.2f}")

        # 3. PnL Absoluto (tamaño del éxito) - SIN CAMBIOS
        if pnl > 100000:
            score += 8
        elif pnl > 50000:
            score += 6
        elif pnl > 20000:
            score += 4
        elif pnl > 5000:
            score += 2
        elif pnl > 0:
            score += 1

        self.scores['profitability'] = min(score, 35)
        return self.scores['profitability']

    def calculate_consistency_score(self):
        """
        CONSISTENCIA (25 puntos) - AJUSTADO
        - Win Rate (12 pts) [umbrales suavizados]
        - Ratio Avg Win / Avg Loss (8 pts)
        - Distribución de ganancias (5 pts)
        """
        score = 0
        d = self.scraped_data

        # 1. Win Rate - ✅ AJUSTE: Umbrales más realistas
        win_rate = d.get('win_rate', 0)
        self.win_rate = win_rate

        if win_rate > 70:  # Era >75
            score += 12
            self.strengths.append(f"✓ Win Rate excepcional: {win_rate:.1f}%")
        elif win_rate > 62:  # Era >67
            score += 10
            self.strengths.append(f"✓ Win Rate alto: {win_rate:.1f}%")
        elif win_rate > 57:  # Era >60
            score += 8
        elif win_rate > 52:  # Era >55
            score += 6
        elif win_rate > 48:  # Era >50
            score += 4
        elif win_rate > 43:  # Era >45
            score += 2
        elif win_rate < 40:
            self.red_flags.append(f"⚠️ Win Rate bajo: {win_rate:.1f}%")

        # 2. Ratio Avg Win / Avg Loss - SIN CAMBIOS
        avg_win = d.get('avg_win', 0)
        avg_loss = d.get('avg_loss', 1)

        if avg_loss > 0:
            win_loss_ratio = avg_win / avg_loss
            self.win_loss_ratio = win_loss_ratio

            if win_loss_ratio > 2.0:
                score += 8
                self.strengths.append(f"✓ Ganancias 2x mayores que pérdidas")
            elif win_loss_ratio > 1.5:
                score += 6
            elif win_loss_ratio > 1.2:
                score += 4
            elif win_loss_ratio > 1.0:
                score += 2
            elif win_loss_ratio < 0.8:
                self.red_flags.append(f"⚠️ Pérdidas promedio mayores que ganancias")

        # 3. Distribución de ganancias - SIN CAMBIOS
        wins = d.get('biggest_wins', [])
        if len(wins) >= 3 and d.get('total_gains', 0) > 0:
            top_win = wins[0]['amount'] if wins else 0
            total_gains = d.get('total_gains', 1)
            concentration = top_win / total_gains

            if concentration < 0.2:
                score += 5
                self.strengths.append("✓ Ganancias bien distribuidas")
            elif concentration < 0.3:
                score += 4
            elif concentration < 0.4:
                score += 2
            elif concentration > 0.5:
                self.red_flags.append(f"⚠️ {concentration*100:.0f}% de ganancias en 1 trade")

        self.scores['consistency'] = min(score, 25)
        return self.scores['consistency']

    def calculate_risk_management_score(self):
        """
        GESTIÓN DE RIESGO (20 puntos) - AJUSTADO [-5 pts]
        - Control de pérdidas máximas (10 pts) [-2]
        - Diversificación por categoría (6 pts) [-2]
        - Ratio PnL / Max Loss (4 pts) [-1]
        """
        score = 0
        d = self.scraped_data

        # 1. Control de pérdidas máximas - ✅ AJUSTE: Menos puntos pero mismos umbrales
        max_loss = d.get('max_loss', 0)
        total_losses = d.get('total_losses', 1)
        pnl = d.get('pnl', 0)

        if total_losses > 0 and max_loss > 0:
            loss_concentration = max_loss / total_losses
            self.max_loss = max_loss
            self.loss_concentration = loss_concentration

            if loss_concentration < 0.15:
                score += 10  # Era 12
                self.strengths.append("✓ Pérdidas bien controladas")
            elif loss_concentration < 0.25:
                score += 8  # Era 9
            elif loss_concentration < 0.35:
                score += 5  # Era 6
            elif loss_concentration < 0.5:
                score += 2  # Era 3
            else:
                self.red_flags.append(f"⚠️ {loss_concentration*100:.0f}% de pérdidas en 1 trade")

        # 2. Diversificación por categoría - ✅ AJUSTE: Menos estricto
        categories = d.get('categories', [])
        if len(categories) >= 2:
            if len(categories) >= 5:
                score += 6  # Era 8
                self.strengths.append(f"✓ Opera en {len(categories)} categorías")
            elif len(categories) >= 3:
                score += 4  # Era 5
            elif len(categories) >= 2:
                score += 2  # Igual
        else:
            self.red_flags.append("⚠️ Solo opera en 1 categoría")

        # 3. Ratio PnL / Max Loss - ✅ AJUSTE: Menos puntos
        if max_loss > 0:
            risk_reward = pnl / max_loss
            self.risk_reward_ratio = risk_reward

            if risk_reward > 10:
                score += 4  # Era 5
            elif risk_reward > 5:
                score += 3  # Era 4
            elif risk_reward > 3:
                score += 2  # Era 3
            elif risk_reward > 1:
                score += 1  # Igual

        self.scores['risk_management'] = min(score, 20)
        return self.scores['risk_management']

    def calculate_experience_score(self):
        """
        EXPERIENCIA (20 puntos) - SIN CAMBIOS
        - Antigüedad y badges (8 pts)
        - Ranking global (7 pts)
        - Volumen operado (5 pts)
        """
        score = 0
        d = self.scraped_data

        # 1. Badges de experiencia
        badges = d.get('badges', [])

        if 'veteran' in badges:
            score += 5
            self.strengths.append("✓ Cuenta con más de 1 año")

        if 'pnl_100k' in badges:
            score += 3
        elif 'pnl_10k' in badges:
            score += 2

        # 2. Ranking global
        rank = d.get('rank', 999999)
        self.rank = rank

        if rank <= 100:
            score += 7
            self.strengths.append(f"✓ Top 100 global (#{rank})")
        elif rank <= 500:
            score += 6
            self.strengths.append(f"✓ Top 500 global (#{rank})")
        elif rank <= 1000:
            score += 5
        elif rank <= 2500:
            score += 3
        elif rank <= 5000:
            score += 2
        elif rank <= 10000:
            score += 1

        # 3. Volumen operado (total_gains + total_losses)
        total_traded = d.get('total_gains', 0) + d.get('total_losses', 0)
        self.total_traded = total_traded

        if total_traded > 500000:
            score += 5
        elif total_traded > 200000:
            score += 4
        elif total_traded > 100000:
            score += 3
        elif total_traded > 50000:
            score += 2
        elif total_traded > 10000:
            score += 1

        self.scores['experience'] = min(score, 20)
        return self.scores['experience']

    def detect_bot_behavior(self):
        """
        🤖 DETECCIÓN DE BOTS
        Analiza múltiples indicadores para determinar si es un bot/MM
        
        Indicadores:
        1. Trades/Market ratio (>50 trades por mercado = bot)
        2. Frecuencia extrema (>7000 trades totales)
        3. Profit Factor muy bajo + volumen alto (market maker)
        4. Volumen extremo con pocos mercados (>4000 trades en <50 mercados)
        """
        d = self.scraped_data
        is_bot = False
        bot_confidence = 0  # 0-100%
        bot_reasons = []
        
        total_trades = d.get('total_trades', 0)
        markets_traded = d.get('markets_traded', 0)
        total_volume = d.get('total_gains', 0) + d.get('total_losses', 0)
        profit_factor = d.get('profit_factor', 0)
        
        # INDICADOR 1: Trades por mercado (bots hacen muchos trades en pocos mercados)
        if markets_traded > 0 and total_trades > 0:
            trades_per_market = total_trades / markets_traded
            
            if trades_per_market > 50:  # Era >100
                is_bot = True
                bot_confidence += 40
                bot_reasons.append(f"🤖 {trades_per_market:.0f} trades/mercado (bot confirmado)")
            elif trades_per_market > 25:  # Era >50
                bot_confidence += 30
                bot_reasons.append(f"⚠️ {trades_per_market:.0f} trades/mercado (posible bot)")
            elif trades_per_market > 15:  # Era >30
                bot_confidence += 15
                bot_reasons.append(f"⚡ {trades_per_market:.0f} trades/mercado (alta frecuencia)")
        
        # INDICADOR 2: Volumen extremo con pocos mercados
        if total_trades > 4000 and markets_traded < 50:  # Era >5000
            is_bot = True
            bot_confidence += 30
            bot_reasons.append(f"🤖 {total_trades:,} trades en solo {markets_traded} mercados")
        
        # INDICADOR 3: Volumen muy alto con profit factor cercano a 1 (market maker)
        if total_volume > 1000000 and 0.95 < profit_factor < 1.05:
            is_bot = True
            bot_confidence += 35
            bot_reasons.append(f"🤖 Market Maker (PF={profit_factor:.2f}, Vol=${total_volume/1e6:.1f}M)")
        
        # INDICADOR 4: Frecuencia absurda
        if total_trades > 7000:  # Era >10000
            is_bot = True
            bot_confidence += 50
            bot_reasons.append(f"🤖 Frecuencia extrema ({total_trades:,} trades)")
        
        # INDICADOR 5: Win rate exactamente 50% con alto volumen (bot arbitrajista)
        win_rate = d.get('win_rate', 0)
        if 49.5 <= win_rate <= 50.5 and total_volume > 500000:
            bot_confidence += 25
            bot_reasons.append(f"⚠️ Win Rate sospechoso (50% exacto con alto volumen)")
        
        # ✅ INDICADOR 6 NUEVO: Hiperactividad (muchos trades + muchos mercados)
        # Bots sofisticados operan en MUCHOS mercados con frecuencia alta
        if total_trades > 3000 and markets_traded > 100:
            # Esto captura bots que se distribuyen en muchos mercados
            is_bot = True
            bot_confidence += 35
            bot_reasons.append(f"🤖 Hiperactividad: {total_trades:,} trades en {markets_traded} mercados")
        
        # ✅ INDICADOR 7 NUEVO: Threshold más bajo para confirmación múltiple
        # Si tiene 2000+ trades Y 15+ trades/mercado = probablemente bot
        if total_trades > 2000 and markets_traded > 0:
            tpm = total_trades / markets_traded
            if tpm > 15:
                bot_confidence += 20
                bot_reasons.append(f"⚠️ Volumen sospechoso: {total_trades:,} trades con {tpm:.0f} t/m")
        
        # ✅ INDICADOR 8 NUEVO: Detección heurística cuando faltan datos
        # Si no tenemos total_trades pero tenemos señales indirectas
        if total_trades == 0 and total_volume > 10000000:  # >$10M (era $20M)
            # Volumen extremadamente alto = posible bot/MM
            if profit_factor < 0.9:  # Pérdidas netas + volumen alto = bot malo o MM
                bot_confidence += 25
                bot_reasons.append(f"⚠️ Volumen extremo ${total_volume/1e6:.1f}M con PF bajo (posible bot)")
            
            # Ranking muy malo + volumen alto = bot
            rank = d.get('rank', 0)
            if rank > 500000 and total_volume > 10000000:  # Bajado de 1M y $25M
                is_bot = True
                bot_confidence += 35  # Aumentado de 30 a 35
                bot_reasons.append(f"🤖 Ranking #{rank:,} con ${total_volume/1e6:.1f}M operados (patrón bot)")
        
        # ✅ INDICADOR 9 NUEVO: Bot perdedor con volumen medio-alto
        # Volumen >$5M + pérdidas netas + ranking malo = bot ineficiente
        if total_trades == 0 and total_volume > 5000000:
            rank = d.get('rank', 0)
            pnl = d.get('pnl', 0)
            
            # Ranking >1M + pérdidas >$500k + volumen >$5M = bot perdedor
            if rank > 1000000 and pnl < -500000:
                is_bot = True
                bot_confidence += 30
                bot_reasons.append(f"🤖 Bot perdedor: Ranking #{rank:,}, PnL ${pnl/1e6:.1f}M, Vol ${total_volume/1e6:.1f}M")
            # Ranking >1M + ROI muy negativo + volumen >$5M
            elif rank > 1000000 and profit_factor < 0.85:
                bot_confidence += 25
                bot_reasons.append(f"⚠️ Patrón sospechoso: Ranking #{rank:,}, PF {profit_factor:.2f}, Vol ${total_volume/1e6:.1f}M")
        
        # ✅ INDICADOR 10 NUEVO: Ratio Volumen/PnL extremo (bots mueven mucho dinero con poco PnL)
        # Cuando total_trades == 0, usar señales indirectas
        if total_trades == 0 and total_volume > 10000000:
            pnl = d.get('pnl', 0)
            if pnl > 0:
                volume_pnl_ratio = total_volume / pnl
                
                # ✅ AJUSTADO: Thresholds más bajos basados en análisis de casos reales
                # Bots típicos: 8-15x, Humanos: 3-6x
                if volume_pnl_ratio > 15:
                    is_bot = True
                    bot_confidence += 45
                    bot_reasons.append(f"🤖 Ratio Vol/PnL extremo: {volume_pnl_ratio:.1f}x (patrón MM/bot)")
                elif volume_pnl_ratio > 10:  # Era >15, ahora >10 para capturar kch123 (10.1x)
                    is_bot = True
                    bot_confidence += 35
                    bot_reasons.append(f"🤖 Ratio Vol/PnL alto: {volume_pnl_ratio:.1f}x (patrón bot)")
                elif volume_pnl_ratio > 8:  # Era >12, ahora >8 para capturar swisstony (8.9x)
                    bot_confidence += 30
                    bot_reasons.append(f"⚠️ Ratio Vol/PnL elevado: {volume_pnl_ratio:.1f}x (posible bot)")
                elif volume_pnl_ratio > 6:
                    bot_confidence += 20
                    bot_reasons.append(f"⚡ Ratio Vol/PnL sospechoso: {volume_pnl_ratio:.1f}x (alta frecuencia)")
        
        # ✅ INDICADOR 11 NUEVO: Top ranking con PnL bajo relativo (volumen, no skill)
        # Top traders con poco PnL pero mucho volumen = bots de alta frecuencia
        if total_trades == 0:
            rank = d.get('rank', 999999)
            pnl = d.get('pnl', 0)
            
            # ✅ AJUSTADO: Thresholds más estrictos para Top 10
            # Top 10 con menos de $10M PnL pero más de $50M volumen = bot casi seguro
            if rank <= 10 and 0 < pnl < 10000000 and total_volume > 50000000:
                is_bot = True
                bot_confidence += 45
                bot_reasons.append(f"🤖 Top #{rank} con PnL ${pnl/1e6:.1f}M vs Vol ${total_volume/1e6:.1f}M (bot confirmado)")
            # Top 20 con menos de $5M PnL pero más de $20M volumen
            elif rank <= 20 and 0 < pnl < 5000000 and total_volume > 20000000:
                is_bot = True
                bot_confidence += 35
                bot_reasons.append(f"🤖 Top #{rank} con PnL ${pnl/1e6:.1f}M vs Vol ${total_volume/1e6:.1f}M (patrón bot)")
            # Top 50 con menos de $3M PnL pero más de $25M volumen
            elif rank <= 50 and 0 < pnl < 3000000 and total_volume > 25000000:
                bot_confidence += 30
                bot_reasons.append(f"⚠️ Top #{rank} con bajo PnL relativo (posible bot)")
            # Top 100 con menos de $2M PnL pero más de $30M volumen
            elif rank <= 100 and 0 < pnl < 2000000 and total_volume > 30000000:
                bot_confidence += 25
                bot_reasons.append(f"⚡ Ranking #{rank} con volumen desproporcionado (alta frecuencia)")
        
        # ✅ INDICADOR 12 NUEVO: Win Rate cercano a 50% + alto volumen (trading aleatorio/MM)
        # Win Rate 50-55% con volumen >$20M = posible bot
        if total_trades == 0 and total_volume > 20000000:
            win_rate = d.get('win_rate', 0)
            if 50 <= win_rate <= 55:
                bot_confidence += 25
                bot_reasons.append(f"⚠️ Win Rate {win_rate:.1f}% cercano a 50% con alto volumen (patrón bot)")
        
        # ✅ INDICADOR 13 NUEVO: Top ranking con ROI bajo (volumen, no skill)
        # Top 10 con ROI <10% = bot casi seguro
        if total_trades == 0:
            rank = d.get('rank', 999999)
            pnl = d.get('pnl', 0)
            
            if pnl > 0 and total_volume > 0:
                roi = (pnl / total_volume) * 100
                
                # Top 10 con ROI <10%
                if rank <= 10 and roi < 10:
                    is_bot = True
                    bot_confidence += 40
                    bot_reasons.append(f"🤖 Top #{rank} con ROI {roi:.1f}% (bot por volumen, no skill)")
                # Top 20 con ROI <12%
                elif rank <= 20 and roi < 12:
                    bot_confidence += 30
                    bot_reasons.append(f"⚠️ Top #{rank} con ROI {roi:.1f}% bajo (posible bot)")
        
        # ✅ INDICADOR 14 NUEVO: Profit Factor bajo + alto volumen
        # PF 1.1-1.3x con volumen >$30M = bot/MM
        if total_trades == 0 and total_volume > 30000000:
            profit_factor = d.get('profit_factor', 0)
            if 1.1 < profit_factor < 1.3:
                bot_confidence += 25
                bot_reasons.append(f"⚠️ Profit Factor {profit_factor:.2f}x bajo con alto volumen (patrón MM)")

        
        # Guardar resultados
        self.is_bot = is_bot
        self.bot_confidence = min(bot_confidence, 100)
        self.bot_reasons = bot_reasons
        
        # Agregar a red flags si es bot
        if is_bot:
            confidence_text = "ALTA" if bot_confidence > 70 else "MEDIA" if bot_confidence > 40 else "BAJA"
            self.red_flags.insert(0, f"🤖 POSIBLE BOT/MM (confianza {confidence_text}: {bot_confidence}%)")
        
        return is_bot

    def calculate_final_score(self):
        """Calcula score final y determina tier/grade"""
        total = (self.scores['profitability'] +
                self.scores['consistency'] +
                self.scores['risk_management'] +
                self.scores['experience'])

        self.scores['total'] = total

        # ✅ Determinar si es bot ANTES de asignar tier
        is_bot = self.detect_bot_behavior()
        
        # ⚠️ PENALIZACIÓN POR BOT
        if is_bot:
            # Penalización proporcional a la confianza
            penalty = int(self.bot_confidence * 0.3)  # Max 30 pts de penalización
            total = max(0, total - penalty)
            self.scores['total'] = total
            self.scores['bot_penalty'] = penalty
        
        # Determinar Tier
        if is_bot and self.bot_confidence > 80:
            # Bot de alta confianza = tier especial
            self.scores['tier'] = "🤖 BOT/MM"
            self.scores['reliability_grade'] = "N/A"
        elif total >= 85:
            self.scores['tier'] = "💎 DIAMOND"
            self.scores['reliability_grade'] = "A+"
        elif total >= 75:
            self.scores['tier'] = "🥇 GOLD"
            self.scores['reliability_grade'] = "A"
        elif total >= 65:
            self.scores['tier'] = "🥈 SILVER"
            self.scores['reliability_grade'] = "B+"
        elif total >= 55:
            self.scores['tier'] = "🥉 BRONZE"
            self.scores['reliability_grade'] = "B"
        elif total >= 45:
            self.scores['tier'] = "📊 STANDARD"
            self.scores['reliability_grade'] = "C"
        elif total >= 35:
            self.scores['tier'] = "⚠️ RISKY"
            self.scores['reliability_grade'] = "D"
        else:
            self.scores['tier'] = "💀 HIGH RISK"
            self.scores['reliability_grade'] = "F"

        return total

    def generate_recommendation(self):
        """Genera recomendación basada en el análisis"""
        total = self.scores['total']
        
        # ⚠️ ADVERTENCIA ESPECIAL PARA BOTS
        if getattr(self, 'is_bot', False):
            if self.bot_confidence > 80:
                return "🤖 BOT/MARKET MAKER DETECTADO - NO RECOMENDADO para copiar. Patrón de trading automatizado."
            elif self.bot_confidence > 50:
                return "⚠️ POSIBLE BOT - Alta sospecha de trading automatizado. NO copiar sin investigar."
            else:
                return "⚠️ ADVERTENCIA: Señales de trading automatizado detectadas. Verificar manualmente."
        
        # Recomendaciones normales
        if total >= 85:
            return "✅ ALTAMENTE CONFIABLE - Trader elite con historial excepcional. Ideal para seguir."
        elif total >= 75:
            return "✅ MUY CONFIABLE - Excelente balance riesgo/retorno. Recomendado para copiar."
        elif total >= 65:
            return "✅ CONFIABLE - Buen rendimiento consistente. Copiar con posiciones moderadas."
        elif total >= 55:
            return "⚠️ MODERADO - Resultados aceptables pero revisar red flags antes de copiar."
        elif total >= 45:
            return "⚠️ PRECAUCIÓN - Solo para seguimiento. No recomendado para copiar directamente."
        elif total >= 35:
            return "❌ NO RECOMENDADO - Alto riesgo o inconsistencia significativa."
        else:
            return "❌ EVITAR - Resultados negativos o perfil de alto riesgo."

    # --- GENERACIÓN DE REPORTE ---
    def generate_report(self):
        print("\n" + "="*70)
        print(f"🦈 POLYWHALE TRADER ANALYZER V5.0 - ADJUSTED")
        print(f"Analizando: {self.original_input}")
        print("="*70 + "\n")

        # Scraping de datos
        if not self.scrape_polymarketanalytics():
            print("\n❌ No se pudieron obtener datos de polymarketanalytics.com")
            print("   Verifica que la wallet/dirección sea correcta.")
            return

        self.setup_file_logging()

        # Calcular scores
        print("\n🔹 Calculando métricas de fiabilidad...")
        self.calculate_profitability_score()
        self.calculate_consistency_score()
        self.calculate_risk_management_score()
        self.calculate_experience_score()
        self.calculate_final_score()

        # === GENERAR REPORTE ===
        d = self.scraped_data
        sep = "═"*70

        self.report("\n" + sep)
        self.report(f"🦈 POLYWHALE TRADER ANALYSIS V5.0 - ADJUSTED")
        
        # Username (display original con guiones/caracteres especiales)
        if d.get('username'):
            self.report(f"Usuario: {d['username']}")
        
        # Wallet
        self.report(f"Wallet: {self.wallet}")
        
        # URL de Polymarket
        self.report(f"Perfil: https://polymarket.com/profile/{self.wallet}")
        
        self.report(f"Ranking Global: #{d.get('rank', 'N/A')}")
        self.report(f"Fuente: polymarketanalytics.com")
        self.report(sep)

        # Score principal
        grade = self.scores['reliability_grade']
        tier = self.scores['tier']
        total = self.scores['total']

        self.report(f"\n{'─'*70}")
        self.report(f"  📊 RELIABILITY SCORE: {total}/100  |  GRADE: {grade}  |  {tier}")
        self.report(f"{'─'*70}")

        self.report(f"\n🎯 RECOMENDACIÓN: {self.generate_recommendation()}")

        # Desglose de scores
        self.report(f"\n📈 DESGLOSE DE PUNTUACIÓN [Sistema Ajustado]")
        self.report(f"   ┌{'─'*50}┐")
        self.report(f"   │ {'Rentabilidad':<20} {self.scores['profitability']:>5}/35  {'█' * (self.scores['profitability']//3):<10} │")
        self.report(f"   │ {'Consistencia':<20} {self.scores['consistency']:>5}/25  {'█' * (self.scores['consistency']//2):<10} │")
        self.report(f"   │ {'Gestión de Riesgo':<20} {self.scores['risk_management']:>5}/20  {'█' * (self.scores['risk_management']//2):<10} │")
        self.report(f"   │ {'Experiencia':<20} {self.scores['experience']:>5}/20  {'█' * (self.scores['experience']//2):<10} │")
        self.report(f"   └{'─'*50}┘")

        # Nota sobre ajustes
        self.report(f"\n   ℹ️  Sistema ajustado: Rentabilidad +5pts, Gestión Riesgo -5pts")
        self.report(f"   ℹ️  Umbrales: ROI>25% (excelente), Win Rate>70% (excepcional)")

        # Métricas clave
        self.report(f"\n💰 MÉTRICAS FINANCIERAS")
        self.report(f"   • PnL Total:          ${d.get('pnl', 0):>12,.2f}")
        self.report(f"   • Total Ganado:       ${d.get('total_gains', 0):>12,.2f}")
        self.report(f"   • Total Perdido:      ${d.get('total_losses', 0):>12,.2f}")
        self.report(f"   • Valor en Posiciones: ${d.get('positions_value', 0):>12,.2f}")

        self.report(f"\n📊 INDICADORES DE RENDIMIENTO")
        self.report(f"   • Win Rate:           {d.get('win_rate', 0):>12.1f}%")
        self.report(f"   • Profit Factor:      {d.get('profit_factor', 0):>12.2f}x")
        self.report(f"   • ROI:                {getattr(self, 'roi', 0):>12.1f}%")
        if hasattr(self, 'win_loss_ratio'):
            self.report(f"   • Avg Win/Loss Ratio: {self.win_loss_ratio:>12.2f}x")

        self.report(f"\n🎲 ANÁLISIS DE RIESGO")
        self.report(f"   • Pérdida Máxima:     ${d.get('max_loss', 0):>12,.2f}")
        self.report(f"   • Ganancia Máxima:    ${d.get('max_win', 0):>12,.2f}")
        if hasattr(self, 'risk_reward_ratio'):
            self.report(f"   • PnL/MaxLoss Ratio:  {self.risk_reward_ratio:>12.2f}x")
        self.report(f"   • Volumen Operado:    ${getattr(self, 'total_traded', 0):>12,.2f}")
        
        # Métricas de frecuencia
        if d.get('total_trades'):
            self.report(f"\n📈 FRECUENCIA DE TRADING")
            self.report(f"   • Total Trades:       {d['total_trades']:>12,}")
            if d.get('markets_traded'):
                self.report(f"   • Markets Operados:   {d['markets_traded']:>12,}")
                trades_per_market = d['total_trades'] / d['markets_traded']
                self.report(f"   • Trades/Market:      {trades_per_market:>12.1f}")
                
                # Clasificación de frecuencia
                if trades_per_market > 50:
                    freq_class = "🤖 EXTREMADAMENTE ALTA (bot confirmado)"
                elif trades_per_market > 25:
                    freq_class = "⚠️ MUY ALTA (posible bot)"
                elif trades_per_market > 15:
                    freq_class = "⚡ ALTA (alta frecuencia)"
                elif trades_per_market > 10:
                    freq_class = "📊 MODERADA-ALTA"
                elif trades_per_market > 5:
                    freq_class = "✓ NORMAL"
                else:
                    freq_class = "✓ BAJA (swing trader)"
                
                self.report(f"   • Clasificación:      {freq_class}")
        else:
            # Advertencia cuando no se pueden verificar datos de frecuencia
            self.report(f"\n⚠️ ADVERTENCIA: FRECUENCIA NO VERIFICABLE")
            self.report(f"   No se pudieron capturar datos de total_trades/markets_traded.")
            self.report(f"   Revisar MANUALMENTE la actividad en tiempo real antes de copiar.")
            self.report(f"   Visita: https://polymarket.com/@{self.wallet}?tab=activity")

        # Fortalezas y Red Flags
        if self.strengths:
            self.report(f"\n✅ FORTALEZAS")
            for s in self.strengths:
                self.report(f"   {s}")

        if self.red_flags:
            self.report(f"\n⚠️ RED FLAGS")
            for r in self.red_flags:
                self.report(f"   {r}")

        # 🤖 ANÁLISIS DE BOT (si aplica)
        if getattr(self, 'is_bot', False):
            self.report(f"\n🤖 ANÁLISIS DE COMPORTAMIENTO BOT")
            self.report(f"   • Confianza Bot:      {self.bot_confidence}%")
            
            d = self.scraped_data
            if d.get('total_trades'):
                self.report(f"   • Total Trades:       {d['total_trades']:,}")
            if d.get('markets_traded'):
                self.report(f"   • Markets Traded:     {d['markets_traded']:,}")
                if d.get('total_trades'):
                    tpm = d['total_trades'] / d['markets_traded']
                    self.report(f"   • Trades/Market:      {tpm:.1f}")
            
            if self.bot_reasons:
                self.report(f"\n   Indicadores detectados:")
                for reason in self.bot_reasons:
                    self.report(f"   {reason}")
            
            if hasattr(self.scores, 'get') and self.scores.get('bot_penalty', 0) > 0:
                self.report(f"\n   ⚠️  Penalización aplicada: -{self.scores['bot_penalty']} puntos")

        # Badges
        badges = d.get('badges', [])
        if badges:
            self.report(f"\n🏅 BADGES")
            badge_names = {
                'pnl_100k': '💎 PnL > $100k',
                'pnl_10k': '💰 PnL > $10k',
                'veteran': '🎖️ Veterano (>1 año)',
                'high_winrate': '🎯 Win Rate > 67%',
                'good_winrate': '✓ Win Rate > 60%'
            }
            for b in badges:
                self.report(f"   {badge_names.get(b, b)}")

        # Especialización
        categories = d.get('categories', [])
        if categories:
            self.report(f"\n🧠 ESPECIALIZACIÓN POR CATEGORÍA")
            for cat in categories[:5]:
                pnl = cat['pnl']
                pnl_str = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
                self.report(f"   #{cat['rank']} {cat['name']:<20} {pnl_str:>12}")

        # Top trades
        wins = d.get('biggest_wins', [])
        losses = d.get('biggest_losses', [])

        if wins:
            self.report(f"\n🏆 TOP 5 MEJORES TRADES")
            for w in wins[:5]:
                self.report(f"   +${w['amount']:>10,.0f}  {w['market'][:45]}")

        if losses:
            self.report(f"\n💀 TOP 5 PEORES TRADES")
            for l in losses[:5]:
                self.report(f"   -${l['amount']:>10,.0f}  {l['market'][:45]}")

        # Veredicto final
        self.report(f"\n{'─'*70}")
        self.report(f"💡 VEREDICTO FINAL")

        total = self.scores['total']
        if total >= 75:
            verdict = "Este trader demuestra alta fiabilidad con métricas consistentes. Su historial sugiere que es capaz de generar ganancias sostenibles con riesgo controlado."
        elif total >= 60:
            verdict = "Trader con buen rendimiento general. Muestra capacidad de generar ganancias pero revisar las áreas de mejora antes de copiar grandes posiciones."
        elif total >= 45:
            verdict = "Resultados mixtos que requieren cautela. Considerar solo para seguimiento o posiciones pequeñas de prueba."
        else:
            verdict = "Perfil de alto riesgo o resultados negativos. No recomendado para copiar estrategias."

        self.report(f"   {verdict}")
        self.report(f"{'─'*70}")

        # Links de verificación
        self.report(f"\n🔗 VERIFICAR EN:")
        self.report(f"   Polymarket: https://polymarket.com/profile/{self.wallet}")
        self.report(f"   Analytics:  https://polymarketanalytics.com/traders/{self.wallet}")

        self.report("\n" + sep + "\n")
        self.close_log()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        inp = sys.argv[1]
    else:
        print("\n🦈 POLYWHALE TRADER ANALYZER V5.0 - ADJUSTED")
        print("Sistema de análisis de FIABILIDAD de traders de Polymarket")
        print("Datos verificados de polymarketanalytics.com")
        print("\n⚙️  Sistema ajustado: Rentabilidad 35pts (+5), Riesgo 20pts (-5)")
        print("⚙️  Umbrales suavizados para métricas clave\n")
        inp = input("👉 Address/Usuario/URL: ")

    analyzer = TraderAnalyzer(inp)
    analyzer.generate_report()