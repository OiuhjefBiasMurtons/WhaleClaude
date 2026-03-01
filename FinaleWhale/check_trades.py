#!/usr/bin/env python3
"""Script para verificar inconsistencias en los trades resueltos"""

from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Obtener todos los trades resueltos
response = supabase.table('whale_signals').select('*').not_.is_('result', 'null').order('id').execute()

print('=' * 100)
print('TRADES RESUELTOS EN SUPABASE')
print('=' * 100)

inconsistencias = []
total_pnl = 0
wins = 0
losses = 0

for trade in response.data:
    trade_id = trade['id']
    result = trade.get('result', 'N/A')
    pnl = float(trade.get('pnl_teorico', 0))
    side = trade.get('side', 'N/A')
    outcome = trade.get('outcome', 'N/A')

    # Detectar inconsistencias: WIN con PnL negativo
    if result == 'WIN' and pnl < 0:
        inconsistencias.append(trade)

    total_pnl += pnl
    if result == 'WIN':
        wins += 1
    elif result == 'LOSS':
        losses += 1

win_rate = wins/(wins+losses)*100 if (wins+losses) > 0 else 0
print(f'RESUMEN: {wins} Wins, {losses} Losses | Win Rate: {win_rate:.1f}% | Total PnL: ${total_pnl:.2f}')
print('=' * 100)

# Mostrar inconsistencias
if inconsistencias:
    print('\n⚠️ INCONSISTENCIAS DETECTADAS (WIN con PnL negativo):')
    print('-' * 100)
    for trade in inconsistencias:
        print(f"\nTrade #{trade['id']}: {trade['market_title'][:60]}")
        print(f"  Side: {trade['side']} | Outcome apostado: {trade['outcome']}")
        print(f"  Poly Price: {trade['poly_price']} | Edge: {trade.get('edge_pct', 0)}%")
        print(f"  Result: {trade['result']} | PnL: ${trade['pnl_teorico']}")
        print(f"  Detected at: {trade.get('detected_at', 'N/A')}")
else:
    print('\n✅ No se detectaron inconsistencias en los trades resueltos')
