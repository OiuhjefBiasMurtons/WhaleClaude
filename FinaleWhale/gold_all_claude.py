#!/usr/bin/env python3
"""
Polymarket Gold All Markets Whale Detector v4.0
Basado en definitive_all_claude.py con filtros avanzados de señales (S1-S6),
whitelists/blacklists de traders, resolución de conflictos y warnings.

Consolida 515 señales analizadas (Feb 2026).

CHANGELOG:
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
WHITELIST_A = ['hioa', 'KeyTransporter']
WHITELIST_B = ['elkmonkey', 'gmanas', 'swisstony', 'synnet']
BLACKLIST = ['sovereign2013', 'BITCOINTO500K', '432614799197', 'xdoors']
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
    'inter', 'milan', 'psg', 'lyon', 'lille', 'chelsea', 'arsenal',
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

    if any(kw in title_lower for kw in SOCCER_KEYWORDS):
        return "SOCCER"

    if any(kw in title_lower for kw in ESPORTS_KEYWORDS):
        return "ESPORTS"

    if any(kw in title_lower for kw in TENNIS_KEYWORDS):
        return "TENNIS"

    if any(kw in title_lower for kw in MMA_KEYWORDS):
        return "MMA"

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

    category = _detect_category(market_title)
    result["category"] = category

    # Calcular payout
    if poly_price > 0:
        result["payout_mult"] = round((1.0 / poly_price) - 1, 2)

    # --- WARNINGS GLOBALES ---

    # FIX 2: edge_pct llega de sports_edge_detector con convención (pinnacle - poly)*100
    # edge_pct < 0 = poly más caro que Pinnacle = sucker bet (ya marcado por is_sucker_bet)
    # No añadimos warning aquí: sports_edge_detector lo comunica vía is_sucker_bet
    # y se muestra explícitamente en el output de Telegram.

    # Warning: precio > 0.85
    if poly_price > 0.85:
        result["warnings"].append(
            "Precio >0.85: WR bueno (78.6%) pero payout destruye EV. "
            f"$10 a {poly_price:.2f} gana solo ${(1/poly_price - 1)*10:.2f}."
        )

    # Warning: zona muerta 0.45-0.49
    if 0.45 <= poly_price <= 0.49:
        result["warnings"].append(
            "Precio en zona 0.45-0.49: underdog sin señal activa. No activa S1 ni S2."
        )

    # Warning: trader en blacklist
    if display_name_lower in blacklist_lower:
        result["warnings"].append(
            f"Trader {display_name} está en BLACKLIST. Evaluar counter."
        )

    # --- FILTRO MÍNIMO DE CAPITAL ---
    if valor_usd < 3000:
        result["reasoning"].append(
            f"Capital ${valor_usd:,.0f} < $3K mínimo para señal. "
            f"Ballena registrada pero sin acción recomendada."
        )
        return result

    # --- DETECCIÓN DE SEÑALES ---
    signals = []

    # S1: Counter HIGH RISK (precio < 0.45)
    if 'HIGH RISK' in tier_upper and poly_price < 0.45:
        if 0.40 <= poly_price < 0.45:
            signals.append({
                "id": "S1",
                "action": "COUNTER",
                "confidence": "HIGH",
                "win_rate": 88.2,
                "reasoning": f"S1 zona fuerte: Counter HIGH RISK a {poly_price:.2f} (WR 88.2%, N=17)",
            })
        elif poly_price < 0.40:  # poly_price < 0.40
            signals.append({
                "id": "S1",
                "action": "COUNTER",
                "confidence": "LOW",
                "win_rate": 60.0,
                "reasoning": f"S1 zona baja: Counter HIGH RISK a {poly_price:.2f} (WR 60.0%, N=14, mezcla deportes)",
            })

    # S1B: Counter Soccer cualquier tier, precio < 0.40 (WR 75.0%, N=24)
    # Las ballenas comprando Soccer a precio muy bajo son malas predictorias.
    # No requiere ser HIGH RISK — el patrón aplica a todos los tiers en Soccer.
    if category == "SOCCER" and poly_price < 0.40:
        signals.append({
            "id": "S1B",
            "action": "COUNTER",
            "confidence": "MEDIUM",
            "win_rate": 75.0,
            "reasoning": f"S1B: Counter Fútbol a {poly_price:.2f} cualquier tier (WR 75.0%, N=24)",
        })

    # S2: Follow NBA 0.50-0.60, excluir HIGH RISK (zona core, datos sólidos)
    # HIGH RISK NBA: WR 49.4%, PnL -818 → destruye el alpha de la categoría.
    # Zona 0.50-0.60: WR 72%, rango validado con mayor volumen de señales.
    if category == "NBA" and 0.50 <= poly_price <= 0.60 and 'HIGH RISK' not in tier_upper:
        confidence = "MEDIUM"
        reasoning = f"S2: Follow NBA a {poly_price:.2f} (WR 72%, rango 0.50-0.60, excl. HIGH RISK)"

        # Whitelist A boost
        if display_name_lower in whitelist_a_lower:
            confidence = "HIGH"
            reasoning += f" | Whitelist A ({display_name}) → stake 1.5x"
        elif display_name_lower in whitelist_b_lower:
            reasoning += f" | Whitelist B ({display_name}) → ejecutar normal"

        signals.append({
            "id": "S2",
            "action": "FOLLOW",
            "confidence": confidence,
            "win_rate": 72.0,
            "reasoning": reasoning,
        })

    # S2B: Follow NBA 0.60-0.80, excluir HIGH RISK (zona extendida, pendiente más datos)
    # Prometedor (WR 69.6%) pero la muestra por tier se fragmenta en este rango.
    # Tratar con stake reducido (0.5x) hasta consolidar n suficiente.
    if category == "NBA" and 0.60 < poly_price <= 0.80 and 'HIGH RISK' not in tier_upper:
        confidence = "LOW"
        reasoning = f"S2B: Follow NBA a {poly_price:.2f} (WR 69.6%, rango 0.60-0.80, stake 0.5x, excl. HIGH RISK)"

        if display_name_lower in whitelist_a_lower:
            confidence = "MEDIUM"
            reasoning += f" | Whitelist A ({display_name}) → stake normal"
        elif display_name_lower in whitelist_b_lower:
            reasoning += f" | Whitelist B ({display_name})"

        signals.append({
            "id": "S2B",
            "action": "FOLLOW",
            "confidence": confidence,
            "win_rate": 69.6,
            "reasoning": reasoning,
        })

    # S3: Follow Nicho — solo Esports y categorías no-core (excluye NBA, Soccer, Crypto)
    # Datos confirman que Nicho Soccer WR 43.5% (PnL -618) y Nicho Crypto WR 33.3% (PnL -200).
    # El filtro nicho solo tiene valor predictivo real en NBA (cubierto por S2) y Esports.
    # Soccer nicho tiene reglas propias en S5/S6.
    _S3_EXCLUDED = ("NBA", "SOCCER", "CRYPTO")
    if is_nicho and category not in _S3_EXCLUDED and 0.50 <= poly_price < 0.85:
        signals.append({
            "id": "S3",
            "action": "FOLLOW",
            "confidence": "LOW",
            "win_rate": 56.5,
            "reasoning": f"S3: Follow Nicho ({category}) a {poly_price:.2f} (stake 0.5x, WR 56.5%)",
        })

    # S4: Counter Crypto (solo intraday Up/Down automático)
    if category == "CRYPTO":
        if _is_crypto_intraday(market_title):
            signals.append({
                "id": "S4",
                "action": "COUNTER",
                "confidence": "MEDIUM",
                "win_rate": 65.0,
                "reasoning": f"S4: Counter Crypto intraday Up/Down a {poly_price:.2f}",
            })
        else:
            result["warnings"].append(
                "S4 aplica solo a crypto intraday Up/Down. Para crypto largo plazo, validar manualmente."
            )

    # S5 (REFACTORIZADA v4.0): Follow Soccer 0.60-0.80, excluir GOLD y RISKY
    # CORRECCIÓN CRÍTICA: la señal anterior estaba invertida. El dato real muestra que
    # Soccer SILVER en 0.50-0.65 la ballena GANA el 58.3% (WR follow, no counter).
    # Con el rango ampliado 0.60-0.80 excl. GOLD/RISKY: WR 75.9%, N=29.
    # GOLD destruye el grupo (GOLD Soccer tiene WR negativo en 0.60-0.80).
    # RISKY Soccer también tiene WR negativo en ese rango.
    if category == "SOCCER" and 0.60 <= poly_price < 0.80:
        if 'GOLD' not in tier_upper and 'RISKY' not in tier_upper:
            signals.append({
                "id": "S5",
                "action": "FOLLOW",
                "confidence": "MEDIUM",
                "win_rate": 75.9,
                "reasoning": (
                    f"S5: Follow Fútbol {tier} a {poly_price:.2f} "
                    f"(WR 75.9%, N=29, excl. GOLD/RISKY)"
                ),
            })

    # S6 — HIPÓTESIS PENDIENTE DE VALIDACIÓN (no implementada)
    # Follow Soccer nicho GOLD/SILVER precio ≥ 0.65: WR 80%, pero N=5.
    # Con n<20 el dato es estadísticamente irrelevante. Implementar cuando n≥20.

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

        # COUNTER — S1 (HIGH RISK precio <0.45)
        if 'HIGH RISK' not in tier_upper:
            counter_blocks.append(f"S1 necesita HIGH RISK (tier={tier or 'desconocido'})")
        elif poly_price >= 0.45:
            counter_blocks.append(f"S1 necesita precio <0.45 (es {poly_price:.2f})")
        # COUNTER — S1B (Soccer precio <0.40)
        if category != "SOCCER":
            counter_blocks.append(f"S1B necesita SOCCER (es {category})")
        elif poly_price >= 0.40:
            counter_blocks.append(f"S1B necesita precio <0.40 (es {poly_price:.2f})")
        # COUNTER — S4 (Crypto intraday)
        if category != "CRYPTO":
            counter_blocks.append(f"S4 necesita CRYPTO (es {category})")
        elif not _is_crypto_intraday(market_title):
            counter_blocks.append("S4 necesita intraday Up/Down")

        # FOLLOW — S2 (NBA 0.50-0.60 excl. HIGH RISK — zona core)
        if category != "NBA":
            follow_blocks.append(f"S2/S2B necesita NBA (es {category})")
        elif 'HIGH RISK' in tier_upper:
            follow_blocks.append("S2/S2B excluye HIGH RISK en NBA")
        elif not (0.50 <= poly_price <= 0.80):
            follow_blocks.append(f"S2 necesita precio 0.50-0.60 (es {poly_price:.2f}), S2B necesita 0.60-0.80")
        elif not (0.50 <= poly_price <= 0.60):
            follow_blocks.append(f"S2 necesita precio 0.50-0.60 (es {poly_price:.2f}) — ver S2B para 0.60-0.80")
        # FOLLOW — S3 (Nicho excl. NBA/Soccer/Crypto)
        if not is_nicho:
            follow_blocks.append("S3 necesita mercado nicho")
        elif category in ("NBA", "SOCCER", "CRYPTO"):
            follow_blocks.append(f"S3 excluye {category} (NBA→S2, Soccer→S5, Crypto→S4)")
        elif not (0.50 <= poly_price < 0.85):
            follow_blocks.append(f"S3 necesita precio 0.50-0.85 (es {poly_price:.2f})")
        # FOLLOW — S5 (Soccer 0.60-0.80 excl. GOLD/RISKY)
        if category != "SOCCER":
            follow_blocks.append(f"S5 necesita SOCCER (es {category})")
        elif 'GOLD' in tier_upper or 'RISKY' in tier_upper:
            follow_blocks.append(f"S5 excluye GOLD/RISKY en Soccer (tier={tier})")
        elif not (0.60 <= poly_price < 0.80):
            follow_blocks.append(f"S5 necesita precio 0.60-0.80 (es {poly_price:.2f})")

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
    s1   = next((s for s in signals if s["id"] == "S1"),   None)
    s1b  = next((s for s in signals if s["id"] == "S1B"),  None)
    s2   = next((s for s in signals if s["id"] == "S2"),   None)
    s2b  = next((s for s in signals if s["id"] == "S2B"),  None)
    s3   = next((s for s in signals if s["id"] == "S3"),   None)
    s4   = next((s for s in signals if s["id"] == "S4"),   None)
    s5   = next((s for s in signals if s["id"] == "S5"),   None)

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


def classify_consensus_counter(whale_entries: list) -> dict:
    """
    S1+: Counter consensus en zona 0.40-0.44, independiente del tier y la categoría.

    Cuando 3+ ballenas compran en esta zona, la señal de consenso supera los datos
    individuales de S1 (WR 88.2% zona fuerte). No requiere que ninguna sea HIGH RISK:
    el consenso por sí solo es la señal.
    """
    if len(whale_entries) < 3:
        return {"signal_id": "NONE", "action": "IGNORE",
                "reasoning": ["S1+: necesita 3+ ballenas"]}

    # Agrupar por lado
    sides = {}
    for e in whale_entries:
        sides.setdefault(e.get("side", "BUY"), []).append(e)

    for entries in sides.values():
        prices_en_zona = [e["poly_price"] for e in entries if 0.40 <= e["poly_price"] < 0.45]
        if len(prices_en_zona) >= 3:
            avg = sum(prices_en_zona) / len(prices_en_zona)
            return {
                "signal_id": "S1+",
                "action": "COUNTER",
                "confidence": "HIGH",
                "win_rate_hist": 88.2,
                "reasoning": [
                    f"S1+ Consensus COUNTER: {len(prices_en_zona)} ballenas en zona 0.40–0.44 "
                    f"(prom. {avg:.2f}) | Tier independiente"
                ],
                "warnings": [],
            }

    return {"signal_id": "NONE", "action": "IGNORE",
            "reasoning": ["S1+: sin 3+ ballenas en zona 0.40-0.44"]}


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

    def signal_handler(self, sig, frame):
        print("\n\nDeteniendo monitor...")
        self.running = False

        uptime_segundos = int(time.time() - self.tiempo_inicio)
        horas = uptime_segundos // 3600
        minutos = (uptime_segundos % 3600) // 60
        segundos = uptime_segundos % 60

        self._guardar_historial()

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

            result = self.supabase.table('whale_signals').insert(data).execute()

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

        # Obtener tier del trader (del cache si ya fue analizado antes)
        cached_analysis = self.analysis_cache.get(wallet, None)
        trader_tier = cached_analysis.get('tier', '') if cached_analysis else ''

        # Consenso multi-ballena (antes de classify para obtener opposite_tier)
        self.consensus.add(condition_id, side, valor, wallet, price, trader_tier, display_name)
        is_consensus, count, consensus_side, total_value = self.consensus.get_signal(condition_id)

        # FIX 3: Obtener tier del lado contrario para detección de conflicto HIGH RISK
        whale_entries_all = self.consensus.get_whale_entries(condition_id)
        opposite_entries = [e for e in whale_entries_all
                            if e['side'] != side and 'HIGH RISK' in e.get('tier', '').upper()]
        opposite_tier_for_conflict = opposite_entries[0]['tier'] if opposite_entries else ""

        # --- CLASIFICACIÓN v3.0 (con tier real si está disponible) ---
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

        # Si tier es desconocido y la acción es IGNORE, guardar trade para re-clasificación retroactiva
        # (el análisis async se lanza más abajo y llenará analysis_cache → disparará el check)
        if not trader_tier and classification['action'] == 'IGNORE':
            self._pending_reclassification[wallet] = {
                'trade': trade, 'valor': valor, 'es_nicho': es_nicho,
                'price': price, 'reason': 'empty_tier', 'ts': datetime.now(),
            }

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

            # Información básica del trader (sin análisis aún)
            telegram_msg += f"\n👤 <b>TRADER:</b> {display_name}\n"
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

            # 2) Lanzar análisis del trader en background (enviará su propio mensaje después)
            self._analizar_trader_async(
                wallet, display_name, trade.get('title', '').lower(),
                esperar_resultado=False,
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

    def _analizar_trader_async(self, wallet, display_name, title_lower, esperar_resultado=False):
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

                tiers_buenos = ['SILVER', 'GOLD', 'DIAMOND', 'BRONZE', 'RISKY', 'STANDARD', 'HIGH RISK']
                tiers_advertencia = ['BOT', 'MM']

                es_tier_bueno = any(t in tier.upper() for t in tiers_buenos)
                es_bot_mm = any(t in tier.upper() for t in tiers_advertencia)

                if not (es_tier_bueno or es_bot_mm):
                    mensaje_simple = f"<b>TRADER NO RECOMENDADO</b>\n\n"
                    mensaje_simple += f"<b>{display_name}</b> ({wallet[:10]}...)\n"
                    mensaje_simple += f"<b>Tier:</b> {tier} (Score: {total}/100)\n"
                    mensaje_simple += f"<b>Recomendacion:</b> NO copiar este trade\n"
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

            if ciclo % 100 == 0:
                logger.info(f"Heartbeat: {len(self.trades_vistos_ids)} trades en memoria. Cache: {len(self.markets_cache)} | Capturadas: {self.ballenas_capturadas} | Ignoradas: {self.ballenas_ignoradas}")
                # BUG-7: Limpiar pending trades sin resolver (análisis falló o tardó > 10 min)
                ahora = datetime.now()
                expirados = [w for w, p in self._pending_reclassification.items()
                             if (ahora - p['ts']).total_seconds() > 600]
                for w in expirados:
                    self._pending_reclassification.pop(w, None)
                if expirados:
                    logger.info(f"Pending cleanup: {len(expirados)} trades expirados eliminados")
                # BUG-8: Invalidar analysis_cache con TTL > 6 horas
                ttl_6h = 6 * 3600
                caducados = [w for w, v in self.analysis_cache.items()
                             if (ahora - v.get('cached_at', ahora)).total_seconds() > ttl_6h]
                for w in caducados:
                    del self.analysis_cache[w]
                if caducados:
                    logger.info(f"Cache cleanup: {len(caducados)} tiers caducados eliminados")

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
