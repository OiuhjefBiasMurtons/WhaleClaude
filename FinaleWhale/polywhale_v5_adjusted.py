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
from whale_scorer import WhaleScorer

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


class TraderAnalyzer(WhaleScorer):
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
            data['username_clean'] = re.sub(r'[^\\w\\-]', '_', username_raw)
    except:
        pass
    
    # Fallback: buscar @username en el texto
    if 'username' not in data:
        username_match = re.search(r'@([A-Za-z0-9_-]+)', page_text)
        if username_match:
            data['username'] = username_match.group(1)
            data['username_clean'] = re.sub(r'[^\\w\\-]', '_', username_match.group(1))
    
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