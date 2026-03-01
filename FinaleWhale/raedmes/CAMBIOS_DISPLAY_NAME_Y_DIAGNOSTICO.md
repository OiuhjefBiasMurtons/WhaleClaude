# 🔧 Cambios: Display Name en Supabase + Diagnóstico de Análisis

## 📅 Fecha: 2026-02-15

---

## 🔍 Diagnóstico: ¿Por qué no llega el análisis a Telegram?

### Ballena reportada:
```
💰 Valor: $7,270.12 USD
📊 Mercado: Will SSC Napoli win on 2026-02-15?
👤 Trader: swisstony (0x204f72f35326db932158cba6adff0b9a1da95e14)
🕐 Hora: 2026-02-15 13:24:13
```

### Logs del sistema:
```
2026-02-15 13:33:43,883 - INFO - ⏱️ Análisis tomando >10s para 0x204f72f3... (continuará en background)
2026-02-15 13:34:17,893 - INFO - 🔍 Trader swisstony (0x204f72f3...) → 🤖 BOT/MM (score: 27) — No se envía a Telegram
```

### ✅ Conclusión: El sistema funciona CORRECTAMENTE

**El análisis SÍ se completó:**
- Inicio: 13:33:43
- Fin: 13:34:17
- Duración: **34 segundos** (normal para polywhale_v5)

**¿Por qué no llegó a Telegram?**

El trader `swisstony` obtuvo tier **🤖 BOT/MM** con score de **27/100**.

El sistema solo envía análisis a Telegram para traders de calidad:
- ✅ 🥈 **SILVER** (score 65-74)
- ✅ 🥇 **GOLD** (score 75-84)
- ✅ 💎 **DIAMOND** (score 85+)

Tiers que NO se envían:
- ❌ 🤖 **BOT/MM** (score < 30) — Bots o market makers
- ❌ 🥉 **BRONZE** (score 45-64) — Principiantes
- ❌ ⚠️ **RISKY** (score 30-44) — Traders riesgosos
- ❌ 📊 **STANDARD** (score 50-64) — Promedio

---

## ✨ Cambios Implementados

### 1. 📝 Cambio de `wallet` a `display_name` en Supabase

**Problema:**
- La tabla guardaba wallet addresses (`0x204f72f3...`) en lugar de nombres legibles
- Dificulta el análisis humano de los datos

**Solución:**
- Cambiar columna `wallet` por `display_name`
- Ahora se guarda: `swisstony`, `JhonAlexanderHinestroza`, `Anónimo`, etc.

**Estructura actualizada de la tabla:**
```sql
whale_signals (
    id SERIAL PRIMARY KEY,
    detected_at TIMESTAMP,
    market_title TEXT,
    condition_id TEXT,
    side TEXT,
    poly_price FLOAT,
    valor_usd FLOAT,
    display_name TEXT,  -- ← CAMBIO: antes era "wallet"
    tier TEXT,
    edge_pct FLOAT,
    is_nicho BOOLEAN,
    resolved_at TIMESTAMP,
    outcome TEXT,
    result TEXT,
    pnl_teorico FLOAT
);
```

---

## 🔧 Archivos Modificados

### `definitive_all_claude.py`

**Línea 649-664:** Movido cálculo de `display_name` antes de Supabase
```python
# Información del usuario
wallet = trade.get('proxyWallet', 'N/A')
username = trade.get('name', '')
pseudonym = trade.get('pseudonym', '')
tx_hash = trade.get('transactionHash', 'N/A')

# Determinar el nombre a mostrar
if username and username != '':
    display_name = username
elif pseudonym and pseudonym != '':
    display_name = pseudonym
else:
    display_name = 'Anónimo'

# Registrar en Supabase si es mercado deportivo (antes de enviar a Telegram)
if edge_result.get('is_sports', False):
    self._registrar_en_supabase(trade, valor, price, wallet, display_name, edge_result, es_nicho)
```

**Línea 542:** Firma actualizada
```python
def _registrar_en_supabase(self, trade, valor, price, wallet, display_name, edge_result, es_nicho):
    #                                                        ^^^^^^^^^^^^ nuevo parámetro
```

**Línea 560:** Cambio en diccionario de datos
```python
data = {
    'detected_at': datetime.now().isoformat(),
    'market_title': trade.get('title', ''),
    'condition_id': trade.get('conditionId', trade.get('market', '')),
    'side': trade.get('side', '').upper(),
    'poly_price': float(price),
    'valor_usd': float(valor),
    'display_name': display_name,  # ← CAMBIO: antes era 'wallet': wallet
    'tier': tier,
    'edge_pct': float(edge_result.get('edge_pct', 0)),
    'is_nicho': es_nicho,
    'outcome': trade.get('outcome', ''),
    'resolved_at': None,
    'result': None,
    'pnl_teorico': None
}
```

### `validate_whale_results.py`

**Línea 186-190:** Mostrar nombre de usuario en logs
```python
trade_id = trade['id']
condition_id = trade['condition_id']
market_title = trade['market_title']
display_name = trade.get('display_name', 'Anónimo')

logger.info(f"🔍 Validando trade #{trade_id}: {market_title[:50]} (Trader: {display_name})")
```

### `README_VALIDACION.md`

**Query actualizado:**
```sql
SELECT
    detected_at,
    display_name,  -- ← Agregado
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

---

## 🎯 Casos de Ejemplo

### Caso 1: Trader con nombre de usuario
```python
trade = {
    'name': 'swisstony',
    'pseudonym': '',
    'proxyWallet': '0x204f72f35326db932158cba6adff0b9a1da95e14'
}

# Resultado:
display_name = 'swisstony'  # ← Se guarda en Supabase
```

### Caso 2: Trader con pseudónimo
```python
trade = {
    'name': '',
    'pseudonym': 'JhonAlexanderHinestroza',
    'proxyWallet': '0x44c58184...'
}

# Resultado:
display_name = 'JhonAlexanderHinestroza'
```

### Caso 3: Trader anónimo
```python
trade = {
    'name': '',
    'pseudonym': '',
    'proxyWallet': '0xb72665ae...'
}

# Resultado:
display_name = 'Anónimo'
```

---

## 📊 Ejemplo de Query Mejorado

**Ver top traders por ROI:**
```sql
SELECT
    display_name,
    tier,
    COUNT(*) as total_trades,
    COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
    ROUND(COUNT(CASE WHEN result = 'WIN' THEN 1 END)::numeric / COUNT(*)::numeric * 100, 1) as win_rate,
    ROUND(SUM(pnl_teorico)::numeric, 2) as total_pnl,
    ROUND(AVG(pnl_teorico)::numeric, 2) as avg_pnl
FROM whale_signals
WHERE result IS NOT NULL
GROUP BY display_name, tier
HAVING COUNT(*) >= 3  -- Mínimo 3 trades para ser relevante
ORDER BY total_pnl DESC
LIMIT 20;
```

**Output esperado:**
```
display_name                  | tier    | total_trades | wins | win_rate | total_pnl | avg_pnl
------------------------------|---------|--------------|------|----------|-----------|--------
JhonAlexanderHinestroza       | 💎 DIAMOND |     15      |  12  |   80.0   |  $1,240  |  $82.67
ProBettor                     | 🥇 GOLD    |      8      |   6  |   75.0   |  $  580  |  $72.50
swisstony                     | 🤖 BOT/MM  |      5      |   2  |   40.0   |  $-120   | -$24.00
```

---

## 🔍 Debugging: ¿Por qué mi análisis no llega?

### 1. Ver tier del trader en logs:
```bash
cd FinaleWhale
grep "Trader.*→" whale_detector.log | tail -20
```

**Buscar:**
```
🔍 Trader swisstony (0x204f72f3...) → 🤖 BOT/MM (score: 27) — No se envía a Telegram  ❌
🔍 Trader JhonAlexanderHinestroza (0x44c58184...) → 💎 DIAMOND (score: 93) — Enviando a Telegram  ✅
```

### 2. Verificar análisis completado:
```bash
grep "Análisis" whale_detector.log | tail -10
```

**Buscar:**
```
✅ Análisis completado en <10s para 0xABC123...  → Tier incluido en mensaje inicial
⏱️ Análisis tomando >10s para 0xDEF456...        → Continuará en background
```

### 3. Ver errores de análisis:
```bash
grep "❌ Error en análisis" whale_detector.log | tail -10
```

---

## ✅ Validación de Cambios

```bash
cd FinaleWhale

# Validar sintaxis
python3 -m py_compile definitive_all_claude.py validate_whale_results.py
# ✅ Sintaxis válida

# Probar insert manual en Supabase
python3 -c "
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Test insert
data = {
    'detected_at': '2026-02-15T14:00:00',
    'market_title': 'Test market',
    'condition_id': '0xtest',
    'side': 'BUY',
    'poly_price': 0.5,
    'valor_usd': 1000,
    'display_name': 'test_user',  # ← Nuevo campo
    'tier': 'GOLD',
    'edge_pct': 2.5,
    'is_nicho': False,
    'outcome': 'Yes'
}

result = client.table('whale_signals').insert(data).execute()
print('✅ Insert exitoso:', result.data[0]['id'])
"
```

---

## 🚀 Próximos Pasos

1. **Actualizar tabla en Supabase:**
   ```sql
   ALTER TABLE whale_signals
   RENAME COLUMN wallet TO display_name;
   ```

2. **Verificar registros existentes:**
   ```sql
   SELECT display_name, COUNT(*) as trades
   FROM whale_signals
   GROUP BY display_name
   ORDER BY trades DESC;
   ```

3. **Monitorear nuevas detecciones** para confirmar que `display_name` se guarda correctamente

---

**Implementado por:** Claude Sonnet 4.5
**Fecha:** 2026-02-15
**Versión:** 2.6.0
