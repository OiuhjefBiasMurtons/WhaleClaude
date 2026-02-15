#!/usr/bin/env python3
"""
🔬 BACKTEST DEL FILTRO DE CALIDAD
Simula qué hubiera pasado si aplicabas el TradeFilter a logs históricos
Compara ROI con/sin filtro para validar efectividad
"""

import re
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict


class BacktestEngine:
    def __init__(self, log_file):
        self.log_file = Path(log_file)
        if not self.log_file.exists():
            raise FileNotFoundError(f"Log no encontrado: {log_file}")

        self.trades = []
        self.filtered_trades = []

    def parse_log(self):
        """Parsea el log de ballenas y extrae trades"""
        with open(self.log_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Pattern para extraer trades del log
        pattern = r"""
            ={80}\n
            (?P<emoji>[🐋🦈]+)\s+(?P<categoria>[\w\s]+)\s+DETECTADA\s+[🐋🦈]+\n
            ={80}\n
            💰\s+Valor:\s+\$(?P<valor>[\d,]+\.\d+)\s+USD\n
            📊\s+Mercado:\s+(?P<mercado>.+?)\n
            🔗\s+URL:\s+(?P<url>.+?)\n
            🎯\s+Outcome:\s+(?P<outcome>.+?)\n
            📈\s+Lado:\s+(?P<lado>\w+)\n
            💵\s+Precio:\s+(?P<precio>\d+\.\d+)\s+\((?P<precio_pct>[\d.]+)%\)
        """

        matches = re.finditer(pattern, content, re.VERBOSE | re.MULTILINE)

        for match in matches:
            trade = {
                'categoria': match.group('categoria').strip(),
                'valor': float(match.group('valor').replace(',', '')),
                'mercado': match.group('mercado').strip(),
                'outcome': match.group('outcome').strip(),
                'lado': match.group('lado'),
                'precio': float(match.group('precio')),
                'precio_pct': float(match.group('precio_pct'))
            }
            self.trades.append(trade)

        print(f"📂 Log parseado: {len(self.trades)} trades de ballenas encontrados")

    def apply_filter(self):
        """Aplica el filtro de calidad a los trades"""
        for trade in self.trades:
            price = trade['precio']

            # Mismo criterio que TradeFilter.is_worth_copying()
            # Filtro 1: Precio fuera de rango
            if price < 0.25 or price > 0.70:
                continue

            # Filtro 3: Retorno potencial < 40%
            potential_return_pct = ((1 / price) - 1) * 100 if price > 0 else 0
            if potential_return_pct < 40:
                continue

            # Si pasa el filtro, agregarlo
            self.filtered_trades.append(trade)

        print(f"✅ Trades que pasan filtro: {len(self.filtered_trades)}/{len(self.trades)} "
              f"({len(self.filtered_trades)/len(self.trades)*100:.1f}%)")

    def calculate_metrics(self, trades_list, label):
        """Calcula métricas de un conjunto de trades"""
        if not trades_list:
            return None

        total_value = sum(t['valor'] for t in trades_list)
        avg_value = total_value / len(trades_list)
        avg_price = sum(t['precio'] for t in trades_list) / len(trades_list)

        # Distribución por categoría
        categories = defaultdict(int)
        for t in trades_list:
            categories[t['categoria']] += 1

        # Distribución de precios
        price_ranges = {
            '0.25-0.40': 0,
            '0.40-0.55': 0,
            '0.55-0.70': 0,
            'Fuera de rango': 0
        }

        for t in trades_list:
            p = t['precio']
            if 0.25 <= p < 0.40:
                price_ranges['0.25-0.40'] += 1
            elif 0.40 <= p < 0.55:
                price_ranges['0.40-0.55'] += 1
            elif 0.55 <= p <= 0.70:
                price_ranges['0.55-0.70'] += 1
            else:
                price_ranges['Fuera de rango'] += 1

        # Potencial retorno promedio
        avg_potential_return = sum(
            ((1 / t['precio']) - 1) * 100 for t in trades_list
        ) / len(trades_list)

        return {
            'label': label,
            'count': len(trades_list),
            'total_value': total_value,
            'avg_value': avg_value,
            'avg_price': avg_price,
            'avg_potential_return': avg_potential_return,
            'categories': dict(categories),
            'price_ranges': price_ranges
        }

    def generate_report(self):
        """Genera reporte comparativo"""
        all_metrics = self.calculate_metrics(self.trades, "SIN FILTRO")
        filtered_metrics = self.calculate_metrics(self.filtered_trades, "CON FILTRO")

        if not all_metrics or not filtered_metrics:
            print("❌ No hay suficientes datos para generar reporte")
            return

        sep = "=" * 80

        report = f"""
{sep}
🔬 BACKTEST DEL FILTRO DE CALIDAD
{sep}
📂 Archivo analizado: {self.log_file.name}
📅 Fecha de análisis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{sep}

📊 COMPARACIÓN GENERAL
{sep}
                        SIN FILTRO    |    CON FILTRO    |   DIFERENCIA
{'-'*80}
Total trades            {all_metrics['count']:>10}    |    {filtered_metrics['count']:>10}    |   {filtered_metrics['count'] - all_metrics['count']:+10}
Valor total             ${all_metrics['total_value']:>9,.0f}    |    ${filtered_metrics['total_value']:>9,.0f}    |   ${filtered_metrics['total_value'] - all_metrics['total_value']:+10,.0f}
Valor promedio          ${all_metrics['avg_value']:>9,.0f}    |    ${filtered_metrics['avg_value']:>9,.0f}    |   ${filtered_metrics['avg_value'] - all_metrics['avg_value']:+10,.0f}
Precio promedio         {all_metrics['avg_price']:>10.4f}    |    {filtered_metrics['avg_price']:>10.4f}    |   {filtered_metrics['avg_price'] - all_metrics['avg_price']:+10.4f}
Retorno potencial (%)   {all_metrics['avg_potential_return']:>10.1f}    |    {filtered_metrics['avg_potential_return']:>10.1f}    |   {filtered_metrics['avg_potential_return'] - all_metrics['avg_potential_return']:+10.1f}

{sep}
📈 ANÁLISIS DE EFICIENCIA DEL FILTRO
{sep}
"""

        # Eficiencia del filtro
        rejection_rate = (1 - filtered_metrics['count'] / all_metrics['count']) * 100
        report += f"🔴 Tasa de rechazo:        {rejection_rate:.1f}% ({all_metrics['count'] - filtered_metrics['count']} trades eliminados)\n"

        value_retained = (filtered_metrics['total_value'] / all_metrics['total_value']) * 100
        report += f"💰 Valor retenido:         {value_retained:.1f}% (${filtered_metrics['total_value']:,.0f} de ${all_metrics['total_value']:,.0f})\n"

        avg_return_improvement = filtered_metrics['avg_potential_return'] - all_metrics['avg_potential_return']
        report += f"📊 Mejora retorno promedio: {avg_return_improvement:+.1f}% ({all_metrics['avg_potential_return']:.1f}% → {filtered_metrics['avg_potential_return']:.1f}%)\n"

        report += f"\n{sep}\n"
        report += f"💡 INTERPRETACIÓN\n"
        report += f"{sep}\n"

        if avg_return_improvement > 5:
            report += f"✅ FILTRO EFECTIVO: Mejora el retorno potencial promedio en {avg_return_improvement:.1f}%\n"
            report += f"   El filtro está eliminando trades de bajo +EV correctamente.\n"
        elif avg_return_improvement > 0:
            report += f"⚠️ FILTRO MODERADO: Mejora marginal de {avg_return_improvement:.1f}% en retorno potencial.\n"
            report += f"   Considerar ajustar umbrales para mayor selectividad.\n"
        else:
            report += f"❌ FILTRO PROBLEMÁTICO: Reduce el retorno potencial en {abs(avg_return_improvement):.1f}%\n"
            report += f"   Revisar criterios del filtro, puede estar eliminando buenos trades.\n"

        report += f"\n{sep}\n"
        report += f"📊 DISTRIBUCIÓN DE PRECIOS (CON FILTRO)\n"
        report += f"{sep}\n"

        for range_label, count in filtered_metrics['price_ranges'].items():
            pct = (count / filtered_metrics['count'] * 100) if filtered_metrics['count'] > 0 else 0
            bar = '█' * int(pct / 2)
            report += f"{range_label:>18}: {count:>4} trades ({pct:>5.1f}%) {bar}\n"

        report += f"\n{sep}\n"
        report += f"🏷️ TOP 5 CATEGORÍAS (CON FILTRO)\n"
        report += f"{sep}\n"

        sorted_categories = sorted(
            filtered_metrics['categories'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        for i, (cat, count) in enumerate(sorted_categories, 1):
            pct = (count / filtered_metrics['count'] * 100) if filtered_metrics['count'] > 0 else 0
            report += f"{i}. {cat:.<30} {count:>4} trades ({pct:>5.1f}%)\n"

        report += f"\n{sep}\n"

        print(report)

        # Guardar reporte
        output_file = self.log_file.parent / f"backtest_{self.log_file.stem}.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"💾 Reporte guardado en: {output_file}")

    def run(self):
        """Ejecuta el backtest completo"""
        self.parse_log()
        if not self.trades:
            print("❌ No se encontraron trades en el log")
            return

        self.apply_filter()
        self.generate_report()


def main():
    print("\n🔬 BACKTEST DEL FILTRO DE CALIDAD DE TRADES")
    print("Analiza logs históricos para validar efectividad del filtro\n")

    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        # Buscar el log más reciente en trades_live/
        trades_live = Path("trades_live")
        if not trades_live.exists():
            print("❌ Directorio trades_live/ no encontrado")
            print("Uso: python backtest.py [ruta_al_log.txt]")
            return

        logs = list(trades_live.glob("whales_*.txt"))
        if not logs:
            print("❌ No se encontraron logs en trades_live/")
            return

        # Tomar el más reciente
        log_file = max(logs, key=lambda p: p.stat().st_mtime)
        print(f"📂 Usando log más reciente: {log_file.name}")

    try:
        backtester = BacktestEngine(log_file)
        backtester.run()
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
