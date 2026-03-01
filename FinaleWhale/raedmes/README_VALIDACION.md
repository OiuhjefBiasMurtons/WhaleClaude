# 🔍 Sistema de Validación Automática de Resultados

## 📋 Descripción

El script `validate_whale_results.py` valida automáticamente los resultados de las ballenas deportivas registradas en Supabase, comparando sus apuestas con los resultados finales de los mercados en Polymarket.

---

## ⚙️ Funcionamiento

### 1. Busca trades pendientes
```sql
SELECT * FROM whale_signals
WHERE resolved_at IS NULL
AND detected_at < NOW() - INTERVAL '1 hour';
```

### 2. Para cada trade:
1. Consulta Polymarket API para ver si el mercado se resolvió
2. Obtiene el outcome ganador
3. Compara con la apuesta de la ballena
4. Calcula PnL teórico (con $100 de capital)
5. Actualiza el registro en Supabase

### 3. Genera estadísticas
- Win rate global
- Win rate por tier (GOLD, SILVER, DIAMOND)
- Win rate por edge (Edge Real, Edge Marginal, Sucker Bet)
- PnL promedio

---

## 🚀 Instalación

### Opción 1: Cron Job Automático (Recomendado)

```bash
cd FinaleWhale
./setup_cron.sh
```

Esto configura el script para ejecutarse **cada hora en punto**.

### Opción 2: Cron Manual

```bash
crontab -e
```

Agregar:
```bash
0 * * * * cd /home/nomadbias/GothamCode/CampCode/Python/Whales/Claude/FinaleWhale && python3 validate_whale_results.py >> cron_output.log 2>&1
```

---

## 🧪 Prueba Manual

```bash
cd FinaleWhale
python3 validate_whale_results.py
```

**Output esperado:**
```
================================================================================
🔍 INICIANDO VALIDACIÓN DE RESULTADOS
================================================================================
📊 Encontrados 5 trades pendientes de validación
🔍 Validando trade #1: Will Lakers win on 2026-02-16?
📊 Ganador: Yes | Ballena apostó: Yes (BUY)
💰 Resultado: WIN | PnL teórico: $72.41
✅ Trade 1 actualizado: WIN | PnL: $72.41
⏳ Mercado aún no resuelto
...
================================================================================
📊 RESUMEN DE VALIDACIÓN
================================================================================
✅ Trades validados:     5
✅ Trades actualizados:  3
❌ Errores:              0
================================================================================
📊 ESTADÍSTICAS GLOBALES
================================================================================
📈 Total trades resueltos: 8
✅ Victorias:              5 (62.5%)
❌ Derrotas:               3
💰 PnL teórico total:      $124.50
💰 PnL promedio por trade: $15.56
================================================================================

📊 ESTADÍSTICAS POR TIER
--------------------------------------------------------------------------------
🥇 GOLD              | Trades:    4 | Win Rate:  75.0% | PnL: $  180.00
🥈 SILVER            | Trades:    3 | Win Rate:  33.3% | PnL: $  -50.00
null                 | Trades:    1 | Win Rate: 100.0% | PnL: $   60.00

📊 ESTADÍSTICAS POR EDGE
--------------------------------------------------------------------------------
Edge Real (>3%)       | Trades:    3 | Win Rate:  66.7% | PnL: $  120.00
Edge Marginal (0-3%)  | Trades:    2 | Win Rate:  50.0% | PnL: $   20.00
Sucker Bet (<0%)      | Trades:    3 | Win Rate:  33.3% | PnL: $ -100.00
================================================================================
```

---

## 📊 Cálculo de Resultados

### BUY (Compra)
```python
if whale_outcome == winning_outcome:
    result = 'WIN'
    pnl_teorico = 100 * (1/poly_price - 1)
else:
    result = 'LOSS'
    pnl_teorico = -100
```

**Ejemplo:**
- Ballena compró `Yes` a 0.58
- Mercado resolvió `Yes` → WIN
- PnL = 100 * (1/0.58 - 1) = $72.41

### SELL (Venta)
```python
if whale_outcome != winning_outcome:
    result = 'WIN'
    pnl_teorico = 100 * poly_price - 100
else:
    result = 'LOSS'
    pnl_teorico = -100 * poly_price
```

**Ejemplo:**
- Ballena vendió `Yes` a 0.58
- Mercado resolvió `No` → WIN
- PnL = 100 * 0.58 - 100 = -$42 (recibió $58, pagó $100)

---

## 📁 Archivos de Log

### `whale_validation.log`
Log detallado de todas las validaciones:
```
2026-02-15 14:00:01 - INFO - ================================================
2026-02-15 14:00:01 - INFO - 🔍 INICIANDO VALIDACIÓN DE RESULTADOS
2026-02-15 14:00:01 - INFO - ================================================
2026-02-15 14:00:02 - INFO - 📊 Encontrados 5 trades pendientes de validación
2026-02-15 14:00:03 - INFO - 🔍 Validando trade #1: Will Lakers win on 2026-02-16?
2026-02-15 14:00:04 - INFO - 📊 Ganador: Yes | Ballena apostó: Yes (BUY)
2026-02-15 14:00:04 - INFO - 💰 Resultado: WIN | PnL teórico: $72.41
2026-02-15 14:00:05 - INFO - ✅ Trade 1 actualizado: WIN | PnL: $72.41
```

### `cron_output.log`
Output del cron job (stdout/stderr):
```
2026-02-15 14:00:00 - Iniciando validación automática
2026-02-15 14:00:30 - Validación completada
```

---

## 🔧 Verificación

### Ver cron jobs activos:
```bash
crontab -l
```

### Ver logs en tiempo real:
```bash
# Log de validación
tail -f whale_validation.log

# Output del cron
tail -f cron_output.log
```

### Ver últimas 50 líneas:
```bash
tail -50 whale_validation.log
```

---

## 🎯 Queries Útiles en Supabase

### Ver trades resueltos recientes:
```sql
SELECT
    detected_at,
    display_name,
    market_title,
    side,
    outcome,
    tier,
    result,
    pnl_teorico
FROM whale_signals
WHERE result IS NOT NULL
ORDER BY resolved_at DESC
LIMIT 20;
```

### Win rate por tier:
```sql
SELECT
    tier,
    COUNT(*) as total_trades,
    COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
    ROUND(COUNT(CASE WHEN result = 'WIN' THEN 1 END)::numeric / COUNT(*)::numeric * 100, 1) as win_rate,
    ROUND(AVG(pnl_teorico)::numeric, 2) as avg_pnl
FROM whale_signals
WHERE result IS NOT NULL
GROUP BY tier
ORDER BY win_rate DESC;
```

### PnL acumulado en el tiempo:
```sql
SELECT
    DATE(resolved_at) as fecha,
    COUNT(*) as trades,
    SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) as wins,
    ROUND(SUM(pnl_teorico)::numeric, 2) as pnl_dia
FROM whale_signals
WHERE result IS NOT NULL
GROUP BY DATE(resolved_at)
ORDER BY fecha DESC;
```

---

## ⚠️ Troubleshooting

### El cron no ejecuta:
```bash
# Ver logs del sistema
grep CRON /var/log/syslog

# Verificar que el cron daemon esté corriendo
sudo service cron status
```

### Error de permisos:
```bash
chmod +x validate_whale_results.py
```

### Error de módulos:
```bash
pip3 install supabase requests python-dotenv
```

---

## 📈 Próximas Mejoras (Opcional)

1. **Dashboard web** con Streamlit/Dash
2. **Alertas** cuando win rate baje de cierto threshold
3. **Backtesting** de filtros modificando parámetros
4. **Exportar reportes** PDF/Excel semanales

---

**Creado:** 2026-02-15
**Versión:** 1.0.0
