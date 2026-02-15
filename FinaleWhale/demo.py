#!/usr/bin/env python3
"""
🎬 DEMO - Nuevas Funcionalidades
Muestra ejemplos en vivo de CoordinationDetector y Backtest
"""

import time
from definitive_all_claude import CoordinationDetector, TradeFilter, ConsensusTracker
from backtest import BacktestEngine


def demo_coordination():
    """Demostración de detección de grupos coordinados"""
    print("\n" + "="*80)
    print("🤝 DEMO: DETECCIÓN DE BALLENAS COORDINADAS")
    print("="*80)
    print("\nSimulando trades en el mercado 'Trump wins 2025'...")
    print()

    cd = CoordinationDetector(coordination_window=300)  # 5 minutos
    market_id = "trump_wins_2025"

    # Simular 4 ballenas apostando en menos de 5 min
    trades = [
        ("0xABC123", "BUY", 8_500, "14:30:12"),
        ("0xDEF456", "BUY", 12_300, "14:31:45"),
        ("0xGHI789", "BUY", 6_700, "14:33:20"),
        ("0xJKL012", "BUY", 15_100, "14:34:08"),
    ]

    for i, (wallet, side, valor, hora) in enumerate(trades, 1):
        print(f"[{hora}] Ballena #{i}: {wallet[:8]}... → {side} ${valor:,}")
        cd.add_trade(market_id, wallet, side, valor)

        if i >= 3:  # Después de 3 trades, verificar coordinación
            is_coord, count, desc, wallets_list = cd.detect_coordination(
                market_id, wallet, side
            )

            if is_coord:
                print(f"\n⚠️  ALERTA: ¡Grupo coordinado detectado!")
                print(f"    → {desc}")
                print(f"    → Wallets involucradas: {', '.join(w[:8] + '...' for w in wallets_list)}")

        time.sleep(0.3)  # Simular paso del tiempo

    print("\n" + "-"*80)
    print("💡 Interpretación:")
    print("   4 wallets diferentes apostaron BUY en menos de 4 minutos.")
    print("   Esto sugiere coordinación o información compartida.")
    print("   Acción recomendada: Copiar con confianza moderada-alta.")


def demo_backtest():
    """Demostración de backtesting"""
    print("\n\n" + "="*80)
    print("🔬 DEMO: BACKTEST DEL FILTRO")
    print("="*80)
    print("\nAnalizando log de ejemplo con 7 trades de ballenas...")
    print()

    backtester = BacktestEngine('trades_live/whales_test_backtest.txt')
    backtester.parse_log()

    print(f"📊 Trades encontrados: {len(backtester.trades)}")
    print()

    # Mostrar algunos trades
    print("Ejemplos de trades en el log:")
    for i, t in enumerate(backtester.trades[:3], 1):
        print(f"  {i}. {t['categoria']:<20} ${t['valor']:>10,.0f}  @{t['precio']:.4f}  → "
              f"Retorno: {((1/t['precio'])-1)*100:>5.1f}%")

    print("\nAplicando filtro de calidad...")
    backtester.apply_filter()

    all_count = len(backtester.trades)
    filt_count = len(backtester.filtered_trades)
    rejected = all_count - filt_count

    print(f"✅ Pasan filtro: {filt_count}/{all_count} ({filt_count/all_count*100:.1f}%)")
    print(f"⛔ Rechazados: {rejected} ({rejected/all_count*100:.1f}%)")
    print()

    # Calcular métricas
    all_m = backtester.calculate_metrics(backtester.trades, "SIN FILTRO")
    filt_m = backtester.calculate_metrics(backtester.filtered_trades, "CON FILTRO")

    print("-"*80)
    print("📈 IMPACTO DEL FILTRO:")
    print("-"*80)

    improvement = filt_m['avg_potential_return'] - all_m['avg_potential_return']
    price_improvement = all_m['avg_price'] - filt_m['avg_price']

    print(f"Retorno potencial promedio:")
    print(f"  Sin filtro:  {all_m['avg_potential_return']:>6.1f}%")
    print(f"  Con filtro:  {filt_m['avg_potential_return']:>6.1f}%")
    print(f"  Mejora:      {improvement:>+6.1f}% ⬆️")
    print()
    print(f"Precio promedio:")
    print(f"  Sin filtro:  {all_m['avg_price']:>6.4f}")
    print(f"  Con filtro:  {filt_m['avg_price']:>6.4f}")
    print(f"  Reducción:   {price_improvement:>+6.4f} ⬇️ (mejor +EV)")

    print("\n" + "-"*80)
    print("💡 Interpretación:")
    print(f"   El filtro rechazó {rejected/all_count*100:.0f}% de trades pero mejoró el retorno")
    print(f"   potencial en {improvement:.1f}%. Esto valida que elimina trades de bajo +EV.")
    print(f"   El precio promedio bajó de {all_m['avg_price']:.2f} a {filt_m['avg_price']:.2f},")
    print(f"   indicando que se filtran trades con odds desfavorables.")


def demo_filter_realtime():
    """Demostración del filtro en tiempo real"""
    print("\n\n" + "="*80)
    print("⚡ DEMO: FILTRO EN TIEMPO REAL")
    print("="*80)
    print("\nSimulando detección de ballenas con diferentes precios...\n")

    # Mock session para TradeFilter
    class MockSession:
        def get(self, *args, **kwargs):
            class R:
                def json(self): return [{'volume': 100000}]
            return R()

    tf = TradeFilter(MockSession())

    trades_test = [
        {"price": "0.75", "valor": 5000, "descripcion": "Precio muy alto (0.75)"},
        {"price": "0.20", "valor": 8000, "descripcion": "Precio muy bajo (0.20)"},
        {"price": "0.52", "valor": 12000, "descripcion": "Precio óptimo (0.52)"},
        {"price": "0.35", "valor": 6500, "descripcion": "Precio bueno (0.35)"},
    ]

    for trade in trades_test:
        is_valid, reason = tf.is_worth_copying(trade, float(trade["price"]))

        status = "✅ VÁLIDO" if is_valid else "⛔ RECHAZADO"
        color = "🟢" if is_valid else "🔴"

        print(f"{color} {status:12} | {trade['descripcion']:<30} | Razón: {reason}")

    print("\n" + "-"*80)
    print("💡 Interpretación:")
    print("   Solo trades con precio 0.25-0.70 pasan el filtro.")
    print("   Esto evita copiar:")
    print("   - Precios >0.70: Muy poco margen incluso si ganas")
    print("   - Precios <0.25: Odds desfavorables (baja probabilidad)")


def main():
    print("\n" + "🎬 "*20)
    print("DEMOSTRACIÓN INTERACTIVA - NUEVAS FUNCIONALIDADES")
    print("🎬 "*20)

    demos = [
        ("1", "Detección de Ballenas Coordinadas", demo_coordination),
        ("2", "Backtest del Filtro de Calidad", demo_backtest),
        ("3", "Filtro en Tiempo Real", demo_filter_realtime),
    ]

    print("\nSelecciona una demo:\n")
    for num, name, _ in demos:
        print(f"  [{num}] {name}")
    print(f"  [4] Ejecutar todas las demos")
    print(f"  [0] Salir")

    try:
        choice = input("\n👉 Opción: ").strip()

        if choice == "0":
            print("\n👋 ¡Hasta luego!")
            return

        if choice == "4":
            for _, _, demo_func in demos:
                demo_func()
        elif choice in ["1", "2", "3"]:
            idx = int(choice) - 1
            demos[idx][2]()
        else:
            print("❌ Opción inválida")
            return

        print("\n\n" + "="*80)
        print("✅ DEMO COMPLETADA")
        print("="*80)
        print("\n📖 Para más información, consulta: README_NUEVAS_FEATURES.md")
        print("🚀 Para usar en producción: python definitive_all_claude.py")
        print()

    except KeyboardInterrupt:
        print("\n\n👋 Demo interrumpida. ¡Hasta luego!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
