#!/usr/bin/env python3
"""
Polymarket Gold All Markets Whale Detector v7.4.3
Basado en definitive_all_claude.py con filtros avanzados de señales (S1-S8),
whitelists/blacklists de traders, resolución de conflictos y warnings.

CHANGELOG:
  v7.4.3 (Mar 2026) — WHITELIST_TIER_OVERRIDE: bypass tier completo para traders validados:
    - NUEVO WHITELIST_TIER_OVERRIDE: traders con WR ≥ 60% y N ≥ 15 cuyo tier es snapshot
      inestable (el tier cambia entre capturas porque el scraper solo lo actualiza al capturar
      una apuesta que cumpla parámetros — entre capturas el trader opera y cambia de percentil).
      Para estos traders el tier del momento es ruido; el WR histórico es la señal real.
    - Bypass cubre BOT/MM y HIGH RISK en S2/S2B/S2C. SILVER y BRONZE siguen excluidos siempre
      (son tiers de calidad real, no artefactos de timing).
    - Entradas iniciales: elkmonkey (WR 68.4% NBA, N≥15) y 0x4924 (WR 61.1%, N≥15).
    - Criterio para entrar a WHITELIST_TIER_OVERRIDE: WR ≥ 60%, N ≥ 15 en categoría específica,
      tier documentado como inestable en producción.

  v7.4.2 (Mar 2026) — Eliminar WHITELIST_BOT_BYPASS (inefectivo en producción):
    - ELIMINADO WHITELIST_BOT_BYPASS: solo bypaseaba BOT/MM, pero los mismos traders llegan
      frecuentemente como HIGH RISK — el bypass nunca cubría ese caso.
    - Reemplazado en v7.4.3 por WHITELIST_TIER_OVERRIDE con cobertura completa.

  v7.4.1 (Mar 2026) — Validación cruzada con dataset Whales (N=483):
    - CRÍTICO S9 NHL COUNTER: DESACTIVADO. Dato Gold N=15 era ilusión estadística.
      Whales N=32 confirma WR exactamente 50% — coin flip sin edge. Revertido.
      No reimplementar hasta N≥40 combinado con WR≥65% sostenido.
    - IMPORTANTE S5-MMA: añadida exclusión HIGH RISK.
      Whales confirma HIGH RISK en MMA 0.60-0.70 WR 33% — destructor. Señal conservada
      para STANDARD/RISKY/SILVER/BRONZE (todo lo demás sin HIGH RISK ni BOT).
    - WHITELIST: añadido 0x4924... a WHITELIST_B (BOT/MM, WR 61.1%, capital $53K avg).
      elkmonkey ya estaba en WHITELIST_B (WR 68.4%, NBA). NOTA: su tier BOT/MM lo excluye
      de S2/S2B/S2C antes del check whitelist — boost solo aplica a S3/S6/S7.
      gmanas (WR 87.5%, N=8): monitorear, posible WHITELIST_A en 2-3 semanas (N≥15).
    - NUEVO WARNING: SILVER en NHL detectado — WR 26.7% (N=15, Whales) trampa confirmada.
    - HIPÓTESIS nuevas del cruce Whales/Gold:
      · "OTHER underdogs <30%": WR ~39% pero PnL +$5,584 (payout >3x). EV ≈ +30% ROI.
        Candidato señal nueva cuando se estructure correctamente con N suficiente.
      · CRYPTO × HIGH RISK FOLLOW: WR 71.4% en Whales. S4 ya tiene warning correcto.
        Evaluar como señal FOLLOW separada (requiere N≥15 en Gold específicamente).
      · SILVER × SOCCER FOLLOW: WR 63.6% en Whales. S5 suspendida. Documentar como
        excepción positiva en Soccer cuando S5 se reactive con restricción de tier.
    - CONFIRMADO: ESPORTS × RISKY ya cubierto por S7 (WR 76.9% consistente con S7 85.7%).
    - CONFIRMADO: BRONZE en crypto beneficia S4 COUNTER (WR follow 27.3% → counter 72.7%).
    - CONFIRMADO: sovereign2013 (WR 25%) y 432614799197 (WR 30.8%) en BLACKLIST. ✓

  v7.4 (Mar 2026) — Dataset Gold N=51+ resoluciones out-of-sample (15 días):
    - CRÍTICO S1 COUNTER: DESACTIVADO GLOBALMENTE. WR 35.3% (N=51) — peor que moneda al aire.
      Desglose: NBA 26% (N=11), Soccer 36% (N=16), NHL 57% (N=10), OTHER 13% (N=8).
      La premisa "counter HIGH RISK = win" refutada en 15 días out-of-sample.
      Única subzona prometedora: NHL 0.40-0.45 WR 83% (N=6) — hipótesis, N insuficiente.
      S1+ Consensus también desactivado (hereda la misma invalidación).
    - CRÍTICO S2 BRONZE: EXCLUIDO. WR 35.7% (N=14, PnL -$431) — tier más destructor en S2.
      Sin BRONZE: S2 WR sube 58.4%→63.5%, PnL +$593→+$1,023. STANDARD (WR 78%) y RISKY
      (WR 75%) cargan la señal. WR y N actualizados en consecuencia.
    - CRÍTICO S8 NHL: DESACTIVADO. WR 33.3% (N=6, PnL -$287) — sin edge.
      4 HIGH RISK (WR 50%) + 1 BRONZE (0W) + 1 NBA mal clasificado (0W).
    - IMPORTANTE S3: RESTRINGIDO A ESPORTS SIN HIGH RISK.
      S3 global WR 54.1% (N=37, PnL -$516). ESPORTS sin HR: WR 83.3% (N=6, +$212).
      NHL (WR 60%, N=10) y MMA añadidos a _S3_EXCLUDED. WR actualizado a 83.3%.
    - IMPORTANTE S2 umbral capital: $3K→$5K. Trades $3K-5K WR 50% (N=36, coin flip).
      $5K+ mejora: $5K-10K WR 69.2% (N=26), $10K-20K WR 61.5% (N=13), $20K+ WR 76.9% (N=13).
    - IMPORTANTE S2C SILVER: EXCLUIDO (WR 33%, N=3). RISKY boost añadido (WR 85.7%, N=7).
      Nicho boost en S2C: WR 80% (N=5, +$334) → confidence HIGH cuando is_nicho=True.
    - IMPORTANTE Nicho boost S2: S2-nicho WR 73.3% vs no-nicho 58.9% → boost a HIGH cuando nicho.
    - IMPORTANTE S2B WR actualizado: 0.60-0.70: 70.4%→78.6% (N=28). 0.70-0.80: 84.1%→84.6% (N=39).
      0.80-0.82: 80%→100% (N=4 — mantener con stake ×0.75 por payout reducido).
    - NUEVO Sucker bet warning en classify(): edge_pct < -3% → warning fuerte + confidence downgrade.
      3/3 trades con edge < -3% perdieron (WR 0%). Downgrade: HIGH→MEDIUM, MEDIUM→LOW.
    - BLACKLIST: añadidos VeryLucky888 (WR 20%, N=5), BWArmageddon (WR 0%, N=3), c4c4 (WR 29%, N=7).
    - HIPÓTESIS S5-MMA actualizada: N=3→N=6. WR 100% (6/6 wins UFC 0.60-0.70 BUY).
      Hipótesis más prometedora del dataset. Implementar cuando N≥15.
    - Señales +EV (Scenario B/C sin destructoras): WR 68.9% / PnL +$3,928 vs total 58.8% / +$1,657.
      Las señales cortadas (S1, S1B, S3 genérico, S5, S8) consumían $2,271 de profit.
    - NUEVO S9: Counter HIGH RISK en NHL (WR counter 73.3%, N=15, precio 0.30-0.80).
      HIGH RISK en NHL WR follow 26.7% (N=15, -$745) — la peor combinación del heatmap.
      Señal inversa simétrica de S8. Confidence MEDIUM (N=15 exactamente en umbral mínimo).
    - NUEVO S5-MMA: Follow MMA 0.60-0.70 (WR 100%, N=6, +$355). Activado con cautela.
      N inferior al umbral N≥15. Stake mínimo (1%), confidence LOW. Excluye BOT/MM.
      Monitorear: subir a MEDIUM cuando N≥15 y WR≥80% sostenido.
    - CONFIRMADO: Nicho boost S2/S2C ya implementado. Dataset confirma WR 73.3% nicho vs 58.9%.
    - CONFIRMADO: Blacklist VeryLucky888 (20% WR) y c4c4 (28.6% WR) — dataset los valida.

  v7.1 (Mar 2026):
    - CORREGIDO Gap 1: S2/S2B/S2C solo activan con side==BUY. SELL NBA WR 36.1% — excluido.
    - CORREGIDO Gap 2: S8 excluye BOT/MM (WR 0%, N=5) y SILVER (WR 25%). Solo BUY.
    - CORREGIDO Gap 4: TENNIS añadido a _S3_EXCLUDED (WR 41.7%, PnL -1,451 — destructor).
    - NO implementado Gap 3 (Crypto >0.65 N=12 insuficiente).
    - NO implementado Gap 7 ($3k→$5k requiere análisis previo de señales en ese rango).
    - HIPÓTESIS Gap 5: Politics <0.30 WR 63% (N=27) — pendiente validación.

  v7.0 (Mar 2026):
    - IMPLEMENTADO S8: Follow NHL 0.60-0.70, WR ~86%, N≥15, conf=MEDIUM, stake 2%.
    - CORREGIDO S2B: hard IGNORE si poly_price > 0.82 (EV negativo con WR 80%).
      Rango activo reducido de 0.60-0.85 a 0.60-0.82.
    - ACTUALIZADO S5: WR 85.7% → 73.0% (N~20). ROI esperado en Telegram corregido.
    - HIPÓTESIS S9: Counter MMA RISKY 0.50-0.70 (N~8-10). Pendiente N≥15.

  v6.1 (Mar 2026):
    - ACTUALIZADO S6: WR 81.8% → 66.7% (N=24). Confianza MEDIUM → LOW.
    - ACTUALIZADO S7: WR 84.6% → 85.7% (N=14). Confianza LOW → MEDIUM (cruzó N=15).
    - ACTUALIZADO S2B: WR 76.1%/85.0% → 80.0% en ambas subzonas (N=60 y N=30).
    - ACTUALIZADO S1B: WR 87.0% → 83.9% (N=31). Sigue siendo señal sólida.
    - ACTUALIZADO S2: WR 62.5% (N=72). Leve baja, sigue válida.
    - ACTUALIZADO S2C: WR 67.6% → 68.3% (N=41). Consistente.
    - ACTUALIZADO S5: WR 85.7% → 75.0% (N=20). Sigue válida.
    - HIPÓTESIS S8: Follow NHL 0.60-0.70 WR 87.5% (N=8). Pendiente N≥15.
    - WHITELIST A: añadidos GetaLife (HIGH RISK NBA, WR 83.3%, N=6) y jackmala (HIGH RISK NBA, WR 80%, N=5).
    - WHITELIST B: swisstony eliminado (WR 50%, PnL -$237, ya no califica).
    - BLACKLIST: añadidos hotdogcat (HIGH RISK NBA, WR 28.6%) y Sensei2 (WR 0%, Soccer+NBA).
    - STAKE: FOLLOW + whitelist (A o B) → ×1.25 adicional.
    - STAKE: COUNTER + blacklist → ×1.25 adicional.

  v5.0 (Mar 2026):
    - CORREGIDO Bug 3: MMA ahora se detecta ANTES que Soccer en _detect_category.
      UFC Fight Night ya no activa S1B falsamente (7 trades UFC tenían WR 42.9%).
    - ACTUALIZADO S1: ahora NBA-aware.
      S1-NBA 0.40-0.44: conf=HIGH, WR 92.3% (N=13).
      S1-NBA <0.40: conf=MEDIUM, WR ~70%.
      S1-OTHER 0.40-0.44: conf=MEDIUM, WR ~72%.
      S1-OTHER <0.40: conf=LOW, WR 60%.
    - CORREGIDO S2: añadida exclusión BOT/MM (WR 30.8%, PnL -595 en NBA 0.50-0.60).
      WR actualizado de 72% → 64% (N=50 excl. BOT). S1B WR actualizado de 72% → 75%.
    - ACTUALIZADO S2B: conf LOW → MEDIUM, WR 69.6% → 76.5%, stake 0.5x → 1x.
      También excluye BOT/MM.
    - AÑADIDO S2C: Follow NBA 0.45-0.50 excl HIGH RISK/BOT (WR ~60%, N=49, conf=MEDIUM).
      La "zona muerta" 0.45-0.50 no existe para NBA — solo para otras categorías.
    - AÑADIDO S6: Counter ESPORTS precio <0.50 (WR 85.7%, N=14, conf=MEDIUM, stake 0.5x).
      Misma lógica que S1: ballenas comprando underdog en Esports = mala señal.
    - DOCUMENTADO S7 (hipótesis): Follow ESPORTS 0.60-0.70 WR 100% pero N=7. Pendiente n≥15.
    - Warning "zona muerta" ahora excluye NBA (NBA tiene S2C en ese rango).
    - Resolución de conflictos: añadido CASO S1+S6 (ESPORTS HIGH RISK <0.45 → S6 prevalece).

  v4.0 (Feb 2026):
    - AÑADIDO S1B: Counter Soccer cualquier tier precio <0.40 (WR 75.0%, N=24)
    - AÑADIDO S2: exclusión HIGH RISK en NBA (WR 49.4%, PnL -818 — destruye capital)
    - DIVIDIDO S2 en S2 + S2B:
        S2  = NBA 0.50-0.60, conf=MEDIUM, WR 72% (zona core, datos sólidos)
        S2B = NBA 0.60-0.80, conf=LOW, WR 69.6%, stake 0.5x (zona extendida, pendiente más datos)
    - CORREGIDO S3: excluir Soccer y Crypto del filtro nicho (WR 43.5% y 33.3% resp.)
    - INVERTIDO S5: era COUNTER Soccer SILVER 0.50-0.65 → ahora FOLLOW Soccer 0.60-0.80
      excl. GOLD/RISKY (WR 75.9%, N=29). El dato original estaba al revés.
    - HIPÓTESIS S6: Follow Soccer nicho GOLD/SILVER ≥0.65 (WR 80%, N=5). No implementada
      hasta n≥20. Documentada como hipótesis pendiente de validación.
    - DESCARTADO: edge_pct alto como señal positiva (invertido: edge>5% → WR 20%)
    - DESCARTADO: Soccer como mercado sin filtros — ahora tiene reglas específicas S1B/S5
    - DESCARTADO: Nicho universal — solo Esports y otras categorías no-core tienen valor
  v3.0 (Feb 2026):
    - ELIMINADO: edge_pct > 0 como bonus (refutado por datos: WR 30.6%)
    - ELIMINADO: tier blacklist para S2 en NBA (HIGH RISK/RISKY ganan más en NBA 0.50-0.60)
    - ELIMINADO: regla counter por peor WR trader (refutado por caso Spurs/Pistons)
    - ELIMINADO: jerarquía de capital como predictor de WR
    - ACTUALIZADO: S1 tiene dos sub-zonas de WR diferente (88.2% en 0.40-0.44, 71.4% en <0.40)
    - ACTUALIZADO: S5 WR corregido a 66.7% (N=6)
    - ACTUALIZADO: S4 solo activa automáticamente en Up/Down intraday
    - ACTUALIZADO: resolución de conflictos — dos HIGH RISK opuestos siempre IGNORAR
    - AÑADIDO: TRADER_MIN_TRADES_FOR_SIGNAL = 15 como umbral mínimo para WR confiable
    - AÑADIDO: swisstony a WHITELIST_B (WR 71.4%, N=7)
    - AÑADIDO: synnet baja de WHITELIST_A a WHITELIST_B (N=1, insuficiente)
    - AÑADIDO: warnings para zona muerta 0.45-0.49, precio >0.75, edge_pct>0
  v7.3 (Mar 2026) — Dataset Gold 409 trades (323 resueltos):
    - CRÍTICO S1-NBA: DESACTIVADO. WR 33.3% (N=12) — señal rota, perdiendo consistentemente.
      S1 sigue activo para todas las demás categorías (non-NBA). Reactivar cuando N≥20 y WR≥60%.
    - CRÍTICO S1B Soccer: SUSPENDIDO. WR 52.9% total (N=17); descomposición por rango:
      <0.30: WR 33%, 0.30-0.35: WR 50%, 0.35-0.40: WR 31%. Sin edge positivo en ningún rango.
      Degradado a HIPÓTESIS — reactivar cuando N≥30 adicionales con WR≥65%.
    - CRÍTICO S5 Soccer: SUSPENDIDO. WR 38.1% (N=21) — reversión total desde WR 73%.
      Causa probable: contaminación MMA/Esports + evento Manchester City (7 losses consecutivos).
      Reactivar cuando N≥30 limpio (Soccer puro, sin BOT/MM del mismo mercado perdedor).
    - IMPORTANTE S2B: zonas diferenciadas por datos.
      0.60-0.70: WR 70.4% (N=27) → conf MEDIUM. 0.70-0.82: WR 84.1% (N=44) → conf HIGH.
    - IMPORTANTE S2: excluir SILVER (WR 25% confirmado — pendiente estaba en v7.2).
    - IMPORTANTE S2C: excluir STANDARD (tier sin edge en zona 0.45-0.50 NBA).
    - IMPORTANTE S3: añadido "OTHER" a _S3_EXCLUDED (WR 30% en OTHER — sin edge real).
    - IMPORTANTE S4 Crypto: restringido a precio ≥ 0.60 (zona baja sin edge confirmado).
    - IMPORTANTE S6 Esports: restringido a 0.40-0.50 (límite inferior añadido).
    - IMPORTANTE S7 Esports: excluir HIGH RISK (tier con WR inferior al average de señal).
    - NO cambiado: S2B excluye HIGH RISK ya desde v7.2. S3 ya excluye CRYPTO.
    - NO cambiado: S8 NHL (N=2 en nuevo dataset — insuficiente para revisar parámetros).
    - HIPÓTESIS nueva: S5-MMA Follow 0.60-0.80 (WR 100% N=3). Documentar, N mínimo ≥15.

  v7.2 (Mar 2026):
    - CRÍTICO S5: añadidos filtros 'HIGH RISK' not in tier + 'BOT' not in tier.
      HR destruye S5 (WR 40%, N=15). BOT también (WR 20%, N=5). Contaminación lyon (ver abajo).
      Señal limpia tras filtros; suspender si N<10 en próximo análisis.
    - CRÍTICO S3: añadido filtro 'HIGH RISK' not in tier.
      S3+HR WR 0%→sin HR WR 85.7% (N=7). Cambio más dramático del análisis.
    - CRÍTICO S1B: umbral reducido de <0.40 a <0.35.
      Subrango 0.35-0.40 colapsa a WR 20% (N=10). Solo <0.35 mantiene WR 80% (N=5).
      WR ajustado de 87.0% a 80.0% (refleja solo el subrango activo).
    - BUG FIX: 'lyon' eliminado de SOCCER_KEYWORDS.
      Equipo de LoL llamado LYON activaba S5 con partidos de League of Legends.
    - swisstony añadido a BLACKLIST (N=8, WR 37.5%, PnL -190). Sus 5 trades en S5 WR 20%.
      Ya había sido eliminado de WHITELIST_B en v6.1 — ahora en BLACKLIST.
    - PENDIENTE: S2 SILVER (WR 25% N=4 — observar hasta N≥10). [RESUELTO en v7.3]
    - PENDIENTE: Umbral mínimo $3k→$5k (analizar impacto antes de implementar).

"""

import re
from unittest import signals

import requests
import json
import time
import signal as signal_module
import sys
import logging
import os
import csv
import argparse
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
TELEGRAM_TOKEN = os.getenv('API_GOLD')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')
TELEGRAM_ENABLED = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)

# Configuración de Supabase (Gold usa sus propias credenciales)
SUPABASE_URL = os.getenv('SUPA_GOLD_URL')
SUPABASE_KEY = os.getenv('SUPA_GOLD_KEY')
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)

# --- CONFIGURACIÓN ---
GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
LIMIT_TRADES = 1000
INTERVALO_NORMAL = 3
MAX_CACHE_SIZE = 5000
VENTANA_TIEMPO = 1800  # 30 minutos

# Cache de tiers persistente entre sesiones (opciones 1+2)
TIER_CACHE_PATH = Path("trades_live/tier_cache.json")
TIER_CACHE_TTL_H = 48  # horas antes de considerar un tier "caducado"
DEFERRED_TIMEOUT_S = 90  # segundos máx. para esperar tier (scraper con 3 retries puede tardar ~60-80s)

BANKROLL_PATH = Path("trades_live/bankroll.json")
DEFAULT_BANKROLL = 500.0  # bankroll inicial por defecto

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

# ============================================================================
# ASCII ART BANNERS — FOLLOW / COUNTER
# ============================================================================

_BANNER_FOLLOW = """
╔══════════════════════════════════════════════════╗
║  ███████╗ ██████╗ ██╗     ██╗      ██████╗ ██╗  ║
║  ██╔════╝██╔═══██╗██║     ██║     ██╔═══██╗██║  ║
║  █████╗  ██║   ██║██║     ██║     ██║   ██║██║  ║
║  ██╔══╝  ██║   ██║██║     ██║     ██║   ██║╚═╝  ║
║  ██║     ╚██████╔╝███████╗███████╗╚██████╔╝██╗  ║
║  ╚═╝      ╚═════╝ ╚══════╝╚══════╝ ╚═════╝ ╚═╝  ║
╚══════════════════════════════════════════════════╝"""

_BANNER_COUNTER = """
╔══════════════════════════════════════════════════════════════╗
║   ██████╗ ██████╗ ██╗   ██╗███╗  ██╗████████╗███████╗██████╗ ║
║  ██╔════╝██╔═══██╗██║   ██║████╗ ██║╚══██╔══╝██╔════╝██╔══██╗║
║  ██║     ██║   ██║██║   ██║██╔██╗██║   ██║   █████╗  ██████╔╝║
║  ██║     ██║   ██║██║   ██║██║╚████║   ██║   ██╔══╝  ██╔══██╗║
║  ╚██████╗╚██████╔╝╚██████╔╝██║ ╚███║   ██║   ███████╗██║  ██║║
║   ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝║
╚══════════════════════════════════════════════════════════════╝"""

_BANNER_IGNORE = """
╔═══════════════════════════════╗
║  ██╗ ██████╗ ███╗  ██╗██████╗ ║
║  ██║██╔════╝ ████╗ ██║██╔══██╗║
║  ██║██║  ███╗██╔██╗██║██████╔╝║
║  ██║██║   ██║██║╚████║██╔══██╗║
║  ██║╚██████╔╝██║ ╚███║██║  ██║║
║  ╚═╝ ╚═════╝ ╚═╝  ╚══╝╚═╝  ╚═╝║
╚═══════════════════════════════╝"""

_BANNERS = {
    'FOLLOW':  _BANNER_FOLLOW,
    'COUNTER': _BANNER_COUNTER,
    'IGNORE':  _BANNER_IGNORE,
}

# Para Telegram (dentro de <pre>, sin emojis)
_TG_BANNER_FOLLOW = (
    "<pre>╔══════════════════════════════════╗\n"
    "║  ▶▶  F  O  L  L  O  W  ◀◀      ║\n"
    "╚══════════════════════════════════╝</pre>"
)
_TG_BANNER_COUNTER = (
    "<pre>╔══════════════════════════════════╗\n"
    "║  ◀◀  C  O  U  N  T  E  R  ▶▶   ║\n"
    "╚══════════════════════════════════╝</pre>"
)

# ============================================================================
# CLASIFICADOR DE SEÑALES v3.0
# ============================================================================

# Listas de traders
WHITELIST_A = ['hioa', 'KeyTransporter', 'HOCHI', 'GetaLife', 'jackmala']
WHITELIST_B = ['theyseemeloosintheyhatin', 'qqzhi4527', 'elkmonkey', 'gmanas', 'TheOnlyHuman', 'synnet', 'takeormake', 'joosangyoo', 'statwC00KS',
               '0x4924',   # BOT/MM, WR 61.1%, capital $53K avg — confirmado whitelist Whales
               # gmanas: WR 87.5% N=8 — monitorear, posible WHITELIST_A cuando N≥15.
               ]

# Traders con WR validado (≥60%, N≥15) cuyo tier es snapshot inestable.
# El tier cambia entre capturas porque el scraper solo actualiza al capturar una apuesta
# que cumpla parámetros. Entre capturas, el trader opera y modifica su percentil.
# Para estos traders el tier del momento es ruido; el WR histórico es la señal real.
# Efecto: bypasea BOT/MM y HIGH RISK en S2/S2B/S2C. SILVER y BRONZE NO se bypasean.
# Criterio de entrada: WR ≥ 60%, N ≥ 15, tier documentado como inestable en producción.
# Si están aquí deben estar también en WHITELIST_B para el stake boost (×1.25).
WHITELIST_TIER_OVERRIDE = [
    'elkmonkey',  # WR 68.4% NBA, N≥15 — tier oscila BOT/MM ↔ HIGH RISK según captura
    '0x4924',     # WR 61.1% NBA, capital $53K avg — ídem
]

BLACKLIST = ['sovereign2013', '0xFc2F4f50...', 'bossoskil1', 'BITCOINTO500K', '432614799197', 'xdoors', 'hotdogcat', 'Sensei2', 'swisstony',
             'VeryLucky888',    # WR 20% N=5 — candidato blacklist confirmado v7.4
             'BWArmageddon',    # WR 0% N=3 — candidato blacklist confirmado v7.4
             'c4c4',            # WR 29% N=7, BOT/MM — candidato blacklist confirmado v7.4
             ]
TRADER_MIN_TRADES_FOR_SIGNAL = 15

# Keywords para detección de categorías
NBA_KEYWORDS = [
    'nba', 'ncaa', 'cougars', 'cyclones', 'wolverines', 'boilermakers', 'cornhuskers',
    'hawkeyes', 'wildcats', 'tigers', 'cowboys', 'buffaloes', 'owls',
    'mean green', 'seminoles', 'tar heels', 'hoosiers', 'gamecocks',
    'bulldogs', 'longhorns', 'sooners', 'jayhawks', 'ncaab',
    'college basketball', 'lakers', 'celtics', 'bulls', 'warriors', 'nets', 'knicks',
    'bucks', 'heat', 'suns', 'nuggets', 'grizzlies', 'jazz', 'spurs',
    'pistons', 'pacers', 'wizards', 'hawks', 'hornets', 'cavaliers',
    'magic', 'raptors', 'thunder', 'clippers', 'kings', 'rockets',
    'mavericks', 'timberwolves', 'blazers', 'pelicans', '76ers', 'sixers',
]

NHL_KEYWORDS = [
    'nhl', 'oilers', 'ducks', 'bruins', 'rangers', 'penguins',
    'maple leafs', 'canadiens', 'flames', 'canucks', 'sharks',
    'golden knights', 'avalanche', 'blues', 'blackhawks', 'red wings',
    'hurricanes', 'panthers', 'lightning', 'capitals', 'flyers',
    'devils', 'islanders', 'sabres', 'senators', 'predators',
    'stars', 'wild ', 'jets', 'kraken',
]
CRICKET_KEYWORDS = ['cricket', 't20 world cup', 'ipl', 'test match', 'odi', 't20']

SOCCER_KEYWORDS = [
    'fc ', ' fc', 'barcelona', 'madrid', 'bayern', 'dortmund', 'juventus',
    'inter', 'milan', 'psg', 'lille', 'chelsea', 'arsenal',  # 'lyon' eliminado v7.2: LoL team LYON activaba S5 erróneamente
    'liverpool', 'tottenham', 'manchester', 'premier', 'liga', 'serie a',
    'bundesliga', 'ligue', 'milan', 'roma', 'napoli', 'atletico', 'sevilla', 'valencia',
    'real sociedad', 'ajax', 'porto', 'benfica', 'feyenoord', 'celtic', 'rangers', 'galatasaray',
    'fenerbahce', 'besiktas', 'marseille', 'monaco', 'olympiacos', 'anderlecht', 'brugge',
    'shakhtar', 'dynamo kiev', 'dortmund', 'leipzig', 'wolfsburg', 'frankfurt', 'leverkusen', 'schalke', 'ucl', 'uel',
]

CRYPTO_KEYWORDS = [
    'bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'solana', 'sol',
    'dogecoin', 'doge', 'xrp', 'cardano', 'ada',
]

ESPORTS_KEYWORDS = [
    'esports', 'league of legends', 'dota', 'csgo', 'cs2', 'valorant', 'dota2', 'counter-strike',     'lol:', 'lck', 'lec', 'lpl', 'bnk fearx', 'gen.g', 'dplus kia',
    'kt rolster', 'natus vincere', 'giantx', 'team heretics', 'karmine corp',
    'team vitality', 'bo3', 'bo5', 'game winner', 'game handicap',
    'counter-strike:', 'cs2:', 'pgl', 'furia', 'parivision', 'mouz',
    'dreamleague', 'aurora', 'tundra', 'liquid', 'team spirit', 'mouz',
    ]

TENNIS_KEYWORDS = ['tennis', 'atp', 'wta', 'grand slam', 'wimbledon', 'roland garros']
MMA_KEYWORDS = [
    'ufc', 'mma', 'boxing', 'bellator', 'one fc', 'fight night',
    'flyweight', 'bantamweight', 'featherweight', 'lightweight',
    'welterweight', 'middleweight', 'heavyweight', 'knockout', ' ko ',
]


def _detect_category(market_title: str) -> str:
    """Detecta la categoría del mercado basándose en el título."""
    title_lower = market_title.lower()

    # NHL antes que NBA (evita que 'blues', 'predators', etc. caigan al fallback vs+o/u NBA)
    if any(kw in title_lower for kw in NHL_KEYWORDS):
        return "NHL"

    # NBA primero (más específico que "sports" genérico)
    if any(kw in title_lower for kw in NBA_KEYWORDS):
        return "NBA"

    if any(kw in title_lower for kw in CRYPTO_KEYWORDS):
        return "CRYPTO"

    # MMA antes de Soccer — evita que "UFC Fight Night" active S1B por falso positivo Soccer
    if any(kw in title_lower for kw in MMA_KEYWORDS):
        return "MMA"

    if any(kw in title_lower for kw in SOCCER_KEYWORDS):
        return "SOCCER"

    if any(kw in title_lower for kw in ESPORTS_KEYWORDS):
        return "ESPORTS"

    if any(kw in title_lower for kw in TENNIS_KEYWORDS):
        return "TENNIS"

    # Fallback 'vs' solo si tiene indicadores típicos de mercados NBA
    # No usar para cualquier "vs" genérico (evita MMA/boxeo activando S2)
    nba_vs_indicators = ['spread:', 'o/u', 'over/under', 'moneyline']
    if (' vs' in title_lower or ' vs.' in title_lower):
        if any(ind in title_lower for ind in nba_vs_indicators):
            return "NBA"
        # "X vs Y" sin contexto claro → OTHER, no NBA
        return "OTHER"

    return "OTHER"


def _is_crypto_intraday(market_title: str) -> bool:
    """Detecta si es mercado crypto intraday (Up/Down)."""
    return 'up or down' in market_title.lower()


# ============================================================================
# SISTEMA DE STAKE KELLY FRACCIONADO
# ============================================================================

# Stake base % por (signal_id, confidence). Fallback por confidence si no está en tabla.
_STAKE_PCT: dict[tuple, int] = {
    ('S1',           'HIGH'):   4,   # S1-NBA 0.40-0.44
    ('S1B',          'HIGH'):   4,   # S1B Soccer [SUSPENDIDA v7.3]
    ('S1+',          'HIGH'):   4,   # S1+ consenso
    ('S2B',          'HIGH'):   3,   # S2B NBA zona 0.70-0.82
    ('S2B',          'MEDIUM'): 2,   # S2B NBA zona 0.60-0.70
    ('S2',           'HIGH'):   3,   # S2+RISKY (boost a HIGH)
    ('S2+',          'HIGH'):   3,   # S2+ consenso
    ('S1',           'MEDIUM'): 2,   # S1-NBA <0.40 y S1-OTHER
    ('S2',           'MEDIUM'): 2,   # S2 NBA core
    ('S2C',          'MEDIUM'): 2,   # S2C NBA
    ('S4',           'MEDIUM'): 2,   # S4 Crypto intraday
    ('S5',           'MEDIUM'): 2,   # S5 Soccer [SUSPENDIDA v7.3]
    ('S6',           'LOW'):    1,   # S6 Counter ESPORTS (v6.1: bajó de MEDIUM a LOW)
    ('S1',           'LOW'):    1,   # S1-OTHER
    ('S1-MMA-RISKY', 'LOW'):    1,   # S1-MMA-RISKY (N=5, muestra pequeña)
    ('S3',           'LOW'):    1,   # S3 Nicho
    ('S7',           'MEDIUM'): 2,   # S7 Follow ESPORTS (v6.1: subió de LOW a MEDIUM)
    # ('S8',         'MEDIUM'): 2,   # S8 DESACTIVADO v7.4 (WR 33.3% N=6)
    # ('S9',         'MEDIUM'): 2,   # S9 DESACTIVADO v7.4.1 (Whales N=32 WR 50% — ilusión estadística)
    ('S5-MMA',       'LOW'):    1,   # S5-MMA Follow MMA 0.60-0.70 (WR 100%, N=6 — stake mínimo)
}
_STAKE_DEFAULT = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}


def calcular_stake(
    signal_id: str,
    confidence: str,
    bankroll: float,
    poly_price: float = 0.0,
    is_nicho: bool = False,
    is_whitelist_a: bool = False,
    is_whitelist_b: bool = False,
    is_blacklist: bool = False,
    action: str = "",
    is_deferred: bool = False,
) -> tuple[float, float, list[str]]:
    """
    Calcula el stake sugerido en USD usando Kelly fraccionado.

    Returns:
        (stake_usd_redondeado, stake_pct_display, lista_modificadores)
    """
    base_pct = _STAKE_PCT.get((signal_id, confidence), _STAKE_DEFAULT.get(confidence, 1))
    stake_pct = base_pct / 100.0
    mods: list[str] = []

    # Drawdown: bankroll < $400 → todos los stakes a la mitad
    if bankroll < 400:
        stake_pct *= 0.5
        mods.append("drawdown <$400 ×0.5")

    # Whitelist A → +50%
    if is_whitelist_a:
        stake_pct *= 1.5
        mods.append("Whitelist A ×1.5")

    # Whitelist B FOLLOW → +25% (solo si NO es A, evitar doble boost)
    elif action == "FOLLOW" and is_whitelist_b:
        stake_pct *= 1.25
        mods.append("FOLLOW+Whitelist B ×1.25")

    # COUNTER + blacklist → +25% (independiente de whitelist)
    if action == "COUNTER" and is_blacklist:
        stake_pct *= 1.25
        mods.append("COUNTER+Blacklist ×1.25")

    # Mercado nicho → +25%
    if is_nicho:
        stake_pct *= 1.25
        mods.append("nicho ×1.25")

    # S2B subzona 0.80-0.85 → payout bajo, reducir
    if signal_id == 'S2B' and poly_price >= 0.80:
        stake_pct *= 0.75
        mods.append("subzona 0.80+ ×0.75")
    elif poly_price > 0.75:
        # Precio alto pero no S2B 0.80+ (evitar doble penalización)
        stake_pct *= 0.75
        mods.append("precio >0.75 ×0.75")

    # Deferred → timing tardío, precio puede haber movido
    if is_deferred:
        stake_pct *= 0.5
        mods.append("deferred ×0.5")

    stake_usd = bankroll * stake_pct
    # Redondeo dinámico según bankroll — evita que confianzas distintas colapsen al mismo valor
    if bankroll < 300:
        step, min_stake = 1, 7.0
    elif bankroll < 600:
        step, min_stake = 2, 7.0
    elif bankroll < 1000:
        step, min_stake = 5, 7.0
    else:
        step, min_stake = 10, 10.0
    stake_usd_rounded = max(min_stake, round(stake_usd / step) * step)
    pct_display = round(stake_pct * 100, 1)

    return stake_usd_rounded, pct_display, mods


def classify(
    market_title: str,
    tier: str,
    poly_price: float,
    is_nicho: bool = False,
    valor_usd: float = 5000,
    side: str = "BUY",
    display_name: str = "Unknown",
    edge_pct: float = 0.0,
    opposite_tier: str = "",
) -> dict:
    """
    Clasifica una señal de ballena y determina la acción recomendada.

    Args:
        market_title: Título del mercado en Polymarket
        tier: Tier del trader (ej: "💀 HIGH RISK", "🥈 SILVER", etc.)
        poly_price: Precio actual en Polymarket (0.0-1.0)
        is_nicho: Si el mercado es nicho (alta concentración)
        valor_usd: Valor del trade en USD
        side: "BUY" o "SELL"
        display_name: Nombre del trader
        edge_pct: Edge porcentual vs Pinnacle (convención sports_edge_detector: pinnacle-poly)
        opposite_tier: Tier de una ballena del lado contrario (para conflicto HIGH RISK)

    Returns:
        dict con action, signal_id, confidence, win_rate_hist, expected_roi,
             payout_mult, reasoning, warnings, category
    """
    result = {
        "action": "IGNORE",
        "signal_id": "NONE",
        "confidence": "—",
        "win_rate_hist": 0.0,
        "expected_roi": 0.0,
        "payout_mult": 0.0,
        "reasoning": [],
        "warnings": [],
        "category": "OTHER",
    }

    tier_upper = tier.upper()
    # FIX 8: Normalizar case para comparaciones con listas
    display_name_lower = display_name.lower()
    whitelist_a_lower = [w.lower() for w in WHITELIST_A]
    whitelist_b_lower = [w.lower() for w in WHITELIST_B]
    blacklist_lower = [b.lower() for b in BLACKLIST]
    # Tier override: WR histórico supera al tier snapshot (inestable por timing de captura)
    _is_tier_override = display_name_lower in [w.lower() for w in WHITELIST_TIER_OVERRIDE]

    category = _detect_category(market_title)
    result["category"] = category

    # Calcular payout
    if poly_price > 0:
        result["payout_mult"] = round((1.0 / poly_price) - 1, 2)

    # --- WARNINGS GLOBALES ---

    # FIX 2: edge_pct llega de sports_edge_detector con convención (pinnacle - poly)*100
    # edge_pct < 0 = poly más caro que Pinnacle = sucker bet.
    # v7.4: cuando edge < -3%, warning fuerte + downgrade de confidence confirmado.
    # Dataset: 3/3 trades con edge < -3% perdieron (WR 0%). Patrón claro aunque N pequeño.
    if edge_pct < -3.0:
        result["warnings"].append(
            f"⚠️ SUCKER BET: poly está {abs(edge_pct):.1f}% MÁS CARO que Pinnacle. "
            f"3/3 trades con edge < -3% perdieron (WR 0%). Downgrade confidence aplicado."
        )

    # Warning: precio > 0.85
    if poly_price > 0.85:
        result["warnings"].append(
            "Precio >0.85: WR bueno (78.6%) pero payout destruye EV. "
            f"$10 a {poly_price:.2f} gana solo ${(1/poly_price - 1)*10:.2f}."
        )

    # Warning: zona 0.45-0.49 (solo non-NBA — NBA tiene S2C en este rango)
    if 0.45 <= poly_price <= 0.49 and category != "NBA":
        result["warnings"].append(
            "Precio en zona 0.45-0.49: sin señal activa para esta categoría. No activa S1 ni S2."
        )

    # Warning: SILVER en NHL — trampa confirmada (Whales N=15, WR 26.7%)
    if category == "NHL" and 'SILVER' in tier_upper:
        result["warnings"].append(
            "⚠️ SILVER en NHL: WR 26.7% (N=15, Whales) — trampa confirmada. "
            "No hay señal activa para esta combinación. Considerar IGNORAR."
        )

    # Warning: trader en blacklist
    if display_name_lower in blacklist_lower:
        result["warnings"].append(
            f"Trader {display_name} está en BLACKLIST. Evaluar counter."
        )

    # --- FILTRO MÍNIMO DE CAPITAL ---
    # v7.4: umbral subido de $3K a $5K — trades $3K-5K tienen WR 50% (coin flip, N=36).
    # $5K-10K WR 69.2% (N=26, +$769), $10K-20K WR 61.5% (N=13), $20K+ WR 76.9% (N=13).
    if valor_usd < 3000:
        result["reasoning"].append(
            f"Capital ${valor_usd:,.0f} < $5K mínimo para señal (v7.4: $3K-5K WR 50% coin flip). "
            f"Ballena registrada pero sin acción recomendada."
        )
        return result

    # --- DETECCIÓN DE SEÑALES ---
    signals = []

    # S1: Counter HIGH RISK (precio < 0.45) — DESACTIVADO GLOBALMENTE v7.4
    # WR global 35.3% (N=51) — peor que moneda al aire. Desglose:
    #   NBA: WR 26% (N=11), Soccer: WR 36% (N=16), NHL: WR 57% (N=10 — único rescatable pero N bajo),
    #   OTHER: WR 13% (N=8, 0W/8L en 0.30-0.40). La premisa "counter HIGH RISK = win" refutada.
    # ÚNICA subzona prometedora: NHL 0.40-0.45 WR 83% (N=6) — hipótesis, sin implementar.
    # Reactivar cuando N≥20 por categoría específica con WR≥65% sostenido.
    # if 'HIGH RISK' in tier_upper and poly_price < 0.45 and category != "NBA":
    #     if 0.40 <= poly_price < 0.45:
    #         signals.append({
    #             "id": "S1",
    #             "action": "COUNTER",
    #             "confidence": "LOW",
    #             "win_rate": 57.0,
    #             "reasoning": f"S1 zona fuerte: Counter HIGH RISK {category} a {poly_price:.2f}",
    #         })
    #     else:  # < 0.40
    #         signals.append({
    #             "id": "S1",
    #             "action": "COUNTER",
    #             "confidence": "LOW",
    #             "win_rate": 60.0,
    #             "reasoning": f"S1 zona baja: Counter HIGH RISK {category} a {poly_price:.2f}",
    #         })

    # S1B: Counter Soccer — SUSPENDIDA v7.3 (WR 52.9% N=17, sin edge en ningún rango)
    # Desglose: <0.30 WR 33%, 0.30-0.35 WR 50%, 0.35-0.40 WR 31%. Señal degradada a HIPÓTESIS.
    # Reactivar cuando N≥30 adicionales con WR≥65% en rango activo.
    # if category == "SOCCER" and poly_price < 0.35:
    #     signals.append({
    #         "id": "S1B",
    #         "action": "COUNTER",
    #         "confidence": "MEDIUM",
    #         "win_rate": 80.0,
    #         "reasoning": f"S1B: Counter Fútbol a {poly_price:.2f} cualquier tier (WR 80%, N=5 — MEDIUM hasta N≥15)",
    #     })

    # S1-MMA-RISKY: Counter RISKY en MMA, precio < 0.50 (embrionaria v6.0)
    # WR follow = 0% (N=5) → WR counter = 100%. Todos underdogs UFC perdieron.
    # RISKY en MMA = opuesto a RISKY en NBA (que es señal positiva WR 78.6%).
    # Muestra pequeña (N=5) → stake 0.5x, solo activar como alerta LOW.
    _is_risky_not_hr = 'RISKY' in tier_upper and 'HIGH RISK' not in tier_upper
    if category == "MMA" and _is_risky_not_hr and poly_price < 0.50:
        signals.append({
            "id": "S1-MMA-RISKY",
            "action": "COUNTER",
            "confidence": "LOW",
            "win_rate": 100.0,
            "reasoning": f"S1-MMA-RISKY: Counter RISKY en MMA a {poly_price:.2f} (WR 100% counter, N=5 — stake 0.5x, muestra pequeña)",
        })

    # S2: Follow NBA 0.50-0.60, excluir HIGH RISK, BOT/MM, SILVER y BRONZE (zona core)
    # WR 62.5% (N=72). RISKY boost: WR 78.6% (N=14) → confianza HIGH cuando tier=RISKY.
    # HIGH RISK NBA: WR 49.4%, PnL -818. BOT/MM: WR 30.8%, PnL -595 → excluir siempre.
    # SILVER: WR 25% (confirmado v7.3) → excluir.
    # BRONZE: WR 35.7% (N=14, PnL -$431, v7.4) — tier más destructor en S2. EXCLUIR.
    # Sin BRONZE: WR sube 58.4%→63.5%, PnL +$593→+$1,023. STANDARD (WR 78%) y RISKY (75%) cargan.
    # SELL global WR 36.1%: excluir SELLs en toda la familia S2 (solo BUY genera señal).
    _s2_excl = (not _is_tier_override and (
                    'HIGH RISK' in tier_upper or 'BOT' in tier_upper)
                or 'SILVER' in tier_upper or 'BRONZE' in tier_upper)
    if category == "NBA" and 0.50 <= poly_price <= 0.60 and not _s2_excl and side == "BUY":
        _is_risky_s2 = 'RISKY' in tier_upper  # HIGH RISK ya excluido arriba
        if _is_risky_s2:
            confidence = "HIGH"
            wr_s2 = 75.0
            reasoning = f"S2+RISKY: Follow NBA a {poly_price:.2f} (WR 75.0%, N=12 — tier RISKY boost)"
        else:
            confidence = "MEDIUM"
            wr_s2 = 63.5
            reasoning = f"S2: Follow NBA a {poly_price:.2f} (WR 63.5%, excl. HIGH RISK/BOT/SILVER/BRONZE)"

        if display_name_lower in whitelist_a_lower:
            confidence = "HIGH"
            reasoning += f" | Whitelist A ({display_name}) → stake 1.5x"
        elif display_name_lower in whitelist_b_lower:
            reasoning += f" | Whitelist B ({display_name}) → stake 1.25x"
        if _is_tier_override and ('HIGH RISK' in tier_upper or 'BOT' in tier_upper):
            reasoning += f" | TIER-OVERRIDE ({display_name}, tier snapshot ignorado — WR validado)"

        # v7.4: Nicho es multiplicador real en NBA — S2 nicho WR 73.3% vs no-nicho 58.9%
        if is_nicho:
            confidence = "HIGH" if confidence == "MEDIUM" else confidence
            reasoning += f" | NICHO +boost (S2-nicho WR 73.3% vs 58.9%)"

        signals.append({
            "id": "S2",
            "action": "FOLLOW",
            "confidence": confidence,
            "win_rate": wr_s2,
            "reasoning": reasoning,
        })

    # S2B: Follow NBA 0.60-0.82, excluir HIGH RISK y BOT/MM (v7.0: hard IGNORE >0.82)
    # v7.3: zonas diferenciadas por dataset Gold 409 trades.
    # v7.4: WR actualizados con nuevo dataset:
    #   0.60-0.70 sin HR: WR 78.6% (N=28) → conf MEDIUM. HR excluido (WR 53.8%, N=13, -$159).
    #   0.70-0.80 sin HR: WR 84.6% (N=39) → conf HIGH. HR en esta zona monitorear (WR 77.8%).
    #   0.80-0.82 sin HR: WR 100% (N=4) → conf HIGH con stake ×0.75 por payout reducido.
    # >0.82: IGNORE — EV negativo (break-even WR = precio, supera WR histórico).
    _s2b_excl = not _is_tier_override and ('HIGH RISK' in tier_upper or 'BOT' in tier_upper)
    if category == "NBA" and 0.82 < poly_price < 0.85 and not _s2b_excl:
        payout_pct = (1 / poly_price - 1) * 100
        result["warnings"].append(
            f"S2B precio {poly_price:.2f} > 0.82: EV negativo "
            f"(WR 84% × payout {payout_pct:.0f}% — break-even requiere WR >{poly_price*100:.0f}%). IGNORADO."
        )
    elif category == "NBA" and 0.60 < poly_price <= 0.82 and not _s2b_excl and side == "BUY":
        if poly_price >= 0.80:
            confidence = "HIGH"
            wr_s2b = 100.0
            payout_pct = (1 / poly_price - 1) * 100
            reasoning = (
                f"S2B zona alta: Follow NBA a {poly_price:.2f} (subzona 0.80-0.82, WR 100%, N=4, excl. HIGH RISK/BOT)"
                f" — payout {payout_pct:.0f}%"
            )
        elif poly_price >= 0.70:
            confidence = "HIGH"
            wr_s2b = 84.6
            reasoning = f"S2B zona fuerte: Follow NBA a {poly_price:.2f} (WR 84.6%, N=39, rango 0.70-0.80, excl. HIGH RISK/BOT)"
        else:  # 0.60 < price < 0.70
            confidence = "MEDIUM"
            wr_s2b = 78.6
            reasoning = f"S2B zona baja: Follow NBA a {poly_price:.2f} (WR 78.6%, N=28, rango 0.60-0.70, excl. HIGH RISK/BOT)"

        if display_name_lower in whitelist_a_lower:
            reasoning += f" | Whitelist A ({display_name}) → stake 1.5x"
        elif display_name_lower in whitelist_b_lower:
            reasoning += f" | Whitelist B ({display_name}) → stake 1.25x"
        if _is_tier_override and ('HIGH RISK' in tier_upper or 'BOT' in tier_upper):
            reasoning += f" | TIER-OVERRIDE ({display_name}, tier snapshot ignorado — WR validado)"

        signals.append({
            "id": "S2B",
            "action": "FOLLOW",
            "confidence": confidence,
            "win_rate": wr_s2b,
            "reasoning": reasoning,
        })

    # S2C: Follow NBA 0.45-0.50, excluir HIGH RISK, BOT/MM, STANDARD y SILVER (v5.0)
    # La "zona muerta" 0.45-0.50 es muerta para non-NBA pero tiene señal real en NBA.
    # v7.3: STANDARD añadido a exclusiones (WR 25%, N=4 — sin edge).
    # v7.4: SILVER añadido a exclusiones (WR 33%, N=3). RISKY es la estrella (WR 85.7%, N=7, +$487).
    # RISKY+BRONZE combinado: WR 73.3% (N=15, +$721). Nicho boost: S2C-nicho WR 80% (N=5, +$334).
    _s2c_excl = ('STANDARD' in tier_upper or 'SILVER' in tier_upper
                 or (not _is_tier_override and ('HIGH RISK' in tier_upper or 'BOT' in tier_upper)))
    if category == "NBA" and 0.45 <= poly_price < 0.50 and not _s2c_excl and side == "BUY":
        _is_risky_s2c = 'RISKY' in tier_upper
        if _is_risky_s2c:
            confidence = "HIGH"
            wr_s2c = 85.7
            reasoning = f"S2C+RISKY: Follow NBA a {poly_price:.2f} (WR 85.7%, N=7 — tier RISKY estrella)"
        else:
            confidence = "MEDIUM"
            wr_s2c = 67.6
            reasoning = f"S2C: Follow NBA a {poly_price:.2f} (WR 67.6%, excl. HIGH RISK/BOT/STANDARD/SILVER)"

        if display_name_lower in whitelist_a_lower:
            confidence = "HIGH"
            reasoning += f" | Whitelist A ({display_name})"
        elif display_name_lower in whitelist_b_lower:
            reasoning += f" | Whitelist B ({display_name}) → stake 1.25x"
        if _is_tier_override and ('HIGH RISK' in tier_upper or 'BOT' in tier_upper):
            reasoning += f" | TIER-OVERRIDE ({display_name}, tier snapshot ignorado — WR validado)"

        # v7.4: Nicho boost en S2C — WR 80% (N=5, +$334)
        if is_nicho:
            confidence = "HIGH" if confidence == "MEDIUM" else confidence
            reasoning += f" | NICHO +boost (S2C-nicho WR 80%, N=5)"

        signals.append({
            "id": "S2C",
            "action": "FOLLOW",
            "confidence": confidence,
            "win_rate": wr_s2c,
            "reasoning": reasoning,
        })

    # S3: Follow Nicho — RESTRINGIDO A ESPORTS SIN HIGH RISK (v7.4)
    # v7.4: S3 global WR 54.1% (N=37, PnL -$516). Desglose por categoría:
    #   ESPORTS sin HR: WR 83.3% (N=6, +$212) — la única subzona con edge real.
    #   NHL sin HR: WR 60% (N=10) — marginal, excluido por seguridad.
    #   OTHER: WR 33% — destruye (ya excluido v7.3).
    #   TENNIS: WR 0% (N=2) — destruye (ya excluido v7.2).
    # Restringir a solo ESPORTS salva la señal. NHL hipótesis pendiente N≥20 con WR≥70%.
    # v7.2: HIGH RISK excluido (S3+HR WR ~33% vs sin HR WR 85.7% — cambio dramático).
    _S3_EXCLUDED = ("NBA", "SOCCER", "CRYPTO", "TENNIS", "OTHER", "NHL", "MMA")
    _s3_excl_tier = 'HIGH RISK' in tier_upper
    if is_nicho and category not in _S3_EXCLUDED and 0.50 <= poly_price < 0.85 and not _s3_excl_tier:
        signals.append({
            "id": "S3",
            "action": "FOLLOW",
            "confidence": "LOW",
            "win_rate": 83.3,
            "reasoning": f"S3: Follow Nicho ESPORTS a {poly_price:.2f} (WR 83.3%, N=6, excl. HIGH RISK)",
        })

    # S4: Counter Crypto (solo intraday Up/Down automático), excluir HIGH RISK
    # WR 62.5% (N=32) excl. HIGH RISK. Con HIGH RISK incluido: WR counter solo 25% (ballena GANA).
    # HIGH RISK en crypto intraday = trader con info → no contrariar.
    # v7.3: restringido a precio ≥ 0.60. Zona <0.60 sin edge confirmado.
    if category == "CRYPTO":
        if _is_crypto_intraday(market_title):
            if 'HIGH RISK' in tier_upper:
                result["warnings"].append(
                    "S4: HIGH RISK en Crypto intraday — la ballena GANA aquí (WR counter 25%). Sin señal."
                )
            elif poly_price < 0.60:
                result["warnings"].append(
                    f"S4: precio {poly_price:.2f} < 0.60 — zona sin edge confirmado. Sin señal S4."
                )
            else:
                signals.append({
                    "id": "S4",
                    "action": "COUNTER",
                    "confidence": "MEDIUM",
                    "win_rate": 62.5,
                    "reasoning": f"S4: Counter Crypto intraday Up/Down a {poly_price:.2f} (WR 62.5%, excl. HIGH RISK, rango ≥0.60)",
                })
        else:
            result["warnings"].append(
                "S4 aplica solo a crypto intraday Up/Down. Para crypto largo plazo, validar manualmente."
            )

    # S5: Follow Soccer — SUSPENDIDA v7.3 (WR 38.1% N=21 — reversión total)
    # Causa probable: contaminación MMA/Esports en clasificador + Manchester City 7 losses.
    # Reactivar cuando N≥30 Soccer puro limpio con WR≥60%.
    # HIPÓTESIS S5-MMA: Follow MMA 0.60-0.70 WR 100% (N=6 actualizado v7.4, era N=3 en v7.3).
    # 6/6 wins en UFC 0.60-0.70 BUY, todas las categorías de tier. Hipótesis más prometedora del dataset.
    # Implementar cuando N≥15. Bajo watch activo.
    # _s5_excl = 'GOLD' in tier_upper or 'RISKY' in tier_upper or 'HIGH RISK' in tier_upper or 'BOT' in tier_upper
    # if category == "SOCCER" and 0.65 <= poly_price < 0.80 and not _s5_excl:
    #     signals.append({
    #         "id": "S5",
    #         "action": "FOLLOW",
    #         "confidence": "MEDIUM",
    #         "win_rate": 73.0,
    #         "reasoning": (
    #             f"S5: Follow Fútbol {tier} a {poly_price:.2f} "
    #             f"(WR hist. 73.0%, excl. GOLD/RISKY/HR/BOT — N reducido post-filtros, monitorear)"
    #         ),
    #     })

    # S6: Counter ESPORTS precio 0.40-0.50 (v6.1: WR bajó a 66.7%, N=24 — conf bajada a LOW)
    # WR redujo de 81.8% → 66.7% con más datos. Sigue válida pero confianza reducida.
    # v7.3: límite inferior añadido — restringido a 0.40-0.50 (precio muy bajo sin datos).
    if category == "ESPORTS" and 0.40 <= poly_price < 0.50:
        signals.append({
            "id": "S6",
            "action": "COUNTER",
            "confidence": "LOW",
            "win_rate": 66.7,
            "reasoning": f"S6: Counter ESPORTS a {poly_price:.2f} (WR 66.7%, N=24)",
        })

    # S7: Follow ESPORTS 0.60-0.70, excluir HIGH RISK (v6.1: WR 85.7%, N=14 — cruzó N=15, conf MEDIUM)
    # WR 85.7% estable (N=14). MEDIUM hasta N≥20 con WR≥85% para subir a HIGH.
    # v7.3: HIGH RISK excluido (tier con WR inferior — mismo principio que S2/S3).
    if category == "ESPORTS" and 0.60 <= poly_price < 0.70 and 'HIGH RISK' not in tier_upper:
        signals.append({
            "id": "S7",
            "action": "FOLLOW",
            "confidence": "MEDIUM",
            "win_rate": 85.7,
            "reasoning": f"S7: Follow ESPORTS a {poly_price:.2f} (WR 85.7%, N=14, excl. HIGH RISK)",
        })

    # S8: Follow NHL 0.60-0.70 — DESACTIVADO v7.4
    # WR 33.3% (N=6, PnL -$287) — no hay edge en esta señal.
    # Desglose: 4 HIGH RISK (WR 50%, PnL -$87) + 1 BRONZE (0W) + 1 NBA mal clasificado (0W).
    # NHL en general WR 44.4% (N=9) en rango 0.60-0.70 combinando todas las DBs.
    # HIPÓTESIS: NHL 0.40-0.50 muestra promise (WR 62.5%, N=8) — documentar, no implementar.
    # Reactivar S8 cuando N≥15 con WR≥65% en dataset limpio.
    # _s8_excl = 'BOT' in tier_upper or 'SILVER' in tier_upper
    # if category == "NHL" and 0.60 <= poly_price < 0.70 and not _s8_excl and side == "BUY":
    #     signals.append({
    #         "id": "S8",
    #         "action": "FOLLOW",
    #         "confidence": "MEDIUM",
    #         "win_rate": 86.0,
    #         "reasoning": f"S8: Follow NHL a {poly_price:.2f} (WR ~86%, N≥15, excl. BOT/SILVER)",
    #     })

    # S9: Counter HIGH RISK en NHL — DESACTIVADO (implementado v7.4, revertido v7.4.1)
    # El dato de Gold N=15 WR 26.7% era ilusión estadística.
    # Dataset Whales N=32 confirma WR exactamente 50% — coin flip, sin edge.
    # No reimplementar hasta N≥40 en dataset combinado con WR≥65% sostenido.
    # HIPÓTESIS: vigilar si el patrón reaparece en futuras iteraciones del dataset.
    # if category == "NHL" and 'HIGH RISK' in tier_upper and 0.30 <= poly_price <= 0.80:
    #     signals.append({
    #         "id": "S9",
    #         "action": "COUNTER",
    #         "confidence": "MEDIUM",
    #         "win_rate": 73.3,
    #         "reasoning": f"S9: Counter HIGH RISK NHL a {poly_price:.2f} ...",
    #     })

    # S5-MMA: Follow MMA 0.60-0.70 — ACTIVADO con cautela v7.4
    # WR 100% (N=6, +$355) — 6/6 wins en UFC BUY 0.60-0.70.
    # N=6 es INFERIOR al umbral N≥15. Activado por petición explícita con stake mínimo (1%).
    # ⚠️ MUESTRA PEQUEÑA: cualquier run de 3-4 pérdidas puede borrar el edge histórico.
    # Excluir BOT/MM y HIGH RISK. Dataset Whales confirma: HIGH RISK en MMA 0.60-0.70 WR 33%.
    # Solo SILVER muestra promise en MMA (Whales) pero N insuficiente para confirmar.
    # Subir a MEDIUM cuando N≥15 y WR≥80% sostenido.
    _s5mma_excl = 'BOT' in tier_upper or 'HIGH RISK' in tier_upper
    if category == "MMA" and 0.60 <= poly_price < 0.70 and not _s5mma_excl and side == "BUY":
        signals.append({
            "id": "S5-MMA",
            "action": "FOLLOW",
            "confidence": "LOW",
            "win_rate": 100.0,
            "reasoning": (
                f"S5-MMA: Follow MMA a {poly_price:.2f} "
                f"(WR 100%, N=6 ⚠️ muestra pequeña — stake 1% mínimo, monitorear activamente)"
            ),
        })

    # --- IGNORAR si precio > 0.85 (payout trap) ---
    if poly_price > 0.85:
        result["action"] = "IGNORE"
        result["signal_id"] = "NONE"
        result["reasoning"].append("Precio >0.85: payout insuficiente. IGNORAR.")
        return result

    # --- IGNORAR zona muerta 0.45-0.49 (no activa ninguna señal) ---
    if 0.45 <= poly_price <= 0.49 and not signals:
        result["action"] = "IGNORE"
        result["signal_id"] = "NONE"
        result["reasoning"].append("Zona muerta 0.45-0.49 sin señal activa. IGNORAR.")
        return result

    # --- SIN SEÑALES ---
    if not signals:
        result["action"] = "IGNORE"
        result["signal_id"] = "NONE"
        # Diagnóstico agrupado por acción: qué impidió COUNTER y qué impidió FOLLOW
        counter_blocks = []
        follow_blocks = []

        # COUNTER — S1 DESACTIVADO GLOBALMENTE v7.4 (WR 35.3% N=51 — sin edge)
        counter_blocks.append("S1 DESACTIVADO v7.4 (global WR 35.3% N=51 — premisa refutada)")
        # COUNTER — S1B (SUSPENDIDA v7.3 — WR 52.9%, sin edge)
        if category == "SOCCER":
            counter_blocks.append("S1B SUSPENDIDA v7.3 (Soccer WR 52.9% N=17 — sin edge, hipótesis)")
        # COUNTER — S4 (Crypto intraday, precio ≥ 0.60)
        if category != "CRYPTO":
            counter_blocks.append(f"S4 necesita CRYPTO (es {category})")
        elif not _is_crypto_intraday(market_title):
            counter_blocks.append("S4 necesita intraday Up/Down")
        elif poly_price < 0.60:
            counter_blocks.append(f"S4 necesita precio ≥0.60 (es {poly_price:.2f})")
        # COUNTER — S6 (ESPORTS precio 0.40-0.50)
        if category != "ESPORTS":
            counter_blocks.append(f"S6 necesita ESPORTS (es {category})")
        elif not (0.40 <= poly_price < 0.50):
            counter_blocks.append(f"S6 necesita precio 0.40-0.50 (es {poly_price:.2f})")
        # COUNTER — S9 (NHL HIGH RISK precio 0.30-0.80)
        if category == "NHL" and 'HIGH RISK' not in tier_upper:
            counter_blocks.append(f"S9 necesita HIGH RISK en NHL (tier={tier})")
        elif category == "NHL" and not (0.30 <= poly_price <= 0.80):
            counter_blocks.append(f"S9 necesita precio 0.30-0.80 (es {poly_price:.2f})")

        # FOLLOW — S2/S2B/S2C (NBA, excl. HIGH RISK/BOT/SILVER/BRONZE)
        if category != "NBA":
            follow_blocks.append(f"S2/S2B/S2C necesita NBA (es {category})")
        elif 'SILVER' in tier_upper or 'BRONZE' in tier_upper:
            follow_blocks.append(f"S2/S2B excluye SILVER/BRONZE (tier={tier})")
        elif ('HIGH RISK' in tier_upper or 'BOT' in tier_upper) and not _is_tier_override:
            follow_blocks.append(f"S2/S2B excluye {tier} (no está en WHITELIST_TIER_OVERRIDE)")
        elif not (0.45 <= poly_price <= 0.82):
            follow_blocks.append(f"S2C/S2/S2B necesita precio 0.45-0.82 (es {poly_price:.2f})")
        # FOLLOW — S3 (Nicho excl. NBA/Soccer/Crypto/Tennis/Other, excl. HIGH RISK)
        if not is_nicho:
            follow_blocks.append("S3 necesita mercado nicho")
        elif category in ("NBA", "SOCCER", "CRYPTO", "TENNIS", "OTHER", "NHL", "MMA"):
            follow_blocks.append(f"S3 excluye {category} (v7.4: solo ESPORTS-nicho activo)")
        elif 'HIGH RISK' in tier_upper:
            follow_blocks.append(f"S3 excluye HIGH RISK (tier={tier}, WR 0% en dataset)")
        elif not (0.50 <= poly_price < 0.85):
            follow_blocks.append(f"S3 necesita precio 0.50-0.85 (es {poly_price:.2f})")
        # FOLLOW — S5 (SUSPENDIDA v7.3 — WR 38.1%)
        if category == "SOCCER":
            follow_blocks.append("S5 SUSPENDIDA v7.3 (Soccer WR 38.1% N=21 — reactivar N≥30 limpio)")
        # FOLLOW — S5-MMA (MMA 0.60-0.70, excl. BOT)
        if category == "MMA" and 'BOT' in tier_upper:
            follow_blocks.append(f"S5-MMA excluye BOT/MM (tier={tier})")
        elif category == "MMA" and not (0.60 <= poly_price < 0.70):
            follow_blocks.append(f"S5-MMA necesita precio 0.60-0.70 (es {poly_price:.2f})")

        counter_str = "Sin COUNTER: " + ", ".join(counter_blocks) if counter_blocks else ""
        follow_str = "Sin FOLLOW: " + ", ".join(follow_blocks) if follow_blocks else ""
        parts = [p for p in [counter_str, follow_str] if p]
        result["reasoning"].append(" | ".join(parts) if parts else "Sin señal activa.")
        return result

    # --- RESOLUCIÓN DE CONFLICTOS (múltiples señales) ---
    # Verificar conflicto HIGH RISK en ambos lados ANTES de asignar señal
    if 'HIGH RISK' in tier_upper and opposite_tier and 'HIGH RISK' in opposite_tier.upper():
        result["action"] = "IGNORE"
        result["signal_id"] = "NONE"
        result["reasoning"].append("Conflicto HIGH RISK en ambos lados — IGNORAR")
        return result
    
    if len(signals) == 1:
        s = signals[0]
        result["action"] = s["action"]
        result["signal_id"] = s["id"]
        result["confidence"] = s["confidence"]
        result["win_rate_hist"] = s["win_rate"]
        result["reasoning"].append(s["reasoning"])
    else:
        result = _resolve_conflicts(signals, result, tier_upper, poly_price, opposite_tier)

    # --- AJUSTES POST-SEÑAL ---

    # v7.4: Sucker bet downgrade — si edge < -3%, bajar confidence un nivel
    if edge_pct < -3.0 and result["action"] != "IGNORE":
        _conf_map = {"HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "LOW"}
        old_conf = result.get("confidence", "MEDIUM")
        result["confidence"] = _conf_map.get(old_conf, old_conf)
        result["reasoning"].append(
            f"Confidence degradada {old_conf}→{result['confidence']} por sucker bet (edge {edge_pct:+.1f}%)"
        )

    # Calcular expected ROI
    if result["win_rate_hist"] > 0 and result["payout_mult"] > 0:
        wr = result["win_rate_hist"] / 100.0
        result["expected_roi"] = round((wr * result["payout_mult"] - (1 - wr)) * 100, 1)

    # FIX 7: Whitelist A boost ya está aplicado dentro de la detección de S2.
    # El bloque duplicado post-señal fue eliminado.

    return result


def _resolve_conflicts(signals: list, result: dict, tier_upper: str, poly_price: float,
                       opposite_tier: str = "") -> dict:
    """Resuelve conflictos entre múltiples señales según el árbol de decisión v4.0."""
    s1      = next((s for s in signals if s["id"] == "S1"),      None)
    s1b     = next((s for s in signals if s["id"] == "S1B"),     None)
    s2      = next((s for s in signals if s["id"] == "S2"),      None)
    s2b     = next((s for s in signals if s["id"] == "S2B"),     None)
    s3      = next((s for s in signals if s["id"] == "S3"),      None)
    s4      = next((s for s in signals if s["id"] == "S4"),      None)
    s5      = next((s for s in signals if s["id"] == "S5"),      None)
    s6      = next((s for s in signals if s["id"] == "S6"),      None)
    # S9 (NHL) y S5-MMA (MMA) no tienen conflictos posibles: sus categorías son exclusivas.

    # CASO 0: S1 + S1B ambas en Soccer precio <0.40 — S1B prevalece (más datos, mejor WR)
    if s1 and s1b:
        result["action"] = "COUNTER"
        result["signal_id"] = "S1B"
        result["confidence"] = "MEDIUM"
        result["win_rate_hist"] = s1b["win_rate"]
        result["reasoning"].append(
            f"S1+S1B Soccer <0.40: S1B prevalece (WR {s1b['win_rate']}% N=24 vs S1 {s1['win_rate']}%)"
        )
        return result

    # CASO 1: S1 + S2 — S1 (COUNTER) prevalece sobre S2 (FOLLOW)
    # Los rangos son exclusivos (S1 precio<0.45, S2 precio 0.50-0.60), pero puede haber
    # solapamiento teórico si lógica cambia. S1 siempre gana a cualquier FOLLOW.
    if s1 and s2:
        result["action"] = "COUNTER"
        result["signal_id"] = "S1"
        result["confidence"] = "HIGH"
        result["win_rate_hist"] = s1["win_rate"]
        result["reasoning"].append(
            f"Conflicto S1 vs S2: S1 prevalece (WR {s1['win_rate']}% vs {s2['win_rate']}%)"
        )
        return result

    # CASO 1B: S1B + S5 — S1B (COUNTER Soccer <0.40) prevalece sobre S5 (FOLLOW Soccer 0.60-0.80)
    # Rangos no se solapan pero se mantiene el caso por claridad del árbol de decisión.
    if s1b and s5:
        result["action"] = "COUNTER"
        result["signal_id"] = "S1B"
        result["confidence"] = "MEDIUM"
        result["win_rate_hist"] = s1b["win_rate"]
        result["reasoning"].append(
            "S1B COUNTER prevalece sobre S5 FOLLOW (precio <0.40 es zona de error ballena en Soccer)"
        )
        return result

    # CASO 2: S4 + S3 — S4 (COUNTER crypto intraday) prevalece sobre S3 (FOLLOW nicho)
    if s4 and s3:
        result["action"] = "COUNTER"
        result["signal_id"] = "S4"
        result["confidence"] = s4["confidence"]
        result["win_rate_hist"] = s4["win_rate"]
        result["reasoning"].append(
            f"S4 prevalece sobre S3 (WR {s4['win_rate']}% vs {s3['win_rate']}%)"
        )
        return result

    # CASO 3: Dos HIGH RISK en lados opuestos → IGNORAR
    if 'HIGH RISK' in tier_upper and 'HIGH RISK' in opposite_tier.upper():
        result["action"] = "IGNORE"
        result["signal_id"] = "NONE"
        result["confidence"] = "—"
        result["reasoning"].append(
            "Conflicto HIGH RISK en ambos lados — IGNORAR (ver árbol de decisión v4.0)"
        )
        return result

    # CASO S1+S6: COUNTER ESPORTS HIGH RISK <0.45 — S6 prevalece (WR 85.7% > S1 72%)
    if s1 and s6:
        result["action"] = "COUNTER"
        result["signal_id"] = "S6"
        result["confidence"] = "MEDIUM"
        result["win_rate_hist"] = s6["win_rate"]
        result["reasoning"].append(
            f"S1+S6 ESPORTS: S6 prevalece (WR {s6['win_rate']}% > S1 {s1['win_rate']}%)"
        )
        return result

    # CASO 4: Conflicto sin HIGH RISK — prevalece señal con precio más cercano a 0.55
    best = min(signals, key=lambda s: abs(poly_price - 0.55))
    result["action"] = best["action"]
    result["signal_id"] = best["id"]
    result["confidence"] = best["confidence"]
    result["win_rate_hist"] = best["win_rate"]
    result["reasoning"].append(best["reasoning"])
    result["reasoning"].append(
        f"Resolución de conflicto: precio {poly_price:.2f} más cercano a 0.55"
    )
    return result


# ============================================================================
# MÓDULO DE CONSENSO MULTI-BALLENA PARA S2+
# ============================================================================

def classify_consensus(
    market_title: str,
    whale_entries: list,
) -> dict:
    """
    Evalúa si un grupo de ballenas en el mismo mercado NBA activa S2+ (consensus boost).

    Args:
        market_title: Título del mercado
        whale_entries: Lista de dicts con {side, poly_price, tier, display_name}

    Returns:
        dict con la clasificación S2+ o NONE
    """
    category = _detect_category(market_title)
    if category != "NBA":
        return {"signal_id": "NONE", "action": "IGNORE", "reasoning": ["S2+ solo aplica a NBA"]}

    if len(whale_entries) < 3:
        return {"signal_id": "NONE", "action": "IGNORE",
                "reasoning": [f"Solo {len(whale_entries)} ballenas, necesita 3+ para S2+"]}

    # Agrupar por lado
    sides = {}
    for entry in whale_entries:
        s = entry.get("side", "BUY")
        if s not in sides:
            sides[s] = []
        sides[s].append(entry)

    # Buscar lado con 3+ ballenas
    for side_key, entries in sides.items():
        if len(entries) >= 3:
            prices = [e["poly_price"] for e in entries]
            avg_price = sum(prices) / len(prices)

            # Todas dentro de 0.50-0.60
            all_in_range = all(0.50 <= p <= 0.60 for p in prices)

            if all_in_range and 0.50 <= avg_price <= 0.60:
                return {
                    "signal_id": "S2+",
                    "action": "FOLLOW",
                    "confidence": "HIGH",
                    "win_rate_hist": 78.1,
                    "reasoning": [
                        f"S2+ Consensus: {len(entries)} ballenas → {side_key} "
                        f"| Precio promedio {avg_price:.2f} (todas en rango 0.50-0.60)"
                    ],
                    "warnings": [],
                    "category": "NBA",
                }
            else:
                out_of_range = [p for p in prices if p < 0.50 or p > 0.60]
                return {
                    "signal_id": "NONE",
                    "action": "IGNORE",
                    "reasoning": [
                        f"S2+ NO activado: dispersión alta. "
                        f"Precios fuera de rango: {out_of_range}"
                    ],
                }

    return {"signal_id": "NONE", "action": "IGNORE",
            "reasoning": ["No hay 3+ ballenas en el mismo lado"]}


def classify_consensus_counter(_whale_entries: list) -> dict:
    """
    S1+: Counter consensus en zona 0.40-0.44 — DESACTIVADO v7.4.

    S1 COUNTER fue desactivado globalmente (WR 35.3% N=51 — refuta la premisa).
    S1+ Consensus hereda la misma invalidación: si el individual no tiene edge,
    el consenso tampoco. Reactivar solo si S1 individual se reactiva con WR≥65%.
    """
    # v7.4: S1 COUNTER desactivado globalmente. S1+ sigue la misma lógica.
    return {"signal_id": "NONE", "action": "IGNORE",
            "reasoning": ["S1+ DESACTIVADO v7.4 (S1 COUNTER global WR 35.3% N=51 — sin edge)"]}


# ============================================================================
# CLASES DE INFRAESTRUCTURA (del definitive_all_claude.py original)
# ============================================================================

class TradeFilter:
    """Filtro de calidad de apuesta para descartar trades no copiables"""
    def __init__(self, session):
        self.session = session
        self.markets_cache = {}

    def is_worth_copying(self, trade, valor) -> tuple:
        price = float(trade.get('price', 0))
        side = trade.get('side', '').upper()

        if price < 0.15 or price > 0.82:
            return False, "Precio fuera de rango (+EV)"

        slug = trade.get('slug', '')
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

        return True, "Trade válido"

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
        self.trades = {}

    def add(self, market_id, side, value, wallet='', price=0.0, tier='', display_name=''):
        if market_id not in self.trades:
            self.trades[market_id] = []
        self.trades[market_id].append({
            'timestamp': time.time(),
            'side': side,
            'value': value,
            'wallet': wallet,
            'price': price,
            'tier': tier,
            'display_name': display_name,
        })
        self._cleanup(market_id)

    def _cleanup(self, market_id):
        now = time.time()
        self.trades[market_id] = [
            e for e in self.trades[market_id]
            if now - e['timestamp'] <= self.window
        ]

    def get_signal(self, market_id):
        self._cleanup(market_id)
        entries = self.trades.get(market_id, [])

        # Deduplicar por wallet: si una misma wallet hizo varios trades en el mismo mercado,
        # contar solo el más reciente para evitar falsos consensos con 1 sola wallet real.
        seen_wallets = {}
        for e in entries:
            w = e.get('wallet', '')
            if not w or w not in seen_wallets or e['timestamp'] > seen_wallets[w]['timestamp']:
                seen_wallets[w] = e
        deduped = list(seen_wallets.values())

        side_counts = {}
        side_values = {}
        for e in deduped:
            side = e['side']
            side_counts[side] = side_counts.get(side, 0) + 1
            side_values[side] = side_values.get(side, 0) + e['value']

        best_side = None
        best_count = 0
        for side, count in side_counts.items():
            if count >= 2 and count > best_count:
                best_count = count
                best_side = side

        if best_side:
            return True, best_count, best_side, side_values[best_side]
        return False, 0, '', 0

    def get_whale_entries(self, market_id):
        """Retorna las entradas de ballenas para evaluación S2+."""
        self._cleanup(market_id)
        entries = self.trades.get(market_id, [])
        return [
            {
                'side': e['side'],
                'poly_price': e['price'],
                'tier': e['tier'],
                'display_name': e['display_name'],
            }
            for e in entries
        ]


class CoordinationDetector:
    """Detecta ballenas coordinadas operando juntas"""
    def __init__(self, coordination_window=300):
        self.coordination_window = coordination_window
        self.market_trades = {}

    def add_trade(self, market_id, wallet, side, value):
        if market_id not in self.market_trades:
            self.market_trades[market_id] = []

        self.market_trades[market_id].append({
            'timestamp': time.time(),
            'wallet': wallet,
            'side': side,
            'value': value
        })
        self._cleanup(market_id)

    def _cleanup(self, market_id):
        now = time.time()
        one_hour = 3600
        self.market_trades[market_id] = [
            t for t in self.market_trades[market_id]
            if now - t['timestamp'] <= one_hour
        ]

    def detect_coordination(self, market_id, current_wallet, current_side):
        if market_id not in self.market_trades:
            return False, 0, "", []

        trades = self.market_trades[market_id]
        now = time.time()

        recent_trades = [
            t for t in trades
            if now - t['timestamp'] <= self.coordination_window
            and t['side'] == current_side
        ]

        if len(recent_trades) < 3:
            return False, 0, "", []

        unique_wallets = set(t['wallet'] for t in recent_trades if t['wallet'])

        if len(unique_wallets) >= 3:
            total_value = sum(t['value'] for t in recent_trades)
            time_spread = now - min(t['timestamp'] for t in recent_trades)
            description = f"{len(unique_wallets)} wallets -> {current_side} en {time_spread/60:.1f} min"
            return True, len(unique_wallets), description, list(unique_wallets)

        return False, 0, "", []


# ============================================================================
# DETECTOR PRINCIPAL (GOLD EDITION)
# ============================================================================

class GoldWhaleDetector:
    def __init__(self, umbral):
        self.umbral = umbral

        self.trades_vistos_ids = set()
        self.trades_vistos_deque = deque(maxlen=5000)

        self.ballenas_detectadas = 0
        self.ballenas_capturadas = 0
        self.ballenas_ignoradas = 0
        self.running = True
        self.markets_cache = {}
        self.ballenas_por_mercado = {}
        self.suma_valores_ballenas = 0.0
        self.ballena_maxima = {'valor': 0, 'mercado': 'N/A', 'wallet': 'N/A'}
        self.tiempo_inicio = time.time()

        self.session = self._crear_session_con_retry()

        self.trade_filter = TradeFilter(self.session)
        self.consensus = ConsensusTracker(window_minutes=30)
        self.coordination = CoordinationDetector(coordination_window=300)

        odds_api_key = os.getenv("ODDS_API_KEY", "")
        self.sports_edge = SportsEdgeDetector(odds_api_key, self.session)

        self.analysis_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="trader_analysis")
        self.scrape_semaphore = threading.Semaphore(1)  # Solo 1 Chrome activo a la vez
        self.analysis_cache = {}
        self._pending_reclassification = {}  # wallet -> trade pendiente de re-clasificar cuando llegue tier
        self._pending_tier_supabase_ids = {}  # wallet -> supabase row id con tier='' para actualizar cuando llegue tier
        self._deferred_trades = {}           # wallet -> trade completo esperando tier (opción 3)

        self.bankroll = self._cargar_bankroll()

        self.supabase: Client | None = None
        if SUPABASE_ENABLED and SUPABASE_URL and SUPABASE_KEY:
            try:
                self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                logger.info("Supabase conectado para tracking de ballenas deportivas")
            except Exception as e:
                logger.warning(f"Error conectando a Supabase: {e}")

        trades_live_dir = Path("trades_live")
        trades_live_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename_log = trades_live_dir / f"whales_{timestamp}.txt"
        self.historial_path = trades_live_dir / "historial_trades.json"

        self._cargar_historial()
        self._cargar_tier_cache()

        signal_module.signal(signal_module.SIGINT, self.signal_handler)
        signal_module.signal(signal_module.SIGTERM, self.signal_handler)

        logger.info(f"Monitor GOLD iniciado. Umbral: ${self.umbral:,.2f}")

    def _crear_session_con_retry(self):
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _es_ballena(self, valor: float, market_volume: float) -> tuple:
        es_ballena_absoluta = valor >= self.umbral
        es_ballena_relativa = (
            market_volume > 0 and
            (valor / market_volume) >= 0.03 and
            valor >= 500
        )

        pct_mercado = (valor / market_volume * 100) if market_volume > 0 else 0
        mostrar_concentracion = es_ballena_relativa

        return (es_ballena_absoluta or es_ballena_relativa), mostrar_concentracion, pct_mercado

    def _cargar_bankroll(self) -> float:
        """Carga el bankroll actual desde disco. Devuelve DEFAULT_BANKROLL si no existe."""
        try:
            if BANKROLL_PATH.exists():
                with open(BANKROLL_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                br = float(data.get('bankroll', DEFAULT_BANKROLL))
                logger.info(f"Bankroll cargado: ${br:,.2f}")
                return br
        except Exception as e:
            logger.warning(f"No se pudo cargar bankroll ({BANKROLL_PATH}): {e}")
        return DEFAULT_BANKROLL

    def _cargar_historial(self):
        if self.historial_path.exists():
            try:
                with open(self.historial_path, 'r') as f:
                    data = json.load(f)

                    ultima_act = data.get('ultima_actualizacion')
                    if ultima_act:
                        try:
                            fecha_hist = datetime.fromisoformat(ultima_act)
                            horas_desde_actualizacion = (datetime.now() - fecha_hist).total_seconds() / 3600
                            if horas_desde_actualizacion > 2:
                                logger.info(f"Historial antiguo ({horas_desde_actualizacion:.1f}h). Empezando fresco...")
                                return
                        except Exception:
                            pass

                    trades_previos = data.get('trades_vistos', [])
                    self.trades_vistos_ids = set(trades_previos[-5000:])
                    for tid in list(self.trades_vistos_ids):
                        self.trades_vistos_deque.append(tid)
                    logger.info(f"Historial cargado: {len(self.trades_vistos_ids)} trades previos")
            except Exception as e:
                logger.warning(f"No se pudo cargar historial: {e}")

    def _guardar_historial(self):
        try:
            with open(self.historial_path, 'w') as f:
                json.dump({
                    'trades_vistos': list(self.trades_vistos_ids),
                    'ultima_actualizacion': datetime.now().isoformat()
                }, f)
            logger.info(f"Historial guardado: {len(self.trades_vistos_ids)} trades")
        except Exception as e:
            logger.error(f"Error al guardar historial: {e}")

    # -------------------------------------------------------------------------
    # TIER CACHE PERSISTENTE (opción 2) + LOOKUP CHAIN (opción 1)
    # -------------------------------------------------------------------------

    def _cargar_tier_cache(self):
        """Carga el cache de tiers desde disco al iniciar la sesión."""
        try:
            if TIER_CACHE_PATH.exists():
                with open(TIER_CACHE_PATH, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                cutoff = datetime.now().timestamp() - TIER_CACHE_TTL_H * 3600
                cargados = 0
                for wallet, entry in raw.items():
                    cached_ts = entry.get('cached_ts', 0)
                    if cached_ts >= cutoff:
                        # Convertir al formato de analysis_cache en memoria
                        self.analysis_cache[wallet] = {
                            'tier': entry['tier'],
                            'score': entry.get('score', 0),
                            'sports_pnl': entry.get('sports_pnl'),
                            'cached_at': datetime.fromtimestamp(cached_ts),
                            'pnl': entry.get('pnl', 0),
                            'win_rate': entry.get('win_rate', 0.0),
                            'categories': entry.get('categories', []),
                        }
                        cargados += 1
                logger.info(f"Tier cache cargado: {cargados} traders (TTL {TIER_CACHE_TTL_H}h)")
        except Exception as e:
            logger.warning(f"No se pudo cargar tier cache: {e}")

    def _guardar_tier_cache(self):
        """Persiste el analysis_cache a disco (solo entradas con tier no vacío)."""
        try:
            TIER_CACHE_PATH.parent.mkdir(exist_ok=True)
            raw = {}
            for wallet, entry in self.analysis_cache.items():
                tier = entry.get('tier', '')
                if not tier:
                    continue
                cached_at = entry.get('cached_at', datetime.now())
                raw[wallet] = {
                    'tier': tier,
                    'score': entry.get('score', 0),
                    'sports_pnl': entry.get('sports_pnl'),
                    'cached_ts': cached_at.timestamp(),
                    'pnl': entry.get('pnl', 0),
                    'win_rate': entry.get('win_rate', 0.0),
                    'categories': entry.get('categories', []),
                }
            with open(TIER_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(raw, f)
            logger.info(f"Tier cache guardado: {len(raw)} traders")
        except Exception as e:
            logger.warning(f"Error guardando tier cache: {e}")

    def _buscar_tier_cached(self, wallet: str, display_name: str) -> str:
        """
        Devuelve el tier conocido para este wallet. Orden de prioridad:
          1. analysis_cache en memoria (incluye lo cargado desde disco al inicio)
          2. Consulta rápida a Supabase whale_signals (opción 1)
        Devuelve '' si no se encuentra nada.
        """
        # 1. Memoria (ya incluye el cache de disco cargado en __init__)
        cached = self.analysis_cache.get(wallet)
        if cached and cached.get('tier'):
            return cached['tier']

        # 2. Supabase — buscar tier más reciente para este wallet/display_name
        if self.supabase:
            try:
                resp = (
                    self.supabase.table('whale_signals')
                    .select('tier, detected_at')
                    .eq('display_name', display_name)
                    .not_.is_('tier', 'null')
                    .neq('tier', '')
                    .order('detected_at', desc=True)
                    .limit(1)
                    .execute()
                )
                rows = resp.data or []
                if rows and isinstance(rows[0], dict):
                    tier = str(rows[0].get('tier') or '')
                    if tier:
                        # Guardar en memoria para no volver a consultar
                        self.analysis_cache[wallet] = {
                            'tier': tier,
                            'score': 0,
                            'sports_pnl': None,
                            'cached_at': datetime.now(),
                        }
                        logger.info(f"Tier recuperado de Supabase para {display_name}: {tier}")
                        return tier
            except Exception as e:
                logger.debug(f"Error consultando tier en Supabase para {display_name}: {e}")

        return ''

    def signal_handler(self, sig, frame):
        print("\n\nDeteniendo monitor...")
        self.running = False

        uptime_segundos = int(time.time() - self.tiempo_inicio)
        horas = uptime_segundos // 3600
        minutos = (uptime_segundos % 3600) // 60
        segundos = uptime_segundos % 60

        self._guardar_historial()
        self._guardar_tier_cache()

        resumen = f"\n{'='*80}\n"
        resumen += "RESUMEN DE SESION (GOLD v3.0)\n"
        resumen += f"{'='*80}\n"
        resumen += f"Tiempo de monitoreo:     {horas}h {minutos}m {segundos}s\n"
        resumen += f"Total de ballenas:       {self.ballenas_detectadas}\n"
        resumen += f"Ballenas capturadas:     {self.ballenas_capturadas}\n"
        resumen += f"Ballenas ignoradas:      {self.ballenas_ignoradas}\n"

        if self.ballenas_detectadas > 0:
            promedio = self.suma_valores_ballenas / self.ballenas_detectadas
            resumen += f"Valor promedio:          ${promedio:,.2f} USD\n"
            resumen += f"Ballena mas grande:      ${self.ballena_maxima['valor']:,.2f} USD\n"
            resumen += f"   Mercado: {self.ballena_maxima['mercado'][:50]}...\n"
            resumen += f"   Wallet: {self.ballena_maxima['wallet'][:20]}...\n"

        resumen += f"Mercados monitoreados:   {len(self.markets_cache)}\n"
        resumen += f"\nArchivos guardados:\n"
        resumen += f"   - {self.filename_log} (log formateado)\n"
        resumen += f"   - {self.historial_path} (historial de trades)\n"

        if self.ballenas_por_mercado:
            resumen += f"\nTOP 5 MERCADOS CON MAS BALLENAS:\n"
            top_mercados = sorted(self.ballenas_por_mercado.items(), key=lambda x: x[1], reverse=True)[:5]
            for i, (mercado, count) in enumerate(top_mercados, 1):
                resumen += f"   {i}. {mercado[:60]}... ({count} ballenas)\n"

        resumen += f"\n{'='*80}\n"

        print(resumen)

        try:
            with open(self.filename_log, "a", encoding="utf-8") as f:
                f.write("\n" + resumen)
        except Exception as e:
            logger.error(f"Error al escribir resumen final: {e}")

        print("\nHasta luego!")
        sys.exit(0)

    def _limpiar_cache_mercados(self):
        if len(self.markets_cache) > MAX_CACHE_SIZE:
            logger.info("Limpiando cache de mercados antigua...")
            keys_to_remove = list(self.markets_cache.keys())[:int(MAX_CACHE_SIZE * 0.2)]
            for k in keys_to_remove:
                del self.markets_cache[k]

    def _parsear_timestamp(self, ts):
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

        return datetime.now()

    def obtener_trades(self):
        try:
            url = f"{DATA_API}/trades"
            params = {"limit": LIMIT_TRADES}
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de red/API: {e}")
            return []
        except json.JSONDecodeError:
            logger.error("Error decodificando JSON de la respuesta")
            return []

    def _obtener_info_mercado(self, trade):
        condition_id = trade.get('conditionId', trade.get('market', 'N/A'))

        if condition_id in self.markets_cache:
            return self.markets_cache[condition_id]

        info = {
            'question': trade.get('title', 'N/A'),
            'slug': trade.get('slug', 'N/A'),
            'market_slug': trade.get('eventSlug', trade.get('slug', 'N/A'))
        }

        self.markets_cache[condition_id] = info
        self._limpiar_cache_mercados()
        return info

    def _registrar_en_supabase(self, trade, valor, price, wallet, display_name, edge_result, es_nicho, classification=None):
        """Registra ballena en Supabase con info de clasificación v3.0"""
        if not self.supabase:
            return

        try:
            cached_analysis = self.analysis_cache.get(wallet, None)
            tier = cached_analysis.get('tier', '') if cached_analysis else ''

            edge_pct_val = float(edge_result.get('edge_pct', 0)) if edge_result.get('is_sports', False) else 0

            data = {
                'detected_at': datetime.now().isoformat(),
                'market_title': trade.get('title', ''),
                'condition_id': trade.get('conditionId', '') or trade.get('market', ''),
                'market_slug': trade.get('slug', '') or trade.get('eventSlug', ''),
                'side': trade.get('side', '').upper(),
                'poly_price': float(price),
                'valor_usd': float(valor),
                'display_name': display_name,
                'tier': tier,
                'edge_pct': edge_pct_val,
                'is_nicho': es_nicho,
                'outcome': trade.get('outcome', ''),
                'resolved_at': None,
                'result': None,
                'pnl_teorico': None,
                'signal_id': classification.get('signal_id', 'NONE') if classification else 'NONE',
                'action': classification.get('action', '') if classification else '',
                'confidence': classification.get('confidence', '') if classification else '',
                'win_rate_hist': classification.get('win_rate_hist', 0.0) if classification else 0.0,
                'expected_roi': classification.get('expected_roi', 0.0) if classification else 0.0,
            }

            try:
                result = self.supabase.table('whale_signals').insert(data).execute()
            except Exception as insert_err:
                err_str = str(insert_err).lower()
                if 'column' in err_str and ('condition_id' in err_str or 'market_slug' in err_str):
                    # Columnas aún no existen en Supabase — reintentar sin ellas
                    logger.info("Columnas condition_id/market_slug no existen aún — insertando sin ellas")
                    data_fb = {k: v for k, v in data.items() if k not in ('condition_id', 'market_slug')}
                    result = self.supabase.table('whale_signals').insert(data_fb).execute()
                else:
                    raise

            market_type = "deportiva" if edge_result.get('is_sports', False) else "general"
            logger.info(f"Ballena {market_type} registrada en Supabase: {data['market_title'][:50]}")

            # Devolver row ID si el tier está vacío, para poder actualizar cuando llegue el análisis
            if not tier and result.data:
                row = result.data[0]
                if isinstance(row, dict):
                    return row.get('id')

        except Exception as e:
            logger.warning(f"Error registrando en Supabase: {e}", exc_info=True)

        return None

    def _log_ballena(self, trade, valor, es_nicho=False, pct_mercado=0.0):
        self.suma_valores_ballenas += valor
        if valor > self.ballena_maxima['valor']:
            self.ballena_maxima = {
                'valor': valor,
                'mercado': trade.get('title', 'N/A'),
                'wallet': trade.get('proxyWallet', 'N/A')
            }

        emoji, categoria = "shark", "TIBURON"
        for tier_val, tier_emoji, tier_cat in WHALE_TIERS:
            if valor >= tier_val:
                emoji, categoria = tier_emoji, tier_cat
                break

        is_valid, reason = self.trade_filter.is_worth_copying(trade, valor)

        slug = trade.get('slug', '')
        cache_key = slug or trade.get('conditionId', trade.get('market', ''))
        market_volume = self.trade_filter.markets_cache.get(cache_key, 0)

        if not is_valid:
                self.ballenas_ignoradas += 1
                hora = datetime.now().strftime('%H:%M:%S')
                print(f"[{hora}] BALLENA IGNORADA — {categoria} ${valor:,.0f} — Razon: {reason} | Volumen: ${market_volume:,.0f}")
                return

        market_info = self._obtener_info_mercado(trade)
        ts = self._parsear_timestamp(trade.get('timestamp') or trade.get('createdAt'))
        side = trade.get('side', 'N/A').upper()
        price = float(trade.get('price', 0))
        outcome = trade.get('outcome', 'N/A')

        edge_result = self.sports_edge.check_edge(
            market_title=trade.get('title', ''),
            poly_price=price,
            side=side
        )

        self.ballenas_capturadas += 1

        mercado_nombre = market_info.get('question', 'Desconocido')
        self.ballenas_por_mercado[mercado_nombre] = self.ballenas_por_mercado.get(mercado_nombre, 0) + 1

        wallet = trade.get('proxyWallet', 'N/A')
        username = trade.get('name', '')
        pseudonym = trade.get('pseudonym', '')
        tx_hash = trade.get('transactionHash', 'N/A')

        if username and username != '':
            display_name = username
        elif pseudonym and pseudonym != '':
            display_name = pseudonym
        else:
            display_name = 'Anonimo'

        # Calcular condition_id temprano (necesario para consensus antes de classify)
        condition_id = trade.get('conditionId', trade.get('market', ''))

        # Obtener tier: memoria → cache disco → Supabase (opciones 1+2)
        trader_tier = self._buscar_tier_cached(wallet, display_name)
        cached_analysis = self.analysis_cache.get(wallet, {})
        cached_has_stats = cached_analysis.get('win_rate', 0.0) > 0

        # Opción 3: trader completamente nuevo — diferir clasificación hasta tener tier
        if not trader_tier:
            hora = datetime.now().strftime('%H:%M:%S')
            print(f"[{hora}] ⏳ DEFERRED {categoria} ${valor:,.0f} | {display_name} — analizando tier...")
            self._deferred_trades[wallet] = {
                'trade': trade, 'valor': valor, 'es_nicho': es_nicho,
                'price': price, 'ts': datetime.now(),
            }
            self._analizar_trader_async(
                wallet, display_name, trade.get('title', '').lower(), esperar_resultado=False, was_deferred=True, silent=True
            )
            return

        # Consenso multi-ballena (antes de classify para obtener opposite_tier)
        self.consensus.add(condition_id, side, valor, wallet, price, trader_tier, display_name)
        is_consensus, count, consensus_side, total_value = self.consensus.get_signal(condition_id)

        # FIX 3: Obtener tier del lado contrario para detección de conflicto HIGH RISK
        whale_entries_all = self.consensus.get_whale_entries(condition_id)
        opposite_entries = [e for e in whale_entries_all
                            if e['side'] != side and 'HIGH RISK' in e.get('tier', '').upper()]
        opposite_tier_for_conflict = opposite_entries[0]['tier'] if opposite_entries else ""

        # --- CLASIFICACIÓN v3.0 (con tier real disponible) ---
        classification = classify(
            market_title=trade.get('title', ''),
            tier=trader_tier,
            poly_price=price,
            is_nicho=es_nicho,
            valor_usd=valor,
            side=side,
            display_name=display_name,
            edge_pct=edge_result.get('edge_pct', 0.0),
            opposite_tier=opposite_tier_for_conflict,
        )

        # Evaluar S2+ y S1+ si hay consenso de 3+
        if is_consensus and count >= 3:
            whale_entries = self.consensus.get_whale_entries(condition_id)

            # S2+: Follow NBA consensus 0.50-0.60
            s2plus_result = classify_consensus(trade.get('title', ''), whale_entries)
            if s2plus_result.get('signal_id') == 'S2+':
                classification = {
                    **classification,
                    'signal_id': 'S2+',
                    'action': 'FOLLOW',
                    'confidence': 'HIGH',
                    'win_rate_hist': 78.1,
                    'reasoning': s2plus_result['reasoning'],
                }

            # S1+: Counter consensus zona 0.40-0.44 (tier independiente, override S2+ si ambos activan)
            s1plus_result = classify_consensus_counter(whale_entries)
            if s1plus_result.get('signal_id') == 'S1+':
                classification = {
                    **classification,
                    'signal_id': 'S1+',
                    'action': 'COUNTER',
                    'confidence': 'HIGH',
                    'win_rate_hist': s1plus_result['win_rate_hist'],
                    'reasoning': s1plus_result['reasoning'],
                }

        # Detección de coordinación
        self.coordination.add_trade(condition_id, wallet, side, valor)
        is_coordinated, coord_count, coord_desc, coord_wallets = self.coordination.detect_coordination(
            condition_id, wallet, side
        )

        # URLs
        profile_url = f"https://polymarket.com/profile/{wallet}" if wallet != 'N/A' else 'N/A'
        tx_url = f"https://polygonscan.com/tx/{tx_hash}" if tx_hash != 'N/A' else 'N/A'

        market_slug = market_info.get('market_slug', 'N/A')
        if market_slug != 'N/A':
            market_url = f"https://polymarket.com/event/{market_slug}"
        else:
            market_url = 'N/A'

        if tx_hash != 'N/A' and len(tx_hash) > 30:
            tx_hash_display = f"{tx_hash[:20]}...{tx_hash[-10:]}"
        else:
            tx_hash_display = tx_hash

        nicho_tag = f"  ⚡ NICHO ({pct_mercado:.1f}% del mercado)" if es_nicho else ""

        # --- BANNER DE ACCIÓN (letras grandes en consola) ---
        action = classification['action']
        action_banner = _BANNERS.get(action, '')

        # Línea de detalle de señal bajo el banner
        signal_detail = ""
        if classification['signal_id'] != 'NONE':
            signal_detail = (
                f"  Signal: {classification['signal_id']}  |  "
                f"Conf: {classification['confidence']}  |  "
                f"WR: {classification['win_rate_hist']:.1f}%  |  "
                f"ROI esperado: {classification['expected_roi']:+.1f}%\n"
            )
            for r in classification['reasoning']:
                signal_detail += f"  › {r}\n"
            for w in classification['warnings']:
                signal_detail += f"  ⚠ {w}\n"
        else:
            # IGNORE: siempre mostrar el motivo
            for r in classification['reasoning']:
                signal_detail += f"  › {r}\n"
            for w in classification['warnings']:
                signal_detail += f"  ⚠ {w}\n"
            if not signal_detail:
                signal_detail = "  › Sin señal activa (motivo no especificado)\n"

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
{action_banner}
{signal_detail}{'='*80}
"""

        if is_consensus:
            msg += f"🔥 SEÑAL CONSENSO: {count} ballenas → {consensus_side} | Total: ${total_value:,.0f}\n"

        if is_coordinated:
            msg += f"⚠️ GRUPO COORDINADO: {coord_desc} | Wallets: {coord_count}\n"

        if edge_result['is_sports'] and edge_result['pinnacle_price'] > 0:
            pp = edge_result['pinnacle_price']
            ep = edge_result['edge_pct']
            edge_icon = "✅" if ep > 3 else "⚠️" if ep > 0 else "❌"
            msg += f"""📊 ANÁLISIS DE ODDS:
   Pinnacle:     {pp:.2f} ({pp*100:.1f}%)
   Polymarket:   {price:.2f} ({price*100:.1f}%)
   Edge:         {ep:+.1f}% {edge_icon}
"""
            if edge_result.get('is_sucker_bet', False):
                msg += f"⚠️⚠️ SUCKER BET - Ballena pagando {abs(ep):.1f}% MÁS que Pinnacle\n"

        print(msg)
        with open(self.filename_log, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

        # === FILTRO ESTRATEGIA v3.0: solo notificar/analizar FOLLOW/COUNTER ===
        if classification['action'] == 'IGNORE':
            return

        # Registrar en Supabase SIEMPRE para trades FOLLOW/COUNTER (con tier del cache si disponible)
        row_id = self._registrar_en_supabase(trade, valor, price, wallet, display_name, edge_result, es_nicho, classification)
        # Si el tier estaba vacío al momento del insert, guardar el row ID para actualizarlo cuando llegue el análisis
        if row_id and wallet and wallet != 'N/A':
            self._pending_tier_supabase_ids[wallet] = row_id

        # Notificación por Telegram: PRIMERO el trade, LUEGO el análisis del trader
        if TELEGRAM_ENABLED:
            lado_texto = 'COMPRA' if side == 'BUY' else 'VENTA'

            # === BANNER EN LETRAS GRANDES (al inicio) ===
            telegram_msg = ""
            if classification['signal_id'] != 'NONE' and action in ('FOLLOW', 'COUNTER'):
                if action == 'FOLLOW':
                    telegram_msg += _TG_BANNER_FOLLOW + "\n"
                    telegram_msg += f"✅✅✅ <b>FOLLOW</b> — Signal <b>{classification['signal_id']}</b>"
                else:
                    telegram_msg += _TG_BANNER_COUNTER + "\n"
                    telegram_msg += f"🚨🚨🚨 <b>COUNTER</b> — Signal <b>{classification['signal_id']}</b>"
                telegram_msg += (
                    f"  |  Conf: <b>{classification['confidence']}</b>"
                    f"  |  WR: <b>{classification['win_rate_hist']:.1f}%</b>"
                    f"  |  ROI: <b>{classification['expected_roi']:+.1f}%</b>\n"
                )
                for r in classification['reasoning']:
                    telegram_msg += f"  › {r}\n"
                for w in classification['warnings']:
                    telegram_msg += f"  ⚠️ {w}\n"
                _is_wl_a = display_name.lower() in [w.lower() for w in WHITELIST_A]
                _is_wl_b = display_name.lower() in [w.lower() for w in WHITELIST_B]
                _is_bl   = display_name.lower() in [w.lower() for w in BLACKLIST]
                _stake_usd, _stake_pct, _stake_mods = calcular_stake(
                    signal_id=classification['signal_id'],
                    confidence=classification['confidence'],
                    bankroll=self.bankroll,
                    poly_price=price,
                    is_nicho=es_nicho,
                    is_whitelist_a=_is_wl_a,
                    is_whitelist_b=_is_wl_b,
                    is_blacklist=_is_bl,
                    action=classification['action'],
                    is_deferred=False,
                )
                telegram_msg += f"💰 <b>STAKE SUGERIDO: ${_stake_usd:.0f}</b> ({_stake_pct:.1f}% bankroll — conf {classification['confidence']})\n"
                if _stake_mods:
                    telegram_msg += f"   › {', '.join(_stake_mods)}\n"
                telegram_msg += "⚠️ Ajustar si hay posiciones abiertas\n"
                telegram_msg += "\n"
            elif classification['warnings']:
                for w in classification['warnings']:
                    telegram_msg += f"⚠️ {w}\n"
                telegram_msg += "\n"

            # === FORMATO IDÉNTICO A definitive_all_claude.py ===
            if es_nicho:
                telegram_msg += f"⚡ <b>ALERTA NICHO</b> — Alta concentración en mercado pequeño\n\n"

            telegram_msg += f"<b>{emoji} {categoria} CAPTURADA {emoji}</b>\n\n"

            nicho_tag_tg = f"  ⚡ <b>NICHO</b> ({pct_mercado:.1f}% del mercado)" if es_nicho else ""
            telegram_msg += f"💰 <b>Valor:</b> ${valor:,.2f}{nicho_tag_tg}\n"
            telegram_msg += f"📊 <b>Mercado:</b> {market_info.get('question', 'N/A')[:80]}\n"
            telegram_msg += f"🎯 <b>Outcome:</b> {outcome}\n"
            telegram_msg += f"📈 <b>Lado:</b> {lado_texto}\n"
            telegram_msg += f"💵 <b>Precio:</b> {price:.4f} ({price*100:.2f}%)\n"
            telegram_msg += f"📦 <b>Volumen:</b> ${market_volume:,.0f}\n"

            telegram_msg += f"\n👤 <b>TRADER:</b> {display_name}\n"
            if cached_has_stats:
                c_pnl = cached_analysis.get('pnl', 0)
                c_wr = cached_analysis.get('win_rate', 0.0)
                c_cats = cached_analysis.get('categories', [])
                c_pnl_str = f"+${c_pnl:,.0f}" if c_pnl >= 0 else f"-${abs(c_pnl):,.0f}"
                telegram_msg += f"   📊 WR: <b>{c_wr:.1f}%</b> | PnL: <b>{c_pnl_str}</b>\n"
                if c_cats:
                    telegram_msg += f"   🏆 Top especialidades:\n"
                    for cat in c_cats[:3]:
                        cp = cat.get('pnl', 0)
                        cp_str = f"+${cp:,.0f}" if cp >= 0 else f"-${abs(cp):,.0f}"
                        telegram_msg += f"      #{cat.get('rank', '?')} {cat.get('name', '?')}: {cp_str}\n"
            telegram_msg += f"   🔗 <a href='{profile_url}'>Ver perfil</a>\n"

            if edge_result['is_sports'] and edge_result['pinnacle_price'] > 0:
                pp = edge_result['pinnacle_price']
                ep = edge_result['edge_pct']
                edge_icon = "✅" if ep > 3 else "⚠️" if ep > 0 else "❌"
                telegram_msg += f"\n📊 <b>Odds Pinnacle:</b> {pp:.2f} ({pp*100:.1f}%)\n"
                telegram_msg += f"📊 <b>Edge:</b> {ep:+.1f}% {edge_icon}\n"

                if edge_result.get('is_sucker_bet', False):
                    telegram_msg += f"⚠️⚠️ <b>SUCKER BET</b> - Pagando {abs(ep):.1f}% MÁS que Pinnacle\n"

            if is_consensus:
                telegram_msg += f"\n🔥 <b>CONSENSO:</b> {count} ballenas → {consensus_side}\n"

            if is_coordinated:
                telegram_msg += f"⚠️ <b>COORDINACIÓN:</b> {coord_count} wallets en {coord_desc.split('en')[1] if 'en' in coord_desc else coord_desc}\n"

            telegram_msg += f"\n🔗 <a href='{market_url}'>Ver mercado</a>"

            # 1) Enviar alerta del trade PRIMERO
            send_telegram_notification(telegram_msg)

            if cached_has_stats:
                # Stats ya incluidos en el trade — marcar wallet como analizada para no re-scraper
                if not hasattr(self, '_wallets_analizadas'):
                    self._wallets_analizadas = set()
                self._wallets_analizadas.add(wallet)
            else:
                # Trader con señal activa pero sin stats en caché → scraper en background.
                # silent=False: cuando termine, envía follow-up con WR/PnL del trader.
                # (Solo llega aquí si hay FOLLOW/COUNTER activo, no para trades IGNORE.)
                self._analizar_trader_async(
                    wallet, display_name, trade.get('title', '').lower(),
                    esperar_resultado=False, silent=False,
                )

    def _obtener_historial_trader(self, display_name: str) -> dict:
        """Consulta Supabase para obtener historial de trades capturados de un trader."""
        if not self.supabase:
            return {}
        try:
            response = (
                self.supabase.table('whale_signals')
                .select('detected_at,market_title,side,poly_price,result,pnl_teorico,outcome')
                .eq('display_name', display_name)
                .order('detected_at', desc=True)
                .limit(20)
                .execute()
            )
            trades = response.data if response.data else []
            if not trades:
                return {}

            resolved = [t for t in trades if t.get('result')]
            wins = [t for t in resolved if t.get('result') == 'WIN']
            losses = [t for t in resolved if t.get('result') == 'LOSS']
            open_trades = [t for t in trades if not t.get('result')]
            pnl_total = sum(float(t.get('pnl_teorico', 0) or 0) for t in resolved)

            return {
                'total': len(trades),
                'resolved': len(resolved),
                'wins': len(wins),
                'losses': len(losses),
                'open': len(open_trades),
                'pnl_total': pnl_total,
                'recent': trades[:5],
            }
        except Exception as e:
            logger.warning(f"Error consultando historial de {display_name}: {e}")
            return {}

    def _analizar_trader_async(self, wallet, display_name, title_lower, esperar_resultado=False, was_deferred=False, silent=False):
        if wallet == 'N/A':
            return None

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
                        # Reintento 1: esperar 10s antes del siguiente intento
                        logger.info(f"⚠️ Scrape fallido para {display_name}, reintentando en 10s...")
                        time.sleep(10)
                        analyzer2 = TraderAnalyzer(wallet)
                        scrape_ok = analyzer2.scrape_polymarketanalytics()
                        if scrape_ok:
                            analyzer = analyzer2
                    if not scrape_ok:
                        # Reintento 2: esperar 20s más
                        logger.info(f"⚠️ Scrape fallido 2do intento para {display_name}, reintentando en 20s...")
                        time.sleep(20)
                        analyzer3 = TraderAnalyzer(wallet)
                        scrape_ok = analyzer3.scrape_polymarketanalytics()
                        if scrape_ok:
                            analyzer = analyzer3
                if not scrape_ok:
                    # Enviar aviso solo si todos los intentos fallaron
                    msg_sin_perfil = f"ℹ️ <b>SIN DATOS DE TRADER</b>\n\n"
                    msg_sin_perfil += f"👤 <b>{display_name}</b> (<code>{wallet[:10]}...</code>)\n"
                    msg_sin_perfil += f"📭 No se encontró perfil en PolymarketAnalytics.\n"
                    msg_sin_perfil += f"💡 Trader nuevo o sin historial registrado.\n"
                    msg_sin_perfil += f"🔗 <a href='https://polymarket.com/profile/{wallet}'>Ver perfil</a>"
                    if not silent:
                        send_telegram_notification(msg_sin_perfil)
                    logger.info(f"Sin perfil en analytics para {display_name} ({wallet[:10]}...)")
                    return

                # Completar campos que el scraper pudo no capturar por timeout de JS (<1s)
                analyzer._enrich_from_api()

                analyzer.calculate_profitability_score()
                analyzer.calculate_consistency_score()
                analyzer.calculate_risk_management_score()
                analyzer.calculate_experience_score()
                analyzer.calculate_final_score()

                tier = analyzer.scores.get('tier', '')
                total = analyzer.scores.get('total', 0)
                d = analyzer.scraped_data

                # Fix: detectar perfil vacío (caso betwick — score 0, trades 0, PnL 0)
                # También detectar traders sin trades resueltos aunque tengan ranking
                is_empty_profile = (
                    d.get('total_trades', 0) == 0 and
                    abs(d.get('pnl', 0)) == 0 and
                    d.get('win_rate', 0) == 0.0 and
                    total == 0
                )
                # IMPORTANTE: distinguir "scraper no capturó el dato" de "realmente 0 trades"
                # d.get('total_trades', 0) == 0 es falso positivo cuando el JS tarda > timeout
                # (el scraper retorna success=True con PnL/WR pero sin total_trades)
                scrape_got_trades = 'total_trades' in d
                has_no_resolved_trades = scrape_got_trades and d['total_trades'] == 0
                if is_empty_profile or has_no_resolved_trades:
                    msg_vacio = f"⚠️ <b>TRADER SIN TRADES RESUELTOS</b>\n\n"
                    msg_vacio += f"👤 <b>{display_name}</b> (<code>{wallet[:10]}...</code>)\n"
                    if d.get('rank'):
                        msg_vacio += f"🏆 <b>Ranking:</b> #{d.get('rank', 'N/A')}\n"
                    msg_vacio += f"📊 0 trades resueltos — WR histórico no disponible.\n"
                    msg_vacio += f"💡 Puede tener posiciones abiertas sin cerrar aún.\n"
                    msg_vacio += f"🔗 <a href='https://polymarket.com/profile/{wallet}'>Ver perfil</a>"
                    msg_vacio += f" | <a href='https://polymarketanalytics.com/traders/{wallet}'>Analytics</a>"
                    if not silent:
                        send_telegram_notification(msg_vacio)
                    logger.info(f"Sin trades resueltos para {display_name} ({wallet[:10]}...) rank=#{d.get('rank', 'N/A')}")
                    return

                sports_pnl = None
                if hasattr(analyzer, '_detect_sport_subtypes'):
                    sport_subtypes = analyzer._detect_sport_subtypes(d)
                    sports_pnl = sum(info['pnl'] for info in sport_subtypes.values()) if sport_subtypes else None

                self.analysis_cache[wallet] = {
                    'tier': tier,
                    'score': total,
                    'sports_pnl': sports_pnl,
                    'cached_at': datetime.now(),
                    'pnl': d.get('pnl', 0),
                    'win_rate': d.get('win_rate', 0.0),
                    'categories': d.get('categories', [])[:5],
                }

                # === ACTUALIZAR TIER EN SUPABASE (trade registrado con tier vacío) ===
                if tier and self.supabase:
                    pending_row_id = self._pending_tier_supabase_ids.pop(wallet, None)
                    if pending_row_id:
                        try:
                            self.supabase.table('whale_signals').update({'tier': tier}).eq('id', pending_row_id).execute()
                            logger.info(f"Tier actualizado en Supabase (id={pending_row_id}): {tier} para {display_name}")
                        except Exception as _e:
                            logger.warning(f"Error actualizando tier en Supabase (id={pending_row_id}): {_e}")

                # === RECLASIFICACIÓN RETROACTIVA ===
                # Si había un trade pendiente de este wallet (tier era '' cuando llegó),
                # re-clasificar ahora que conocemos el tier real.
                pending = self._pending_reclassification.pop(wallet, None)
                if pending and tier:
                    p_trade = pending['trade']
                    p_price = pending['price']
                    p_valor = pending['valor']
                    p_es_nicho = pending['es_nicho']
                    p_side = p_trade.get('side', '').upper()
                    p_wallet_addr = p_trade.get('proxyWallet', '')
                    p_display = (p_trade.get('name') or p_trade.get('pseudonym') or 'Anonimo')

                    p_edge_result = self.sports_edge.check_edge(
                        market_title=p_trade.get('title', ''),
                        poly_price=p_price,
                        side=p_side
                    )
                    reclass = classify(
                        market_title=p_trade.get('title', ''),
                        tier=tier,
                        poly_price=p_price,
                        is_nicho=p_es_nicho,
                        valor_usd=p_valor,
                        side=p_side,
                        display_name=p_display,
                        edge_pct=p_edge_result.get('edge_pct', 0.0),
                        opposite_tier='',
                    )
                    if reclass['action'] in ('FOLLOW', 'COUNTER'):
                        elapsed = (datetime.now() - pending['ts']).total_seconds()
                        elapsed_str = f"{int(elapsed)}s" if elapsed < 60 else f"{elapsed/60:.1f}min"
                        if reclass['action'] == 'FOLLOW':
                            banner = _TG_BANNER_FOLLOW
                            action_txt = "✅✅✅ <b>FOLLOW</b>"
                        else:
                            banner = _TG_BANNER_COUNTER
                            action_txt = "🚨🚨🚨 <b>COUNTER</b>"
                        msg = banner + "\n"
                        msg += f"⏱️ <b>SEÑAL RETROACTIVA</b> ({elapsed_str} de retraso — tier llegó tarde)\n"
                        msg += f"{action_txt} — Signal <b>{reclass['signal_id']}</b>"
                        msg += f"  |  Conf: <b>{reclass['confidence']}</b>"
                        msg += f"  |  WR: <b>{reclass['win_rate_hist']:.1f}%</b>"
                        msg += f"  |  ROI: <b>{reclass['expected_roi']:+.1f}%</b>\n"
                        for r in reclass['reasoning']:
                            msg += f"  › {r}\n"
                        msg += f"\n👤 <b>{p_display}</b> | {tier}\n"
                        msg += f"📈 {p_trade.get('title', '')[:60]}\n"
                        msg += f"💰 ${p_valor:,.0f} | {p_side} @ {p_price:.2f}\n"
                        msg += f"\n🔗 <a href='https://polymarket.com/profile/{p_wallet_addr}'>Ver perfil</a>"
                        msg += f" | <a href='https://polymarketanalytics.com/traders/{p_wallet_addr}'>Analytics</a>"
                        send_telegram_notification(msg)
                        logger.info(f"Señal retroactiva {reclass['action']} ({reclass['signal_id']}) para {p_display} — {elapsed_str}")
                        self._registrar_en_supabase(p_trade, p_valor, p_price, p_wallet_addr, p_display, p_edge_result, p_es_nicho, reclass)

                # === OPCIÓN 3: DEFERRED TRADE — primera señal, tier recién confirmado ===
                deferred = self._deferred_trades.pop(wallet, None)
                if was_deferred and not deferred:
                    # La entrada deferred expiró (cleanup la eliminó) antes de que el scraper terminara.
                    # El trade nunca fue clasificado — el análisis a continuación se enviaría sin señal.
                    logger.warning(f"Deferred expirado para {display_name} — trade perdido (timeout < scraper). "
                                   f"Considera aumentar DEFERRED_TIMEOUT_S (actual: {DEFERRED_TIMEOUT_S}s)")
                if deferred and tier:
                    d_trade    = deferred['trade']
                    d_price    = deferred['price']
                    d_valor    = deferred['valor']
                    d_es_nicho = deferred['es_nicho']
                    d_side     = d_trade.get('side', '').upper()
                    d_wallet   = d_trade.get('proxyWallet', '')
                    d_display  = (d_trade.get('name') or d_trade.get('pseudonym') or 'Anonimo')

                    d_edge = self.sports_edge.check_edge(
                        market_title=d_trade.get('title', ''),
                        poly_price=d_price,
                        side=d_side
                    )
                    d_class = classify(
                        market_title=d_trade.get('title', ''),
                        tier=tier,
                        poly_price=d_price,
                        is_nicho=d_es_nicho,
                        valor_usd=d_valor,
                        side=d_side,
                        display_name=d_display,
                        edge_pct=d_edge.get('edge_pct', 0.0),
                        opposite_tier='',
                    )
                    elapsed_d = (datetime.now() - deferred['ts']).total_seconds()
                    elapsed_d_str = f"{int(elapsed_d)}s" if elapsed_d < 60 else f"{elapsed_d/60:.1f}min"

                    # --- Consola: mismo formato que trade normal ---
                    d_emoji, d_categoria = "shark", "TIBURON"
                    for _tv, _te, _tc in WHALE_TIERS:
                        if d_valor >= _tv:
                            d_emoji, d_categoria = _te, _tc
                            break
                    d_market_info = self._obtener_info_mercado(d_trade)
                    d_market_slug = d_market_info.get('market_slug', '')
                    d_outcome     = d_trade.get('outcome', 'N/A')
                    d_lado_texto  = 'COMPRA' if d_side == 'BUY' else 'VENTA'
                    d_slug_key    = d_trade.get('slug', '') or d_trade.get('conditionId', d_trade.get('market', ''))
                    d_mkt_volume  = self.trade_filter.markets_cache.get(d_slug_key, 0)
                    d_ts_orig     = self._parsear_timestamp(d_trade.get('timestamp') or d_trade.get('createdAt'))
                    d_tx_hash     = d_trade.get('transactionHash', 'N/A')
                    d_tx_disp     = f"{d_tx_hash[:20]}...{d_tx_hash[-10:]}" if d_tx_hash != 'N/A' and len(d_tx_hash) > 30 else d_tx_hash
                    d_profile_url = f"https://polymarket.com/profile/{d_wallet}" if d_wallet != 'N/A' else 'N/A'
                    d_tx_url      = f"https://polygonscan.com/tx/{d_tx_hash}" if d_tx_hash != 'N/A' else 'N/A'
                    d_mkt_url     = f"https://polymarket.com/event/{d_market_slug}" if d_market_slug not in ('N/A', '', None) else 'N/A'
                    d_nicho_tag   = "  ⚡ NICHO" if d_es_nicho else ""
                    d_act_banner  = _BANNERS.get(d_class['action'], '')
                    d_sig_detail  = ""
                    if d_class['signal_id'] != 'NONE':
                        d_sig_detail = (
                            f"  Signal: {d_class['signal_id']}  |  "
                            f"Conf: {d_class['confidence']}  |  "
                            f"WR: {d_class['win_rate_hist']:.1f}%  |  "
                            f"ROI esperado: {d_class['expected_roi']:+.1f}%\n"
                        )
                        for r in d_class['reasoning']:
                            d_sig_detail += f"  › {r}\n"
                        for w in d_class['warnings']:
                            d_sig_detail += f"  ⚠ {w}\n"
                    else:
                        for r in d_class['reasoning']:
                            d_sig_detail += f"  › {r}\n"
                        for w in d_class['warnings']:
                            d_sig_detail += f"  ⚠ {w}\n"
                        if not d_sig_detail:
                            d_sig_detail = "  › Sin señal activa\n"
                    d_console_msg = f"""
{'='*80}
⏳ DEFERRED RESUELTO en {elapsed_d_str} — {d_emoji} {d_categoria} | {d_display} | {tier}
{'='*80}
💰 Valor: ${d_valor:,.2f} USD{d_nicho_tag}
📊 Mercado: {d_market_info.get('question', 'N/A')}
🔗 URL: {d_mkt_url}
🎯 Outcome: {d_outcome}
📈 Lado: {d_lado_texto}
💵 Precio: {d_price:.4f} ({d_price*100:.2f}%)
📦 Volumen: ${d_mkt_volume:,.2f}
🕐 Trade original: {d_ts_orig.strftime('%Y-%m-%d %H:%M:%S')}

👤 INFORMACIÓN DEL USUARIO:
   Nombre: {d_display}
   Wallet: {d_wallet}
   Perfil: {d_profile_url}
   TX Hash: {d_tx_disp}
   TX URL: {d_tx_url}
{'='*80}
{d_act_banner}
{d_sig_detail}{'='*80}
"""
                    print(d_console_msg)
                    with open(self.filename_log, "a", encoding="utf-8") as f:
                        f.write(d_console_msg + "\n")

                    if d_class['action'] in ('FOLLOW', 'COUNTER'):
                        d_banner = _TG_BANNER_FOLLOW if d_class['action'] == 'FOLLOW' else _TG_BANNER_COUNTER
                        d_action_txt = "✅✅✅ <b>FOLLOW</b>" if d_class['action'] == 'FOLLOW' else "🚨🚨🚨 <b>COUNTER</b>"
                        dmsg  = d_banner + "\n"
                        dmsg += f"⏳ <b>SEÑAL DEFERRED</b> (tier confirmado en {elapsed_d_str})\n"
                        dmsg += f"{d_action_txt} — Signal <b>{d_class['signal_id']}</b>"
                        dmsg += f"  |  Conf: <b>{d_class['confidence']}</b>"
                        dmsg += f"  |  WR: <b>{d_class['win_rate_hist']:.1f}%</b>"
                        dmsg += f"  |  ROI: <b>{d_class['expected_roi']:+.1f}%</b>\n"
                        for r in d_class['reasoning']:
                            dmsg += f"  › {r}\n"
                        for w in d_class['warnings']:
                            dmsg += f"  ⚠️ {w}\n"
                        _is_wl_a_d = d_display.lower() in [w.lower() for w in WHITELIST_A]
                        _is_wl_b_d = d_display.lower() in [w.lower() for w in WHITELIST_B]
                        _is_bl_d   = d_display.lower() in [w.lower() for w in BLACKLIST]
                        _d_stake_usd, _d_stake_pct, _d_stake_mods = calcular_stake(
                            signal_id=d_class['signal_id'],
                            confidence=d_class['confidence'],
                            bankroll=self.bankroll,
                            poly_price=d_price,
                            is_nicho=d_es_nicho,
                            is_whitelist_a=_is_wl_a_d,
                            is_whitelist_b=_is_wl_b_d,
                            is_blacklist=_is_bl_d,
                            action=d_class['action'],
                            is_deferred=True,
                        )
                        dmsg += f"💰 <b>STAKE SUGERIDO: ${_d_stake_usd:.0f}</b> ({_d_stake_pct:.1f}% bankroll — conf {d_class['confidence']})\n"
                        if _d_stake_mods:
                            dmsg += f"   › {', '.join(_d_stake_mods)}\n"
                        dmsg += "⚠️ Timing tardío (deferred) — verificar precio actual antes de entrar\n"
                        dmsg += f"\n👤 <b>{d_display}</b> | {tier}\n"
                        d_pnl = d.get('pnl', 0)
                        d_wr = d.get('win_rate', 0.0)
                        d_cats = d.get('categories', [])
                        if d_wr > 0:
                            d_pnl_str = f"+${d_pnl:,.0f}" if d_pnl >= 0 else f"-${abs(d_pnl):,.0f}"
                            dmsg += f"   📊 WR: <b>{d_wr:.1f}%</b> | PnL: <b>{d_pnl_str}</b>\n"
                            if d_cats:
                                dmsg += f"   🏆 Top especialidades:\n"
                                for cat in d_cats[:3]:
                                    cp = cat.get('pnl', 0)
                                    cp_str = f"+${cp:,.0f}" if cp >= 0 else f"-${abs(cp):,.0f}"
                                    dmsg += f"      #{cat.get('rank', '?')} {cat.get('name', '?')}: {cp_str}\n"
                        dmsg += f"📊 {d_trade.get('title', '')[:60]}\n"
                        dmsg += f"🎯 <b>Outcome:</b> {d_outcome}\n"
                        dmsg += f"📈 <b>Lado:</b> {d_lado_texto}\n"
                        dmsg += f"💰 ${d_valor:,.0f} @ {d_price:.2f}\n"
                        dmsg += f"\n🔗 <a href='https://polymarket.com/profile/{d_wallet}'>Ver perfil</a>"
                        dmsg += f" | <a href='https://polymarketanalytics.com/traders/{d_wallet}'>Analytics</a>"
                        if d_market_slug and d_market_slug not in ('N/A', ''):
                            dmsg += f"\n📊 <a href='https://polymarket.com/event/{d_market_slug}'>Ver mercado</a>"
                        send_telegram_notification(dmsg)
                        logger.info(f"Señal deferred {d_class['action']} ({d_class['signal_id']}) para {d_display} — {elapsed_d_str}")
                        self._registrar_en_supabase(d_trade, d_valor, d_price, d_wallet, d_display, d_edge, d_es_nicho, d_class)
                        return  # stats ya incluidos en el mensaje deferred — no enviar análisis separado
                    else:
                        logger.info(f"Deferred trade de {d_display} resuelto como IGNORE tras tier — sin señal")
                        return  # no enviar análisis para trades IGNORE

                tiers_buenos = ['SILVER', 'GOLD', 'DIAMOND', 'BRONZE', 'RISKY', 'STANDARD', 'HIGH RISK']
                tiers_advertencia = ['BOT', 'MM']

                es_tier_bueno = any(t in tier.upper() for t in tiers_buenos)
                es_bot_mm = any(t in tier.upper() for t in tiers_advertencia)

                if not (es_tier_bueno or es_bot_mm):
                    mensaje_simple = f"<b>TRADER NO RECOMENDADO</b>\n\n"
                    mensaje_simple += f"<b>{display_name}</b> ({wallet[:10]}...)\n"
                    mensaje_simple += f"<b>Tier:</b> {tier} (Score: {total}/100)\n"
                    mensaje_simple += f"<b>Recomendacion:</b> NO copiar este trade\n"
                    if not silent:
                        send_telegram_notification(mensaje_simple)
                    logger.info(f"Trader {display_name} ({wallet[:10]}...) -> {tier} (score: {total}) — Mensaje simple enviado")
                    return

                logger.info(f"Trader {display_name} ({wallet[:10]}...) -> {tier} (score: {total}) — Enviando analisis completo")

                rec = analyzer.generate_recommendation()

                if es_bot_mm and not es_tier_bueno:
                    tg = f"<b>ANALISIS DE TRADER - BOT/MARKET MAKER</b>\n\n"
                    tg += f"<b>ADVERTENCIA:</b> Este trader muestra patrones de bot o market maker\n"
                    tg += f"<b>Recomendacion:</b> No copiar - posible farming de liquidez o arbitraje automatizado\n\n"
                else:
                    tg = f"<b>ANALISIS DE TRADER</b>\n\n"

                # FIX 5: Verificar umbral mínimo de trades para señal confiable
                total_resolved = d.get('total_trades', 0)
                if total_resolved < TRADER_MIN_TRADES_FOR_SIGNAL:
                    low_trades_warning = (
                        f"\n⚠️ <b>MUESTRA INSUFICIENTE</b>: {total_resolved} trades resueltos "
                        f"(mínimo recomendado: {TRADER_MIN_TRADES_FOR_SIGNAL})\n"
                        f"WR histórico no es señal confiable todavía."
                    )
                else:
                    low_trades_warning = ""

                tg += f"<b>{display_name}</b> | {tier}\n"
                tg += f"<b>Score:</b> {total}/100\n"
                tg += f"<b>PnL:</b> ${d.get('pnl', 0):,.0f}\n"
                tg += f"<b>Win Rate:</b> {d.get('win_rate', 0):.1f}%\n"
                tg += low_trades_warning
                tg += f"<b>Trades:</b> {d.get('total_trades', 0):,}\n"
                tg += f"<b>Ranking:</b> #{d.get('rank', 'N/A')}\n"

                categories = d.get('categories', [])
                if categories:
                    tg += f"\n<b>ESPECIALIZACION:</b>\n"
                    sports_kw = ['win', 'vs', ' fc', 'nba', 'nfl', 'liga', 'premier',
                                 'serie a', 'bundesliga', 'ligue', 'ufc', 'nhl', 'mlb', 'tennis', 'cup']
                    is_current_sports = any(kw in title_lower for kw in sports_kw)

                    for cat in categories[:5]:
                        pnl = cat['pnl']
                        pnl_str = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
                        cat_name = cat['name']
                        tg += f"  #{cat['rank']} {cat_name}: {pnl_str}\n"

                        if is_current_sports and pnl > 0:
                            cat_lower = cat_name.lower()
                            if any(kw in cat_lower for kw in ['sport', 'football', 'soccer', 'basket', 'baseball',
                                                               'hockey', 'tennis', 'mma', 'boxing', 'cricket']):
                                tg += f"  <b>ESPECIALISTA en {cat_name} con {pnl_str}</b>\n"

                sport_subtypes = analyzer._detect_sport_subtypes(d)
                if sport_subtypes:
                    tg += f"\n<b>DETALLE DEPORTIVO:</b>\n"
                    for sport, info in sorted(sport_subtypes.items(), key=lambda x: x[1]['pnl'], reverse=True):
                        spnl = info['pnl']
                        spnl_str = f"+${spnl:,.0f}" if spnl >= 0 else f"-${abs(spnl):,.0f}"
                        tg += f"  {sport}: {spnl_str} ({info['count']} trades)\n"

                wins = d.get('biggest_wins', [])
                if wins:
                    tg += f"\n<b>Top Wins:</b>\n"
                    for w in wins[:3]:
                        tg += f"  +${w['amount']:,.0f} — {w['market'][:40]}\n"

                # Historial de trades capturados en Gold
                historial = self._obtener_historial_trader(display_name)
                if historial and historial.get('total', 0) > 0:
                    tg += f"\n<b>HISTORIAL EN GOLD ({historial['total']} trades):</b>\n"
                    if historial['resolved'] > 0:
                        wr_hist = historial['wins'] / historial['resolved'] * 100
                        pnl_str = f"+${historial['pnl_total']:,.0f}" if historial['pnl_total'] >= 0 else f"-${abs(historial['pnl_total']):,.0f}"
                        tg += f"  Resueltos: {historial['wins']}W / {historial['losses']}L — WR {wr_hist:.0f}% | PnL {pnl_str}\n"
                    if historial['open'] > 0:
                        tg += f"  Abiertos: {historial['open']} trades pendientes\n"
                    # Últimos 3 trades
                    for t in historial['recent'][:3]:
                        fecha = t.get('detected_at', '')[:10]
                        resultado = t.get('result', '—') or '—'
                        pnl_t = t.get('pnl_teorico')
                        pnl_t_str = f" ${pnl_t:+,.0f}" if pnl_t is not None else ""
                        tg += f"  {fecha} {t.get('side','?')} {t.get('market_title','')[:35]}... → {resultado}{pnl_t_str}\n"

                tg += f"\n<b>{rec[:100]}</b>\n"
                tg += f"\n<a href='https://polymarket.com/profile/{wallet}'>Ver perfil</a>"
                tg += f" | <a href='https://polymarketanalytics.com/traders/{wallet}'>Analytics</a>"

                if not silent:
                    send_telegram_notification(tg)

            except Exception as e:
                logger.error(f"Error en analisis de {wallet[:10]}...: {e}", exc_info=True)

        future = self.analysis_executor.submit(_run_analysis)

        if esperar_resultado:
            try:
                future.result(timeout=20)
                logger.info(f"Analisis completado en <20s para {wallet[:10]}...")
            except Exception:
                logger.info(f"Analisis tomando >20s para {wallet[:10]}... (continuara en background)")

        return future

    def ejecutar(self):
        telegram_status = "ACTIVO" if TELEGRAM_ENABLED else "DESACTIVADO"
        resumen = f"""\n{'='*80}
MONITOR GOLD v3.0 INICIADO
{'='*80}
Umbral de ballena:        ${self.umbral:,.2f} USD
Intervalo de polling:     {INTERVALO_NORMAL} segundos
Limite de trades/ciclo:   {LIMIT_TRADES}
Ventana de tiempo:        {VENTANA_TIEMPO//60} minutos (solo trades recientes)
Archivo de log:           {self.filename_log}
Trades en memoria:        {len(self.trades_vistos_ids)}
Notificaciones Telegram:  {telegram_status}
Esperando trades...
{'='*80}\n"""

        print(resumen)

        try:
            with open(self.filename_log, "w", encoding="utf-8") as f:
                f.write(resumen + "\n")
        except Exception as e:
            logger.error(f"Error al escribir resumen inicial: {e}")

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
                    trade_internal_id = trade.get('id', '')
                    outcome = trade.get('outcome', '')

                    if not trade_internal_id:
                        trade_internal_id = trade.get('transactionHash', str(time.time()))

                    trade_id = f"{trade_internal_id}_{outcome}"

                    if trade_id in self.trades_vistos_ids:
                        continue

                    ts = self._parsear_timestamp(trade.get('timestamp') or trade.get('createdAt'))
                    edad_trade = (datetime.now() - ts).total_seconds()

                    if edad_trade > VENTANA_TIEMPO:
                        if len(self.trades_vistos_deque) >= self.trades_vistos_deque.maxlen:
                            oldest_id = self.trades_vistos_deque[0]
                            self.trades_vistos_ids.discard(oldest_id)
                        self.trades_vistos_ids.add(trade_id)
                        self.trades_vistos_deque.append(trade_id)
                        continue

                    nuevos += 1

                    try:
                        size = float(trade.get('size', 0))
                        price = float(trade.get('price', 0))
                        valor = size * price
                    except (ValueError, TypeError):
                        continue

                    if len(self.trades_vistos_deque) >= self.trades_vistos_deque.maxlen:
                        oldest_id = self.trades_vistos_deque[0]
                        self.trades_vistos_ids.discard(oldest_id)

                    self.trades_vistos_ids.add(trade_id)
                    self.trades_vistos_deque.append(trade_id)

                    slug = trade.get('slug', '')
                    cache_key = slug or trade.get('conditionId', trade.get('market', ''))
                    market_volume = self.trade_filter.markets_cache.get(cache_key, 0)

                    es_ballena, es_nicho, pct_mercado = self._es_ballena(valor, market_volume)
                    if es_ballena:
                        trades_sobre_umbral += 1
                        self._log_ballena(trade, valor, es_nicho, pct_mercado)
                        ballenas_ciclo += 1
                        self.ballenas_detectadas += 1

            hora_actual = datetime.now().strftime("%H:%M:%S")
            print(f"[{hora_actual}] Ciclo #{ciclo} | Trades: {len(trades)} | Nuevos: {nuevos} | Sobre umbral: {trades_sobre_umbral} | Totales: {self.ballenas_detectadas} | Capturadas: {self.ballenas_capturadas} | Ignoradas: {self.ballenas_ignoradas}")

            if ciclo % 50 == 0:
                self._guardar_historial()

            # Limpiar deferred trades expirados cada ciclo (timeout es 35s, no esperar 5 min)
            if self._deferred_trades:
                _ahora_def = datetime.now()
                def_expirados = [w for w, d in self._deferred_trades.items()
                                 if (_ahora_def - d['ts']).total_seconds() > DEFERRED_TIMEOUT_S]
                for w in def_expirados:
                    d = self._deferred_trades.pop(w, None)
                    if d:
                        p_display = (d['trade'].get('name') or d['trade'].get('pseudonym') or 'Anonimo')
                        logger.warning(f"Deferred expirado sin tier ({DEFERRED_TIMEOUT_S}s): {p_display} — scraper falló, trade perdido")

            if ciclo % 100 == 0:
                logger.info(f"Heartbeat: {len(self.trades_vistos_ids)} trades en memoria. Cache: {len(self.markets_cache)} | Capturadas: {self.ballenas_capturadas} | Ignoradas: {self.ballenas_ignoradas}")
                ahora = datetime.now()
                # Limpiar pending reclassification expirados (> 10 min)
                expirados = [w for w, p in self._pending_reclassification.items()
                             if (ahora - p['ts']).total_seconds() > 600]
                for w in expirados:
                    self._pending_reclassification.pop(w, None)
                if expirados:
                    logger.info(f"Pending cleanup: {len(expirados)} trades expirados eliminados")
                # Invalidar analysis_cache con TTL > 6 horas (en memoria)
                ttl_6h = 6 * 3600
                caducados = [w for w, v in self.analysis_cache.items()
                             if (ahora - v.get('cached_at', ahora)).total_seconds() > ttl_6h]
                for w in caducados:
                    del self.analysis_cache[w]
                if caducados:
                    logger.info(f"Cache cleanup: {len(caducados)} tiers caducados eliminados")
                # Persistir tier cache a disco cada 100 ciclos (~5 min)
                self._guardar_tier_cache()

            elapsed = time.time() - start_time
            sleep_time = max(0.5, INTERVALO_NORMAL - elapsed)
            time.sleep(sleep_time)


# ============================================================================
# CLI MODES
# ============================================================================

def _run_demo():
    """Ejecuta los 10 test cases obligatorios del prompt."""
    tests = [
        ("Test 1: S1 zona fuerte (0.40-0.44)",
         {"market_title": "Jazz vs. Grizzlies", "tier": "HIGH RISK", "poly_price": 0.42, "is_nicho": False, "valor_usd": 8000}),
        ("Test 2: S1 zona normal (<0.40)",
         {"market_title": "Nuggets vs Warriors", "tier": "HIGH RISK", "poly_price": 0.35, "is_nicho": False, "valor_usd": 12000}),
        ("Test 3: S2 con tier HIGH RISK — DEBE PASAR",
         {"market_title": "Celtics vs. Lakers", "tier": "HIGH RISK", "poly_price": 0.55, "is_nicho": False, "valor_usd": 9000}),
        ("Test 4: Crypto intraday",
         {"market_title": "Bitcoin Up or Down - March 1, 2AM ET", "tier": "GOLD", "poly_price": 0.52, "is_nicho": False, "valor_usd": 4500}),
        ("Test 5: Crypto NO intraday",
         {"market_title": "Will Bitcoin reach $100K by March 2026?", "tier": "SILVER", "poly_price": 0.55, "is_nicho": False, "valor_usd": 5000}),
        ("Test 6: Futbol SILVER con WR actualizado",
         {"market_title": "Will FC Barcelona win on 2026-03-01?", "tier": "SILVER", "poly_price": 0.62, "is_nicho": False, "valor_usd": 6000}),
        ("Test 7: zona muerta 0.45-0.49",
         {"market_title": "Magic vs. Suns", "tier": "HIGH RISK", "poly_price": 0.48, "is_nicho": False, "valor_usd": 5500}),
        ("Test 8: precio > 0.85",
         {"market_title": "Spurs vs Pistons", "tier": "SILVER", "poly_price": 0.90, "is_nicho": False, "valor_usd": 8000}),
        ("Test 9: Whitelist A boost",
         {"market_title": "Pacers vs. Wizards", "tier": "BOT/MM", "poly_price": 0.55, "is_nicho": False, "valor_usd": 7000, "side": "BUY", "display_name": "hioa"}),
        ("Test 10: Blacklist no cancela S2 pero genera warning",
         {"market_title": "Knicks vs. Bulls", "tier": "BRONZE", "poly_price": 0.58, "is_nicho": False, "valor_usd": 4000, "side": "BUY", "display_name": "sovereign2013"}),
    ]

    print(f"\n{'='*80}")
    print("GOLD CLASSIFY v3.0 — DEMO (10 test cases)")
    print(f"{'='*80}\n")

    for name, kwargs in tests:
        result = classify(**kwargs)
        print(f"--- {name} ---")
        print(f"  Action:     {result['action']}")
        print(f"  Signal:     {result['signal_id']}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  WR Hist:    {result['win_rate_hist']:.1f}%")
        print(f"  ROI:        {result['expected_roi']:.1f}%")
        print(f"  Payout:     {result['payout_mult']:.2f}x")
        print(f"  Category:   {result['category']}")
        if result['reasoning']:
            print(f"  Reasoning:")
            for r in result['reasoning']:
                print(f"    > {r}")
        if result['warnings']:
            print(f"  Warnings:")
            for w in result['warnings']:
                print(f"    ! {w}")
        print()


def _run_single(market_title, tier, price, valor, side="BUY", name="Unknown", nicho=False, edge=0.0):
    """Clasifica un solo mercado."""
    result = classify(
        market_title=market_title,
        tier=tier,
        poly_price=price,
        is_nicho=nicho,
        valor_usd=valor,
        side=side,
        display_name=name,
        edge_pct=edge,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _run_interactive():
    """Modo interactivo: el usuario ingresa datos manualmente."""
    print(f"\n{'='*80}")
    print("GOLD CLASSIFY v3.0 — MODO INTERACTIVO")
    print(f"{'='*80}")
    print("Escribe 'q' para salir.\n")

    while True:
        try:
            market_title = input("Mercado (titulo): ").strip()
            if market_title.lower() == 'q':
                break
            tier = input("Tier (ej: HIGH RISK, SILVER, GOLD, BRONZE): ").strip()
            price = float(input("Precio Polymarket (0.0-1.0): ").strip())
            valor = float(input("Valor USD: ").strip())
            side = input("Side (BUY/SELL) [BUY]: ").strip().upper() or "BUY"
            name = input("Nombre trader [Unknown]: ").strip() or "Unknown"
            nicho = input("Es nicho? (s/n) [n]: ").strip().lower() == 's'
            edge = float(input("Edge % [0]: ").strip() or "0")

            result = classify(
                market_title=market_title,
                tier=tier,
                poly_price=price,
                is_nicho=nicho,
                valor_usd=valor,
                side=side,
                display_name=name,
                edge_pct=edge,
            )

            print(f"\n--- RESULTADO ---")
            print(f"  Action:     {result['action']}")
            print(f"  Signal:     {result['signal_id']}")
            print(f"  Confidence: {result['confidence']}")
            print(f"  WR Hist:    {result['win_rate_hist']:.1f}%")
            print(f"  ROI:        {result['expected_roi']:.1f}%")
            print(f"  Payout:     {result['payout_mult']:.2f}x")
            print(f"  Category:   {result['category']}")
            if result['reasoning']:
                for r in result['reasoning']:
                    print(f"    > {r}")
            if result['warnings']:
                for w in result['warnings']:
                    print(f"    ! {w}")
            print()

        except (ValueError, EOFError):
            print("Error en entrada. Intenta de nuevo.\n")
        except KeyboardInterrupt:
            break

    print("Saliendo del modo interactivo.")


def _run_csv(csv_path):
    """Lee un CSV con columnas: market_title,tier,poly_price,valor_usd,side,display_name,is_nicho,edge_pct
       y clasifica cada fila."""
    print(f"\n{'='*80}")
    print(f"GOLD CLASSIFY v3.0 — CSV MODE: {csv_path}")
    print(f"{'='*80}\n")

    results = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            result = classify(
                market_title=row.get('market_title', ''),
                tier=row.get('tier', ''),
                poly_price=float(row.get('poly_price', 0)),
                is_nicho=row.get('is_nicho', '').lower() in ('true', '1', 'yes', 's'),
                valor_usd=float(row.get('valor_usd', 5000)),
                side=row.get('side', 'BUY'),
                display_name=row.get('display_name', 'Unknown'),
                edge_pct=float(row.get('edge_pct', 0)),
            )
            results.append({**row, **result})

            print(f"{result['signal_id']:6s} | {result['action']:7s} | {result['confidence']:6s} | "
                  f"WR:{result['win_rate_hist']:5.1f}% | ROI:{result['expected_roi']:6.1f}% | "
                  f"{row.get('market_title', '')[:50]}")

    # Guardar resultados
    out_path = csv_path.replace('.csv', '_classified.csv')
    if results:
        fieldnames = list(results[0].keys())
        # Convertir lists to strings for CSV
        for r in results:
            r['reasoning'] = ' | '.join(r.get('reasoning', []))
            r['warnings'] = ' | '.join(r.get('warnings', []))

        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nResultados guardados en: {out_path}")
    print(f"\nTotal clasificados: {len(results)}")


def main():
    parser = argparse.ArgumentParser(description="Polymarket Gold Whale Detector v3.0")
    parser.add_argument('--csv', type=str, help='Clasificar trades desde CSV')
    parser.add_argument('--interactive', action='store_true', help='Modo interactivo')
    parser.add_argument('--single', nargs='*', help='Clasificar un mercado: "titulo" tier precio valor [side] [nombre]')
    parser.add_argument('--demo', action='store_true', help='Ejecutar test cases de demo')
    parser.add_argument('--live', action='store_true', help='Modo live (monitor de ballenas)')
    args = parser.parse_args()

    if args.csv:
        _run_csv(args.csv)
    elif args.interactive:
        _run_interactive()
    elif args.single:
        parts = args.single
        if len(parts) < 4:
            print("Uso: --single 'titulo' tier precio valor [side] [nombre]")
            sys.exit(1)
        _run_single(
            market_title=parts[0],
            tier=parts[1],
            price=float(parts[2]),
            valor=float(parts[3]),
            side=parts[4] if len(parts) > 4 else "BUY",
            name=parts[5] if len(parts) > 5 else "Unknown",
        )
    elif args.demo:
        _run_demo()
    elif args.live:
        print("\nPOLYMARKET WHALE DETECTOR — GOLD EDITION v3.0")
        while True:
            try:
                val = input("Umbral (USD) [Enter para 2500]: ").strip()
                umbral = float(val) if val else 2500.0
                if umbral > 0:
                    break
            except ValueError:
                print("Numero invalido")

        detector = GoldWhaleDetector(umbral)
        detector.ejecutar()
    else:
        # Por defecto: demo
        _run_demo()


if __name__ == "__main__":
    main()
