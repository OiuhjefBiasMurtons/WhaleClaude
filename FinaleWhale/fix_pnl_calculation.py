#!/usr/bin/env python3
"""
Script para corregir el cálculo de PnL en trades de tipo SELL que fueron
calculados con la fórmula incorrecta.
"""

from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

def recalcular_pnl(side, poly_price, result):
    """
    Recalcula el PnL con la fórmula correcta.

    BUY WIN: 100 * (1/price - 1)
    BUY LOSS: -100
    SELL WIN: 100 * price
    SELL LOSS: -(100 - 100 * price)
    """
    if side == 'BUY':
        if result == 'WIN':
            return 100 * (1 / poly_price - 1)
        else:
            return -100.0
    else:  # SELL
        if result == 'WIN':
            return 100 * poly_price
        else:
            return -(100 - 100 * poly_price)

# Obtener todos los trades resueltos
response = supabase.table('whale_signals').select('*').not_.is_('result', 'null').execute()

print('=' * 100)
print('CORRIGIENDO CÁLCULOS DE PNL')
print('=' * 100)

actualizaciones = 0
cambios_detectados = []

for trade in response.data:
    trade_id = trade['id']
    side = trade['side']
    poly_price = float(trade['poly_price'])
    result = trade['result']
    pnl_actual = float(trade['pnl_teorico'])

    # Recalcular PnL con fórmula correcta
    pnl_correcto = recalcular_pnl(side, poly_price, result)

    # Si hay diferencia, actualizar
    if abs(pnl_correcto - pnl_actual) > 0.01:  # Tolerancia de $0.01
        cambios_detectados.append({
            'id': trade_id,
            'market': trade['market_title'][:50],
            'side': side,
            'result': result,
            'price': poly_price,
            'pnl_viejo': pnl_actual,
            'pnl_nuevo': pnl_correcto
        })

        # Actualizar en Supabase
        supabase.table('whale_signals')\
            .update({'pnl_teorico': pnl_correcto})\
            .eq('id', trade_id)\
            .execute()

        actualizaciones += 1

# Mostrar resultados
if cambios_detectados:
    print(f'\n✅ Se detectaron {len(cambios_detectados)} trades con PnL incorrecto:\n')
    for cambio in cambios_detectados:
        print(f"Trade #{cambio['id']}: {cambio['market']}")
        print(f"  {cambio['side']} | {cambio['result']} | Price: {cambio['price']}")
        print(f"  PnL viejo: ${cambio['pnl_viejo']:.2f} → PnL nuevo: ${cambio['pnl_nuevo']:.2f}")
        print()

    print('=' * 100)
    print(f'✅ Actualizados {actualizaciones} trades en Supabase')
else:
    print('\n✅ No se encontraron trades con PnL incorrecto')

print('=' * 100)

# Calcular estadísticas corregidas
response_final = supabase.table('whale_signals').select('*').not_.is_('result', 'null').execute()
total_pnl = sum(float(t['pnl_teorico']) for t in response_final.data)
wins = sum(1 for t in response_final.data if t['result'] == 'WIN')
losses = sum(1 for t in response_final.data if t['result'] == 'LOSS')
total = wins + losses

print(f'\n📊 ESTADÍSTICAS CORREGIDAS:')
print(f'  Total trades: {total}')
print(f'  Wins: {wins} ({wins/total*100:.1f}%)')
print(f'  Losses: {losses}')
print(f'  PnL total: ${total_pnl:.2f}')
print(f'  PnL promedio: ${total_pnl/total:.2f}')
print('=' * 100)
