#!/usr/bin/env python3
"""
Resuelve trades pendientes en Supabase Gold consultando el CLOB API de Polymarket.
"""

import requests
import time
import os
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPA_GOLD_URL")
SUPABASE_KEY = os.getenv("SUPA_GOLD_KEY")
CLOB_API = "https://clob.polymarket.com"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Faltan SUPA_GOLD_URL y SUPA_GOLD_KEY en el .env")

# Trades con condition_id obtenidos de la query anterior
TRADES = [
    {"id": 166, "condition_id": "0x24026080b17f4e88729eab0ac2929ee37c13bfbb4a159179ec63deb4a242d9c9", "side": "BUY", "poly_price": 0.384275149940943, "outcome": "Yes"},
    {"id": 167, "condition_id": "0x84c7382fc6881416a2b07b0ebe9da32daba8be44a48623a0c3fe4b22f816431a", "side": "SELL", "poly_price": 0.226922434639777, "outcome": "Yes"},
    {"id": 169, "condition_id": "0x337e5c84b83679d5557acafcf78b5c5d4d932b9fcd7dfba7966249d64f0f0a0f", "side": "BUY", "poly_price": 0.288813763975155, "outcome": "Yes"},
    {"id": 173, "condition_id": "0x9345d5142a67f5541264c96515496affee02580f1c572680759eac9fd2a1588a", "side": "BUY", "poly_price": 0.66, "outcome": "No"},
    {"id": 174, "condition_id": "0x9345d5142a67f5541264c96515496affee02580f1c572680759eac9fd2a1588a", "side": "BUY", "poly_price": 0.67, "outcome": "No"},
    {"id": 180, "condition_id": "0xaed2af7846d09d24b18c206a64abd7b0e1e6e0a92a7a611e7bac6adec4e8d0d7", "side": "BUY", "poly_price": 0.5, "outcome": "G2 Esports"},
    {"id": 181, "condition_id": "0x747dc809fb79e1b05be09c42d6179459a58de2ef3e40f02484a4e1260f741f75", "side": "SELL", "poly_price": 0.2, "outcome": "Yes"},
    {"id": 202, "condition_id": "0x5051e7e7d3a23daed892ed1f6723c375ae0b50a282d2c81cb2faec6c7a7cdf9f", "side": "SELL", "poly_price": 0.77, "outcome": "No"},
    {"id": 203, "condition_id": "0x50f400421c280de0b7c3fa5b68bd7d5acb6b7fb4acd2d7c6d3dfba3ad7c53b0d", "side": "SELL", "poly_price": 0.5, "outcome": "Over 2.5"},
    {"id": 205, "condition_id": "0x30241ae99e08f7be36dccd1312be3c2ad1a0132ed444f9bd47bd71c800d9213d", "side": "SELL", "poly_price": 0.5, "outcome": "Over"},
    {"id": 208, "condition_id": "0xaeea5f917fc5746387b5f9c0a4263dba035dbb3f0ac6ad72bf92183d21e26739", "side": "BUY", "poly_price": 0.42321429979203, "outcome": "Yes"},
    {"id": 209, "condition_id": "0x561cd8d035bac38ed04e23d7882a126da38d7ead9d6679f722ad62c0c9d54ad2", "side": "SELL", "poly_price": 0.376443553996611, "outcome": "No"},
    {"id": 210, "condition_id": "0xaeea5f917fc5746387b5f9c0a4263dba035dbb3f0ac6ad72bf92183d21e26739", "side": "BUY", "poly_price": 0.42772545, "outcome": "Yes"},
    {"id": 227, "condition_id": "0x9352c559e9648ab4cab236087b64ca85c5b7123a4c7d9d7d4efde4a39c18056f", "side": "SELL", "poly_price": 0.39, "outcome": "Yes"},
    {"id": 238, "condition_id": "0xcba24842ceac7a40d2a8b9adde1f4407999b6505193b9fd68156ae76fbffa706", "side": "BUY", "poly_price": 0.33, "outcome": "No"},
    {"id": 249, "condition_id": "0xcba24842ceac7a40d2a8b9adde1f4407999b6505193b9fd68156ae76fbffa706", "side": "BUY", "poly_price": 0.67, "outcome": "Yes"},
    {"id": 277, "condition_id": "0x2e8438e1d9d2737a35161a5380e491fcbcfd66ccfe359bed3a4642d7fffa4db6", "side": "BUY", "poly_price": 0.51, "outcome": "Lupus Esports"},
    {"id": 358, "condition_id": "0x1a01bf78f56a507fcb666d564d8c8b91b0750679163ed6e96746102c9b7d285d", "side": "BUY", "poly_price": 0.344530579155283, "outcome": "Yes"},
    {"id": 407, "condition_id": "0x9352c559e9648ab4cab236087b64ca85c5b7123a4c7d9d7d4efde4a39c18056f", "side": "BUY", "poly_price": 0.32, "outcome": "Yes"},
    {"id": 410, "condition_id": "0x4290a4aa43a0707f0f1193c73667074f2ef5ce8ab5d6fcdd4ca645bfe1528f03", "side": "BUY", "poly_price": 0.36916771750401, "outcome": "Yes"},
    {"id": 415, "condition_id": "0xccc6ec43c9e7cce52fd9af5cfe14d47181c5fd299caee2bf8187d6d58a2365f5", "side": "BUY", "poly_price": 0.51, "outcome": "Mighty Tiger Gaming"},
    {"id": 424, "condition_id": "0x306d10d4a4d51b41910dbc779ca00908bd917c131541c5c42bbbc736258d2d56", "side": "BUY", "poly_price": 0.2897876, "outcome": "Yes"},
    {"id": 426, "condition_id": "0xaeea5f917fc5746387b5f9c0a4263dba035dbb3f0ac6ad72bf92183d21e26739", "side": "BUY", "poly_price": 0.403485546827121, "outcome": "Yes"},
    {"id": 427, "condition_id": "0xe546672750517f62c45a5a00067481981e62b9c20fa8220203232c9dc8fd2093", "side": "BUY", "poly_price": 0.192841979055536, "outcome": "Yes"},
    {"id": 461, "condition_id": "0xc5300759dc2089042380795fe7384010a6b6ebdf9e6da7ed3f786d9a5f61c563", "side": "BUY", "poly_price": 0.36, "outcome": "No"},
    {"id": 462, "condition_id": "0x8df5a4256840dee05851250c0490da7593597faff3a7f9a156ccbbda7fec76f8", "side": "BUY", "poly_price": 0.291266483811817, "outcome": "Yes"},
    {"id": 464, "condition_id": "0x3c6bcb7da14ea576e5af25547dbd96f2bb24ac34e748e76aecff2ee9195dd1ac", "side": "SELL", "poly_price": 0.300013555844104, "outcome": "Yes"},
    {"id": 474, "condition_id": "0x306d10d4a4d51b41910dbc779ca00908bd917c131541c5c42bbbc736258d2d56", "side": "SELL", "poly_price": 0.327799766666667, "outcome": "Yes"},
    {"id": 482, "condition_id": "0x2daeb83296e57fa3ecdc944fe7f99b309313326fa1c8b2f7ce2eb3c3b25b6b6e", "side": "BUY", "poly_price": 0.52, "outcome": "North Carolina Tar Heels"},
    {"id": 483, "condition_id": "0xc1c06476d8050e3ba5624e91b7e6f0ae9c7d18aceb8ca07677b663256a1441f6", "side": "BUY", "poly_price": 0.629555899903645, "outcome": "Raptors"},
    {"id": 484, "condition_id": "0x6353c0fb42fedd926bd2055fc192b2e0fbf9bcb3313e08de30a03a256e2e5022", "side": "BUY", "poly_price": 0.579997312415139, "outcome": "Natus Vincere"},
    {"id": 485, "condition_id": "0x221959fe367bcd17f8438404ad8785b41631c12494949298c2f30ccadb3d60fb", "side": "BUY", "poly_price": 0.68, "outcome": "Aurora"},
    {"id": 486, "condition_id": "0x98fba04922158c14286af9765a3755bcc4d17dfd6137a06e9812a7f1d2450fe9", "side": "BUY", "poly_price": 0.49, "outcome": "Pelicans"},
    {"id": 487, "condition_id": "0x4bdaa5093741c4c44a5b84b5233de4dba4339e761a89cf2128d0e1c40c7df023", "side": "BUY", "poly_price": 0.68, "outcome": "Timberwolves"},
    {"id": 488, "condition_id": "0x4bdaa5093741c4c44a5b84b5233de4dba4339e761a89cf2128d0e1c40c7df023", "side": "BUY", "poly_price": 0.67, "outcome": "Timberwolves"},
    {"id": 489, "condition_id": "0x4bdaa5093741c4c44a5b84b5233de4dba4339e761a89cf2128d0e1c40c7df023", "side": "BUY", "poly_price": 0.68, "outcome": "Timberwolves"},
    {"id": 490, "condition_id": "0x4bdaa5093741c4c44a5b84b5233de4dba4339e761a89cf2128d0e1c40c7df023", "side": "BUY", "poly_price": 0.67, "outcome": "Timberwolves"},
    {"id": 491, "condition_id": "0x6fe4be2c9781c416f110eefafd59252fd92696b9cc660a3d8c244b9cf980393e", "side": "BUY", "poly_price": 0.569753176004141, "outcome": "Under"},
    {"id": 492, "condition_id": "0x4bdaa5093741c4c44a5b84b5233de4dba4339e761a89cf2128d0e1c40c7df023", "side": "BUY", "poly_price": 0.66, "outcome": "Timberwolves"},
    {"id": 493, "condition_id": "0x4bdaa5093741c4c44a5b84b5233de4dba4339e761a89cf2128d0e1c40c7df023", "side": "BUY", "poly_price": 0.687043126654987, "outcome": "Timberwolves"},
    {"id": 494, "condition_id": "0x86b034f6e656d8c9da1c0701a403bbedf688f094dded4cbe103156eab3a491a8", "side": "BUY", "poly_price": 0.483378979259086, "outcome": "Team Spirit"},
    {"id": 495, "condition_id": "0x1813f5f26f269a677d6d72a5502d2f0f008426374a6ecaef982717574f29bc16", "side": "BUY", "poly_price": 0.81, "outcome": "Hawks"},
    {"id": 496, "condition_id": "0x3fe5032148c141e64d7fbe9a8ee13a25a87c57252f69e24d079b39fa9aa5619e", "side": "BUY", "poly_price": 0.47728286000478, "outcome": "Astralis"},
    {"id": 497, "condition_id": "0x0c478faec8241aa63adca971560a17878d508f158be1b6dacf1c95283f2b8f41", "side": "BUY", "poly_price": 0.406813358725341, "outcome": "Paper Rex"},
    {"id": 498, "condition_id": "0x5d4fbc606c90f11cf2217a86939df08e705348572acba2fcccc792ef8b7c1c4b", "side": "BUY", "poly_price": 0.68, "outcome": "Spurs"},
    {"id": 499, "condition_id": "0x86b034f6e656d8c9da1c0701a403bbedf688f094dded4cbe103156eab3a491a8", "side": "BUY", "poly_price": 0.456681560078987, "outcome": "Team Liquid"},
    {"id": 500, "condition_id": "0x86b034f6e656d8c9da1c0701a403bbedf688f094dded4cbe103156eab3a491a8", "side": "BUY", "poly_price": 0.478014427157001, "outcome": "Team Liquid"},
    {"id": 501, "condition_id": "0x218e70b31ab4683ffe980b9df0a6797a19708365c601f6dbe21c830f832c3810", "side": "BUY", "poly_price": 0.48, "outcome": "UCLA Bruins"},
    {"id": 502, "condition_id": "0xd282ab4a31a34203b251dde259067c0842647d623aef0915028c74c3cef6009f", "side": "BUY", "poly_price": 0.46, "outcome": "Magic"},
    {"id": 503, "condition_id": "0x3fe5032148c141e64d7fbe9a8ee13a25a87c57252f69e24d079b39fa9aa5619e", "side": "SELL", "poly_price": 0.655308448303951, "outcome": "Astralis"},
    {"id": 504, "condition_id": "0xc34af25221919b98a6c1a743f76cb5f2dca39eccaff88327adb160cf8e4ce2a9", "side": "BUY", "poly_price": 0.62, "outcome": "Heat"},
    {"id": 505, "condition_id": "0x38c63f01ef52eec70ef3fbff8623ad60f55dfb90a0c29892ae16dd3c98307fdc", "side": "BUY", "poly_price": 0.52, "outcome": "Magic"},
    {"id": 506, "condition_id": "0xc34af25221919b98a6c1a743f76cb5f2dca39eccaff88327adb160cf8e4ce2a9", "side": "BUY", "poly_price": 0.62, "outcome": "Heat"},
    {"id": 507, "condition_id": "0x393beb48ce5694c1fcc301a98a0888064f0d2d7393a724f0db8043c9c55956d0", "side": "BUY", "poly_price": 0.56, "outcome": "Lakers"},
    {"id": 508, "condition_id": "0x3a66938b3919b0150696b23ef354246c856d2a65000768d0ce4f23a6ec61d571", "side": "BUY", "poly_price": 0.519999999994781, "outcome": "Over"},
    {"id": 509, "condition_id": "0xc2587749c3f96ebaa8fd61da783cc06eda7da7de13bde783b00921b53cddb74c", "side": "BUY", "poly_price": 0.47, "outcome": "Lakers"},
    {"id": 510, "condition_id": "0xc34af25221919b98a6c1a743f76cb5f2dca39eccaff88327adb160cf8e4ce2a9", "side": "BUY", "poly_price": 0.63, "outcome": "Heat"},
    {"id": 511, "condition_id": "0x3a66938b3919b0150696b23ef354246c856d2a65000768d0ce4f23a6ec61d571", "side": "BUY", "poly_price": 0.49, "outcome": "Under"},
    {"id": 512, "condition_id": "0xc281629998ccf7213b2eeb2fc400f32fab2e6d8400cb1ae170bdca98a65993e8", "side": "BUY", "poly_price": 0.26, "outcome": "Ion Cutelaba"},
    {"id": 513, "condition_id": "0xc2587749c3f96ebaa8fd61da783cc06eda7da7de13bde783b00921b53cddb74c", "side": "BUY", "poly_price": 0.562077269596414, "outcome": "Lakers"},
    {"id": 514, "condition_id": "0x31c04ce6e53a5a4ea2224f98c913374c2bc4eda7926e7677584c79ebe0a6e1e5", "side": "BUY", "poly_price": 0.509999999975852, "outcome": "Over"},
    {"id": 515, "condition_id": "0xc2587749c3f96ebaa8fd61da783cc06eda7da7de13bde783b00921b53cddb74c", "side": "BUY", "poly_price": 0.64, "outcome": "Nuggets"},
    {"id": 516, "condition_id": "0x7b58f67f7f8231a9bb515d47cc44c5088c5be59e3b848358295c90916301c479", "side": "BUY", "poly_price": 0.522115038580754, "outcome": "Over"},
    {"id": 517, "condition_id": "0x43ec63bda2d67434cc3544dcb4cb2e87048181d22bf1e8575f23523cb3240541", "side": "BUY", "poly_price": 0.49, "outcome": "Celtics"},
]

def calcular_pnl(side, poly_price, result):
    if side == 'BUY':
        return round(100 * (1 / poly_price - 1), 4) if result == 'WIN' else -100.0
    else:  # SELL
        return round(100 * poly_price, 4) if result == 'WIN' else round(-(100 - 100 * poly_price), 4)

def get_market_result(condition_id, session):
    """Consulta CLOB API y retorna el outcome ganador si el mercado cerró."""
    try:
        resp = session.get(f"{CLOB_API}/markets/{condition_id}", timeout=10)
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        
        market = resp.json()
        if not market.get('closed', False):
            return None, "ABIERTO"
        
        # Buscar token ganador
        winning_outcome = None
        for token in market.get('tokens', []):
            if token.get('winner', False):
                winning_outcome = token.get('outcome')
                break
        
        if not winning_outcome:
            return None, "CERRADO_SIN_GANADOR"
        
        return winning_outcome, None
    except Exception as e:
        return None, str(e)

def main():
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    resueltos = []
    abiertos = []
    errores = []
    sin_ganador = []
    
    # Cache de condition_ids ya consultados (evitar re-consultar el mismo mercado)
    cache = {}
    
    print(f"Procesando {len(TRADES)} trades...\n")
    
    for trade in TRADES:
        trade_id = trade['id']
        cid = trade['condition_id']
        
        # Usar cache si ya consultamos este mercado
        if cid in cache:
            winning_outcome, error = cache[cid]
        else:
            winning_outcome, error = get_market_result(cid, session)
            cache[cid] = (winning_outcome, error)
            time.sleep(0.3)  # Rate limiting
        
        if error == "ABIERTO":
            abiertos.append(trade_id)
            print(f"  ⏳ #{trade_id} — aún abierto")
            continue
        
        if error == "CERRADO_SIN_GANADOR":
            sin_ganador.append(trade_id)
            print(f"  ⚠️  #{trade_id} — cerrado sin ganador declarado")
            continue
        
        if error:
            errores.append((trade_id, error))
            print(f"  ❌ #{trade_id} — error: {error}")
            continue
        
        # Determinar resultado
        whale_outcome = trade['outcome'].upper()
        winner_norm = winning_outcome.upper()
        side = trade['side']
        
        if side == 'BUY':
            result = 'WIN' if whale_outcome == winner_norm else 'LOSS'
        else:  # SELL
            result = 'WIN' if whale_outcome != winner_norm else 'LOSS'
        
        pnl = calcular_pnl(side, trade['poly_price'], result)
        icon = '✅' if result == 'WIN' else '❌'
        
        # Actualizar Supabase
        try:
            sb.table('whale_signals').update({
                'resolved_at': datetime.now().isoformat(),
                'result': result,
                'pnl_teorico': pnl
            }).eq('id', trade_id).execute()
            
            resueltos.append({'id': trade_id, 'result': result, 'pnl': pnl})
            print(f"  {icon} #{trade_id} — {side} '{trade['outcome']}' | Ganó: '{winning_outcome}' | {result} | PnL: ${pnl:+.2f}")
        except Exception as e:
            errores.append((trade_id, str(e)))
            print(f"  ❌ #{trade_id} — error Supabase: {e}")
    
    # Resumen
    wins = sum(1 for t in resueltos if t['result'] == 'WIN')
    losses = sum(1 for t in resueltos if t['result'] == 'LOSS')
    pnl_total = sum(t['pnl'] for t in resueltos)
    wr = wins / len(resueltos) * 100 if resueltos else 0
    
    print(f"\n{'='*60}")
    print(f"RESUMEN")
    print(f"{'='*60}")
    print(f"  Resueltos hoy:    {len(resueltos)} (W={wins}, L={losses}, WR={wr:.1f}%)")
    print(f"  PnL de los nuevos: ${pnl_total:+.2f}")
    print(f"  Aún abiertos:     {len(abiertos)} {abiertos}")
    print(f"  Sin ganador:      {len(sin_ganador)} {sin_ganador}")
    print(f"  Errores:          {len(errores)}")
    if errores:
        for eid, emsg in errores:
            print(f"    #{eid}: {emsg}")

if __name__ == "__main__":
    main()