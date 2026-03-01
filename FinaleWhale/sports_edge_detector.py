#!/usr/bin/env python3
"""
Sports Edge Detector - Compara precios de Polymarket vs Pinnacle
para detectar si un trade deportivo tiene edge real.
"""

import re
import time
import logging
import difflib

logger = logging.getLogger(__name__)

SPORTS_KEYWORDS = [
    'win', 'vs', 'match', 'game', 'score', 'beat', 'champion',
    'nba', 'nfl', 'nhl', 'mlb', 'premier', 'liga', 'serie a',
    'bundesliga', 'ligue', 'ufc', 'tennis', 'cup', 'tournament',
    'fc ', ' fc', 'united', 'city', 'real ', 'atletico',
    'lakers', 'celtics', 'bulls', 'warriors', 'nets',
    'barcelona', 'madrid', 'bayern', 'dortmund', 'juventus',
    'inter', 'milan', 'psg', 'lyon', 'lille', 'chelsea',
    'arsenal', 'liverpool', 'tottenham', 'manchester',
]

# Mapeo de keywords a sport keys de The Odds API
SPORT_MAP = {
    'nba': 'basketball_nba',
    'lakers': 'basketball_nba',
    'celtics': 'basketball_nba',
    'bulls': 'basketball_nba',
    'warriors': 'basketball_nba',
    'nets': 'basketball_nba',
    'knicks': 'basketball_nba',
    'bucks': 'basketball_nba',
    'nfl': 'americanfootball_nfl',
    'nhl': 'icehockey_nhl',
    'mlb': 'baseball_mlb',
    'premier': 'soccer_epl',
    'chelsea': 'soccer_epl',
    'arsenal': 'soccer_epl',
    'liverpool': 'soccer_epl',
    'tottenham': 'soccer_epl',
    'manchester': 'soccer_epl',
    'liga': 'soccer_spain_la_liga',
    'barcelona': 'soccer_spain_la_liga',
    'real ': 'soccer_spain_la_liga',
    'atletico': 'soccer_spain_la_liga',
    'ligue': 'soccer_france_ligue_one',
    'lille': 'soccer_france_ligue_one',
    'psg': 'soccer_france_ligue_one',
    'lyon': 'soccer_france_ligue_one',
    'paris': 'soccer_france_ligue_one',
    'serie a': 'soccer_italy_serie_a',
    'inter': 'soccer_italy_serie_a',
    'milan': 'soccer_italy_serie_a',
    'juventus': 'soccer_italy_serie_a',
    'bundesliga': 'soccer_germany_bundesliga',
    'bayern': 'soccer_germany_bundesliga',
    'dortmund': 'soccer_germany_bundesliga',
    'ufc': 'mma_mixed_martial_arts',
}

CACHE_TTL = 300  # 5 minutos


class SportsEdgeDetector:
    def __init__(self, api_key, session):
        self.api_key = api_key
        self.session = session
        self.base_url = "https://api.the-odds-api.com/v4"
        self._cache = {}  # key -> (timestamp, result)
        self.enabled = bool(api_key)

    def check_edge(self, market_title, poly_price, side):
        """
        Compara precio de Polymarket con odds de Pinnacle.

        Returns:
            dict con is_sports, has_edge, pinnacle_price, edge_pct, reason, event_name, is_sucker_bet
        """
        default_pass = {
            'is_sports': False,
            'has_edge': True,
            'pinnacle_price': 0.0,
            'edge_pct': 0.0,
            'reason': 'Mercado no deportivo',
            'event_name': '',
            'is_sucker_bet': False
        }

        if not market_title:
            return default_pass

        title_lower = market_title.lower()

        # Paso 1: Detectar si es deportivo
        if not any(kw in title_lower for kw in SPORTS_KEYWORDS):
            return default_pass

        # Es deportivo
        result = {
            'is_sports': True,
            'has_edge': True,
            'pinnacle_price': 0.0,
            'edge_pct': 0.0,
            'reason': '',
            'event_name': market_title,
            'is_sucker_bet': False
        }

        if not self.enabled:
            result['reason'] = 'ODDS_API_KEY no configurada'
            return result

        # Paso 2: Parsear evento
        team, date_str = self._parse_event(market_title)
        if not team:
            result['reason'] = 'No se pudo parsear el evento'
            return result

        result['event_name'] = team

        # Cache check
        cache_key = f"{team.lower()}_{side}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < CACHE_TTL:
            return cached[1]

        # Paso 3: Detectar deporte
        sport_key = self._detect_sport(title_lower)

        # Paso 4: Buscar odds en Pinnacle
        pinnacle_price = self._get_pinnacle_odds(sport_key, team, side)

        if pinnacle_price <= 0:
            result['reason'] = 'Odds no disponibles en Pinnacle'
            self._cache[cache_key] = (time.time(), result)
            return result

        result['pinnacle_price'] = pinnacle_price

        # Paso 5: Calcular edge
        # Convención: edge_pct = (pinnacle - poly) * 100
        # edge_pct > 0 → poly más barato que Pinnacle → edge real para el apostador
        # edge_pct < 0 → poly más caro → is_sucker_bet = True
        # NOTA: el CSV histórico (whale_signals) usa la convención OPUESTA (poly - pinnacle).
        # No confundir al cruzar datos del CSV con valores en tiempo real.
        edge_pct = (pinnacle_price - poly_price) * 100
        result['edge_pct'] = edge_pct

        # SIEMPRE capturar el trade, solo marcar si es sucker bet
        result['has_edge'] = True  # No rechazar nunca
        result['is_sucker_bet'] = False

        if edge_pct > 3:
            result['reason'] = f"Edge real: Poly {edge_pct:.1f}% mas barato que Pinnacle"
        elif edge_pct > 0:
            result['reason'] = f"Edge marginal: {edge_pct:.1f}%"
        else:
            result['is_sucker_bet'] = True
            result['reason'] = f"⚠️ SUCKER BET: ballena pagando {abs(edge_pct):.1f}% mas caro que Pinnacle"

        self._cache[cache_key] = (time.time(), result)
        return result

    def _parse_event(self, title):
        """Extrae equipo y fecha del titulo del mercado"""
        # Patron: "Will X win on YYYY-MM-DD?"
        m = re.search(r'[Ww]ill\s+(.+?)\s+win\s+on\s+(\d{4}-\d{2}-\d{2})', title)
        if m:
            return m.group(1).strip(), m.group(2)

        # Patron: "Will X beat Y?"
        m = re.search(r'[Ww]ill\s+(.+?)\s+beat\s+(.+?)[\?\.]', title)
        if m:
            return m.group(1).strip(), ''

        # Patron: "X vs Y"
        m = re.search(r'(.+?)\s+vs\.?\s+(.+?)[\s\-\?\.]', title)
        if m:
            return m.group(1).strip(), ''

        # Patron generico: extraer nombre propio antes de "win"
        m = re.search(r'[Ww]ill\s+(.+?)\s+win', title)
        if m:
            return m.group(1).strip(), ''

        return None, None

    def _detect_sport(self, title_lower):
        """Detecta el deporte basado en keywords del titulo"""
        for keyword, sport in SPORT_MAP.items():
            if keyword in title_lower:
                return sport
        return 'soccer_epl'  # fallback

    def _get_pinnacle_odds(self, sport_key, team_name, side):
        """Busca odds de Pinnacle via The Odds API"""
        try:
            url = f"{self.base_url}/sports/{sport_key}/odds"
            params = {
                'apiKey': self.api_key,
                'regions': 'eu',
                'markets': 'h2h',
                'bookmakers': 'pinnacle'
            }
            res = self.session.get(url, params=params, timeout=15)

            if res.status_code == 401:
                logger.warning("ODDS_API_KEY inválida")
                return 0.0
            if res.status_code == 429:
                logger.warning("Límite de requests alcanzado en The Odds API")
                return 0.0
            if res.status_code != 200:
                logger.warning(f"Odds API status: {res.status_code}")
                return 0.0

            events = res.json()
            if not events:
                return 0.0

            # Buscar el evento que mejor matchee por nombre de equipo
            best_match = self._find_best_event(events, team_name)
            if not best_match:
                return 0.0

            # Extraer odds de Pinnacle para el equipo correcto
            return self._extract_pinnacle_price(best_match, team_name, side)

        except Exception as e:
            logger.warning(f"Error consultando Odds API: {e}")
            return 0.0

    def _find_best_event(self, events, team_name):
        """Encuentra el evento que mejor matchea con fuzzy matching"""
        team_lower = team_name.lower()
        best_event = None
        best_ratio = 0.0

        for event in events:
            home = event.get('home_team', '')
            away = event.get('away_team', '')

            # Fuzzy match contra ambos equipos
            for name in [home, away]:
                ratio = difflib.SequenceMatcher(None, team_lower, name.lower()).ratio()
                if ratio > best_ratio and ratio >= 0.5:
                    best_ratio = ratio
                    best_event = event

            # Match parcial (team_name contenido en nombre del evento)
            if team_lower in home.lower() or team_lower in away.lower():
                best_event = event
                best_ratio = 1.0
                break

        return best_event

    def _extract_pinnacle_price(self, event, team_name, side):
        """Extrae precio implícito de Pinnacle para el equipo"""
        bookmakers = event.get('bookmakers', [])
        pinnacle = None
        for bk in bookmakers:
            if bk.get('key') == 'pinnacle':
                pinnacle = bk
                break

        if not pinnacle:
            return 0.0

        markets = pinnacle.get('markets', [])
        h2h = None
        for m in markets:
            if m.get('key') == 'h2h':
                h2h = m
                break

        if not h2h:
            return 0.0

        outcomes = h2h.get('outcomes', [])
        team_lower = team_name.lower()

        # Buscar el equipo en los outcomes
        best_match_idx = -1
        best_ratio = 0.0

        for i, outcome in enumerate(outcomes):
            name = outcome.get('name', '')
            ratio = difflib.SequenceMatcher(None, team_lower, name.lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match_idx = i

            if team_lower in name.lower():
                best_match_idx = i
                best_ratio = 1.0
                break

        if best_match_idx < 0 or best_ratio < 0.4:
            return 0.0

        decimal_odd = outcomes[best_match_idx].get('price', 0)
        if decimal_odd <= 0:
            return 0.0

        # Convertir odds decimal a precio implícito
        return 1.0 / decimal_odd
