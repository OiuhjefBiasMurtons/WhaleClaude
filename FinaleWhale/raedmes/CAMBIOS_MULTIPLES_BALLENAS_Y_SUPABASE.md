# 🔧 Cambios Implementados - Fix Análisis Múltiple + Supabase Tracking

## 📅 Fecha: 2026-02-15

---

## ✨ Cambios Realizados

### 1. 🐛 Fix: Análisis de Ballenas Múltiples

**Problema:**
Cuando 2 o más ballenas del mismo wallet aparecían simultáneamente:
- Primera ballena: muestra "⏳ Analizando perfil..." en Telegram, inicia análisis
- Segunda ballena: también muestra "⏳ Analizando perfil..." pero el análisis ya está en progreso
- Resultado: Solo la primera ballena recibe el análisis completo, las demás quedan esperando indefinidamente

**Causa raíz:**
```python
# En _analizar_trader_async():
if wallet in self._wallets_analizadas:
    return  # ← Retorna sin hacer nada si ya está analizando

self._wallets_analizadas.add(wallet)
```

Cuando llega la segunda ballena del mismo wallet:
1. Detecta que `wallet` ya está en `_wallets_analizadas`
2. Retorna inmediatamente sin ejecutar análisis
3. El mensaje inicial ya prometió "Analizando perfil..." pero nunca llega

**Solución:**
Eliminado el mensaje "⏳ Analizando perfil..." del mensaje inicial de Telegram. Ahora solo se muestra el tier si ya está disponible en caché.

```python
# ANTES:
if cached_analysis:
    # ... mostrar tier
else:
    telegram_msg += f"   ⏳ <b>Analizando perfil...</b>\n"  # ← Genera expectativa

# AHORA:
if cached_analysis:
    # ... mostrar tier
else:
    # No mostrar nada, no generar expectativa
    telegram_msg += f"\n👤 <b>TRADER:</b> {display_name}\n"
    telegram_msg += f"   🔗 <a href='{profile_url}'>Ver perfil</a>\n"
```

**Comportamiento esperado:**

| Escenario | Mensaje Inicial | Mensaje de Análisis |
|-----------|-----------------|---------------------|
| Primera ballena de wallet nuevo | Sin tier (solo link) | Llega en ~30s si es Silver+ |
| Segunda ballena mismo wallet (antes de análisis) | Sin tier (solo link) | Ya no llega (análisis en progreso) |
| Tercera ballena mismo wallet (después de análisis) | ✅ Muestra tier inmediatamente | Ya no envía (ya se envió) |

**Ventajas:**
- ✅ No genera expectativas falsas
- ✅ Si hay tier en caché, se muestra inmediatamente
- ✅ Si no hay tier, simplemente no se muestra (sin promesas)
- ✅ El análisis completo se envía solo UNA VEZ por wallet

---

### 2. 📊 Nueva Funcionalidad: Tracking en Supabase

**Objetivo:**
Registrar automáticamente todas las ballenas deportivas en Supabase para poder:
1. Contrastar apuestas con resultados finales
2. Calcular precisión de las ballenas
3. Validar efectividad de los filtros
4. Analizar ROI teórico

**Implementación:**

#### A) Configuración (`.env`)
```env
SUPABASE_URL=https://enacybjlovvzvyoleeic.supabase.co
SUPABASE_KEY=sb_publishable_H__5cyFllruKLA9L4tL9zw_ceDalLRA
```

#### B) Instalación de dependencia
```bash
pip3 install supabase
```

#### C) Cliente de Supabase en `__init__`
```python
# Cliente de Supabase para tracking de ballenas deportivas
self.supabase: Client | None = None
if SUPABASE_ENABLED and SUPABASE_URL and SUPABASE_KEY:
    try:
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase conectado para tracking de ballenas deportivas")
    except Exception as e:
        logger.warning(f"⚠️ Error conectando a Supabase: {e}")
```

#### D) Método `_registrar_en_supabase()`
```python
def _registrar_en_supabase(self, trade, valor, price, wallet, edge_result, es_nicho):
    """Registra ballena deportiva en Supabase para tracking automático de resultados"""
    if not self.supabase:
        return

    try:
        # Obtener tier del caché si existe
        cached_analysis = self.analysis_cache.get(wallet, None)
        tier = cached_analysis.get('tier', '') if cached_analysis else None

        # Preparar datos para inserción
        data = {
            'detected_at': datetime.now().isoformat(),
            'market_title': trade.get('title', ''),
            'condition_id': trade.get('conditionId', trade.get('market', '')),
            'side': trade.get('side', '').upper(),
            'poly_price': float(price),
            'valor_usd': float(valor),
            'wallet': wallet,
            'tier': tier,
            'edge_pct': float(edge_result.get('edge_pct', 0)),
            'is_nicho': es_nicho,
            'outcome': trade.get('outcome', ''),
            # Campos de resultado se dejan NULL para llenarse después
            'resolved_at': None,
            'result': None,
            'pnl_teorico': None
        }

        # Insertar en Supabase
        self.supabase.table('whale_signals').insert(data).execute()
        logger.info(f"📊 Ballena deportiva registrada en Supabase: {data['market_title'][:50]}")

    except Exception as e:
        logger.warning(f"⚠️ Error registrando en Supabase: {e}")
```

#### E) Integración en `_log_ballena()`
```python
# Información del usuario
wallet = trade.get('proxyWallet', 'N/A')

# Registrar en Supabase si es mercado deportivo
if edge_result.get('is_sports', False):
    self._registrar_en_supabase(trade, valor, price, wallet, edge_result, es_nicho)
```

**Estructura de la tabla `whale_signals`:**

```sql
whale_signals (
    id          SERIAL PRIMARY KEY,
    detected_at TIMESTAMP,
    market_title TEXT,
    condition_id TEXT,
    side        TEXT,         -- BUY/SELL
    poly_price  FLOAT,
    valor_usd   FLOAT,
    wallet      TEXT,
    tier        TEXT,         -- GOLD, SILVER, etc.
    edge_pct    FLOAT,        -- diferencia con Pinnacle
    is_nicho    BOOLEAN,
    -- resultado (se llena después)
    resolved_at TIMESTAMP,
    outcome     TEXT,         -- YES/NO
    result      TEXT,         -- WIN/LOSS/PUSH
    pnl_teorico FLOAT         -- ganancia/pérdida teórica con $100 de capital
);
```

**Campos que se registran automáticamente:**

| Campo | Fuente | Ejemplo |
|-------|--------|---------|
| `detected_at` | datetime.now() | "2026-02-15T14:30:22" |
| `market_title` | trade.title | "Will Lakers win on 2026-02-16?" |
| `condition_id` | trade.conditionId | "0xABC123..." |
| `side` | trade.side | "BUY" |
| `poly_price` | trade.price | 0.58 |
| `valor_usd` | Calculado (size * price) | 4076.64 |
| `wallet` | trade.proxyWallet | "0xDEF456..." |
| `tier` | analysis_cache | "🥇 GOLD" |
| `edge_pct` | SportsEdgeDetector | -1.8 (sucker bet) |
| `is_nicho` | Umbral dinámico | true (4% del mercado) |
| `outcome` | trade.outcome | "Yes" |

**Campos que se llenan después (proceso automático):**

| Campo | Se llenará cuando | Propósito |
|-------|-------------------|-----------|
| `resolved_at` | El mercado se resuelva | Timestamp de resolución |
| `result` | Se compare con outcome | "WIN", "LOSS", "PUSH" |
| `pnl_teorico` | Se calcule resultado | +$72.41 (si ganó) o -$100 (si perdió) |

**Ejemplo de registro:**

```json
{
  "detected_at": "2026-02-15T14:30:22.123Z",
  "market_title": "Will Lakers win on 2026-02-16?",
  "condition_id": "0xABC123...",
  "side": "BUY",
  "poly_price": 0.58,
  "valor_usd": 4076.64,
  "wallet": "0xDEF456...",
  "tier": "🥇 GOLD",
  "edge_pct": -1.8,
  "is_nicho": false,
  "outcome": "Yes",
  "resolved_at": null,
  "result": null,
  "pnl_teorico": null
}
```

**Log esperado en consola:**
```
📊 Ballena deportiva registrada en Supabase: Will Lakers win on 2026-02-16?
```

---

## 🎯 Casos de Uso

### Caso 1: Primera ballena de un wallet nuevo
```
🐋 BALLENA CAPTURADA 🐋

💰 Valor: $4,076.00
📊 Mercado: Will Lakers win on 2026-02-16?
🎯 YES | 📈 COMPRA | 💵 0.58 (58%)

👤 TRADER: ProBettor
   🔗 https://polymarket.com/profile/0x...

📊 Odds Pinnacle: 0.56 (56.0%)
📊 Edge: -1.8% ❌
⚠️⚠️ SUCKER BET - Pagando 1.8% MÁS que Pinnacle

🔗 Mercado: https://polymarket.com/event/...
```

**En consola:**
```
📊 Ballena deportiva registrada en Supabase: Will Lakers win on 2026-02-16?
```

**En Supabase:**
```
✅ Nuevo registro insertado con tier=null (aún no analizado)
```

---

### Caso 2: Segunda ballena del mismo wallet (5 segundos después)
```
🐋 BALLENA CAPTURADA 🐋

💰 Valor: $2,100.00
📊 Mercado: Will Lakers score 110+ points?
🎯 YES | 📈 COMPRA | 💵 0.62 (62%)

👤 TRADER: ProBettor
   🔗 https://polymarket.com/profile/0x...

📊 Odds Pinnacle: 0.60 (60.0%)
📊 Edge: -2.0% ❌

🔗 Mercado: https://polymarket.com/event/...
```

**Nota:**
- ✅ No muestra "⏳ Analizando perfil..." (análisis ya en progreso)
- ✅ Tampoco recibe segundo mensaje de análisis (ya fue enviado)

**En Supabase:**
```
✅ Nuevo registro insertado con tier=null
```

---

### Caso 3: Tercera ballena del mismo wallet (después del análisis)
```
🐋 BALLENA CAPTURADA 🐋

💰 Valor: $3,500.00
📊 Mercado: Will Celtics win on 2026-02-17?
🎯 YES | 📈 COMPRA | 💵 0.55 (55%)

👤 TRADER: ProBettor
   🏆 Tier: 🥇 GOLD (Score: 78/100)
   ⚽ PnL Deportes: 🟢 $4,200
   🔗 https://polymarket.com/profile/0x...

📊 Odds Pinnacle: 0.52 (52.0%)
📊 Edge: +3.0% ✅

🔗 Mercado: https://polymarket.com/event/...
```

**Nota:**
- ✅ Tier aparece inmediatamente (ya en caché)
- ✅ No envía segundo mensaje de análisis (ya fue enviado)

**En Supabase:**
```
✅ Nuevo registro insertado con tier="🥇 GOLD"
```

---

## 📊 Análisis Futuro con los Datos

Una vez que los mercados se resuelvan, podrás ejecutar un script automático (cada hora) que:

1. **Busque mercados resueltos:**
   ```sql
   SELECT * FROM whale_signals
   WHERE resolved_at IS NULL
   AND detected_at < NOW() - INTERVAL '1 day';
   ```

2. **Consulte Polymarket API** para obtener resultado:
   ```python
   market_data = get_market_result(condition_id)
   winning_outcome = market_data['winning_outcome']
   ```

3. **Compare con la apuesta de la ballena:**
   ```python
   if signal['outcome'] == winning_outcome:
       result = 'WIN'
       pnl_teorico = 100 * (1/signal['poly_price'] - 1)
   else:
       result = 'LOSS'
       pnl_teorico = -100
   ```

4. **Actualice el registro:**
   ```sql
   UPDATE whale_signals
   SET resolved_at = NOW(),
       result = 'WIN',
       pnl_teorico = 72.41
   WHERE id = 123;
   ```

5. **Genere métricas:**
   ```sql
   -- Precisión general
   SELECT
       COUNT(CASE WHEN result = 'WIN' THEN 1 END) * 100.0 / COUNT(*) as win_rate
   FROM whale_signals
   WHERE result IS NOT NULL;

   -- ROI por tier
   SELECT
       tier,
       AVG(pnl_teorico) as avg_roi,
       COUNT(*) as total_trades
   FROM whale_signals
   WHERE result IS NOT NULL
   GROUP BY tier;

   -- Precisión por edge
   SELECT
       CASE
           WHEN edge_pct > 3 THEN 'Edge Real (>3%)'
           WHEN edge_pct > 0 THEN 'Edge Marginal (0-3%)'
           ELSE 'Sucker Bet (<0%)'
       END as edge_category,
       COUNT(CASE WHEN result = 'WIN' THEN 1 END) * 100.0 / COUNT(*) as win_rate
   FROM whale_signals
   WHERE result IS NOT NULL
   GROUP BY edge_category;
   ```

---

## 🔧 Archivos Modificados

### `definitive_all_claude.py`

**Línea 22-23:** Importar Supabase
```python
from supabase import create_client, Client
```

**Línea 31-34:** Configuración de Supabase
```python
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)
```

**Línea 337-343:** Cliente en `__init__`
```python
self.supabase: Client | None = None
if SUPABASE_ENABLED and SUPABASE_URL and SUPABASE_KEY:
    try:
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase conectado para tracking de ballenas deportivas")
    except Exception as e:
        logger.warning(f"⚠️ Error conectando a Supabase: {e}")
```

**Línea 542-571:** Método `_registrar_en_supabase()`
```python
def _registrar_en_supabase(self, trade, valor, price, wallet, edge_result, es_nicho):
    """Registra ballena deportiva en Supabase para tracking automático de resultados"""
    # ... implementación
```

**Línea 655-657:** Llamada en `_log_ballena()`
```python
if edge_result.get('is_sports', False):
    self._registrar_en_supabase(trade, valor, price, wallet, edge_result, es_nicho)
```

**Línea 766-768:** Fix mensaje de análisis
```python
# ANTES: telegram_msg += f"   ⏳ <b>Analizando perfil...</b>\n"
# AHORA: Solo link, sin promesa de análisis
```

### `.env`

**Línea 4-5:** Credenciales agregadas
```env
SUPABASE_KEY=sb_publishable_H__5cyFllruKLA9L4tL9zw_ceDalLRA
SUPABASE_URL=https://enacybjlovvzvyoleeic.supabase.co
```

---

## ✅ Validación

```bash
cd FinaleWhale
python3 -m py_compile definitive_all_claude.py
# ✅ Sintaxis válida

pip3 list | grep supabase
# supabase 2.14.0
```

---

## 🚀 Uso

```bash
cd FinaleWhale
python3 definitive_all_claude.py
```

**Output esperado al iniciar:**
```
🚀 Monitor iniciado. Umbral: $2,500.00
✅ Supabase conectado para tracking de ballenas deportivas
```

**Output cuando se captura ballena deportiva:**
```
================================================================================
🐋 BALLENA DETECTADA 🐋
================================================================================
💰 Valor: $4,076.64 USD
📊 Mercado: Will Lakers win on 2026-02-16?
...
📊 Ballena deportiva registrada en Supabase: Will Lakers win on 2026-02-16?
```

---

## 🎯 Próximos Pasos (Opcional)

Para automatizar la validación de resultados:

1. **Crear script `validate_results.py`:**
   ```python
   # Cada hora, buscar mercados resueltos y actualizar
   supabase.table('whale_signals').select('*').is_('resolved_at', 'null').execute()
   ```

2. **Configurar cron job:**
   ```bash
   0 * * * * cd /path/to/FinaleWhale && python3 validate_results.py
   ```

3. **Dashboard de métricas** (opcional):
   - Win rate por tier
   - ROI promedio
   - Precisión de filtros de edge

---

**Implementado por:** Claude Sonnet 4.5
**Fecha:** 2026-02-15
**Versión:** 2.4.0
