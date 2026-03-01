#!/usr/bin/env python3
"""
Script de prueba para verificar la detección de nuevos trades.
Compara los trades actuales con los de hace N segundos.
"""

import sys
import time
import requests
from datetime import datetime

DATA_API = "https://data-api.polymarket.com"

def get_recent_trades(wallet, limit=10):
    """Obtiene trades recientes ordenados"""
    try:
        url = f"{DATA_API}/trades"
        params = {'maker': wallet, '_limit': 100}
        response = requests.get(url, params=params, timeout=10)
        trades = response.json()

        # Ordenar por timestamp descendente
        trades_sorted = sorted(trades, key=lambda x: x.get('timestamp', 0), reverse=True)
        return trades_sorted[:limit]
    except Exception as e:
        print(f"Error: {e}")
        return []

def create_trade_id(trade):
    """Crea ID único para un trade"""
    tx_hash = trade.get('transactionHash')
    if tx_hash:
        return tx_hash

    timestamp = trade.get('timestamp', '')
    side = trade.get('side', '').upper()
    size = float(trade.get('size', 0))
    condition_id = trade.get('conditionId', '')
    return f"{timestamp}_{condition_id}_{side}_{size}"

def main():
    if len(sys.argv) < 2:
        print("Uso: python3 test_live_detection.py <wallet_address>")
        sys.exit(1)

    wallet = sys.argv[1]

    print("=" * 80)
    print("🧪 TEST DE DETECCIÓN EN VIVO")
    print("=" * 80)
    print(f"Wallet: {wallet}")
    print()

    # Primera consulta
    print("📊 Obteniendo estado inicial...")
    initial_trades = get_recent_trades(wallet, 10)
    initial_ids = {create_trade_id(t) for t in initial_trades}

    print(f"✅ {len(initial_trades)} trades iniciales detectados")
    print()

    if initial_trades:
        print("Últimos 3 trades:")
        for i, t in enumerate(initial_trades[:3], 1):
            dt = datetime.fromtimestamp(t.get('timestamp', 0))
            print(f"  {i}. {t.get('title', 'N/A')[:50]}")
            print(f"     {t.get('side')} | {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

    # Monitoreo
    print("🔍 Esperando 15 segundos y verificando nuevos trades...")
    print("(Si el trader hace un trade nuevo en este tiempo, se detectará)")
    print()

    time.sleep(15)

    # Segunda consulta
    print("📊 Obteniendo estado actual...")
    current_trades = get_recent_trades(wallet, 10)
    current_ids = {create_trade_id(t) for t in current_trades}

    # Detectar nuevos
    new_ids = current_ids - initial_ids

    if new_ids:
        print(f"🚨 ¡{len(new_ids)} NUEVO(S) TRADE(S) DETECTADO(S)!")
        print()
        for trade in current_trades:
            trade_id = create_trade_id(trade)
            if trade_id in new_ids:
                dt = datetime.fromtimestamp(trade.get('timestamp', 0))
                print(f"  🆕 {trade.get('title', 'N/A')[:60]}")
                print(f"     {trade.get('side')} {trade.get('size')} @ ${trade.get('price')}")
                print(f"     Hora: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print()
    else:
        print("✅ No se detectaron nuevos trades en los últimos 15 segundos")
        print("   (El trader no ha hecho trades nuevos)")

    print()
    print("=" * 80)
    print("Test completado")
    print("=" * 80)

if __name__ == "__main__":
    main()
