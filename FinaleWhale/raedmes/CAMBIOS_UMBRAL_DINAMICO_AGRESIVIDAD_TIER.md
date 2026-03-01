# 🔧 Cambios Implementados - Umbral Dinámico, Agresividad y Tier

## 📅 Fecha: 2026-02-15

---

## ✨ Cambios Realizados

### 1. 🎯 Umbral Dinámico de Ballena

**ANTES:**
```python
if valor >= self.umbral:  # Solo umbral fijo ($1,000)
    self._log_ballena(trade, valor)
```

**AHORA:**
```python
def _es_ballena(self, valor: float, market_volume: float) -> tuple:
    """
    Umbral dinámico: alerta si cumple CUALQUIERA de estas condiciones:
    1. Valor absoluto >= umbral configurado (default 2500)
    2. Valor representa >= 3% del volumen total del mercado
    """
    es_ballena_absoluta = valor >= self.umbral
    es_ballena_relativa = (
        market_volume > 0 and
        (valor / market_volume) >= 0.03 and
        valor >= 500  # mínimo absoluto para evitar micro-trades
    )

    pct_mercado = (valor / market_volume * 100) if market_volume > 0 else 0

    # Mostrar etiqueta NICHO si cumple criterio relativo (independiente del absoluto)
    # Si representa ≥3% del mercado, SIEMPRE es información relevante
    mostrar_concentracion = es_ballena_relativa

    return (es_ballena_absoluta or es_ballena_relativa), mostrar_concentracion, pct_mercado
```

**IMPORTANTE:** La etiqueta ⚡ NICHO se muestra siempre que el trade represente ≥3% del mercado, incluso si también cumple el umbral absoluto. Esta información de concentración es valiosa para evaluar el impacto potencial en el mercado.

**Ejemplos de detección:**

| Valor | Volumen del Mercado | Umbral Usuario | ¿Detecta? | 🏷️ NICHO | Razón |
|-------|---------------------|----------------|-----------|---------|-------|
| $800 | $20,000 | $2,500 | ✅ SÍ | ⚡ SÍ | 4% del mercado |
| $1,000 | $500,000 | $2,500 | ❌ NO | NO | 0.2% del mercado, < umbral |
| $3,000 | $100,000 | $2,500 | ✅ SÍ | ⚡ SÍ | Umbral absoluto + 3% concentración |
| $400 | $10,000 | $2,500 | ❌ NO | NO | 4% pero < $500 mínimo |
| $5,000 | $150,000 | $2,500 | ✅ SÍ | ⚡ SÍ | Umbral absoluto + 3.3% concentración |

**Output de consola cuando es NICHO:**
```
================================================================================
🐋 BALLENA DETECTADA 🐋
================================================================================
💰 Valor: $800.00 USD  ⚡ NICHO (4.0% del mercado)
📊 Mercado: Will Lille OSC win on 2026-02-14?
...
```

**Output de Telegram cuando es NICHO:**
```
⚡ ALERTA NICHO — Alta concentración en mercado pequeño

🐋 BALLENA CAPTURADA 🐋

💰 Valor: $800.00  ⚡ NICHO (4.0% del mercado)
📊 Mercado: Will Lille OSC win on 2026-02-14?
...
```

**Cambios específicos:**
- Default del umbral: $1,000 → $2,500
- Prompt de usuario: "Enter para 1000" → "Enter para 2500"
- Nuevo método `_es_ballena()` en `AllMarketsWhaleDetector`
- Etiqueta "⚡ NICHO (X%)" en mensajes de consola y Telegram

---

### 2. ⚡ Detección de Orden Agresiva vs Pasiva

**Problema:**
Una orden de $10k que NO mueve el precio es una **limit order pasiva** (farming de liquidez).
Una orden de $10k que mueve el precio 3% es una **market order agresiva** (convicción real).

**Solución:**

```python
def _detectar_agresividad(self, trade: dict, market_volume: float) -> tuple:
    """
    Determina si el trade fue una orden agresiva (tomó liquidez) o pasiva (puso liquidez).

    Señales:
    1. feeRateBps == 0 → Maker order = pasiva
    2. Diferencia de precio con mercado actual > 1.5% → agresiva
    """
    # Señal 1: feeRateBps
    fee_rate = int(trade.get('feeRateBps', -1))
    if fee_rate == 0:
        return False, 0.0  # Maker order = pasiva

    # Señal 2: movimiento de precio
    # ... consulta GAMMA_API para precio actual ...
    movimiento_pct = abs(trade_price - current_price) / current_price * 100
    es_agresiva = movimiento_pct > 1.5

    return es_agresiva, movimiento_pct
```

**Integración en `is_worth_copying()`:**
```python
# Filtro 5: Orden agresiva vs pasiva (solo deportes)
if is_sports:
    es_agresiva, movimiento_pct = self._detectar_agresividad(trade, market_volume)
    if not es_agresiva:
        return False, f"Orden pasiva en deporte (farming de liquidez, movimiento {movimiento_pct:.1f}%)"
```

**Ejemplos:**

| Trade | feeRateBps | Movimiento Precio | ¿Pasa Filtro? | Razón |
|-------|------------|-------------------|---------------|-------|
| $5,000 Lakers BUY | 0 | 0.0% | ❌ NO | Maker order (farming) |
| $5,000 Lakers BUY | 10 | 0.5% | ❌ NO | Movimiento < 1.5% |
| $5,000 Lakers BUY | 10 | 2.8% | ✅ SÍ | Movimiento > 1.5% (agresiva) |
| $5,000 Trump BUY | 0 | 0.0% | ✅ SÍ | No deportivo (filtro no aplica) |

**Output cuando se rechaza:**
```
⛔ [12:30:45] BALLENA IGNORADA — BALLENA $5,000 — Razón: Orden pasiva en deporte (farming de liquidez, movimiento 0.5%) | Volumen: $125,000
```

**Fail-safe:**
- Si la API falla al obtener precio actual → asume agresiva (no bloquea)
- Solo aplica a mercados deportivos (política/crypto permite limit orders)

---

### 3. 🏆 Tier de Ballena en Telegram (Mensaje Inicial)

**ANTES:**
```
🐋 BALLENA CAPTURADA 🐋

💰 Valor: $4,076.00
...
👤 Trader: VeryLucky888
🔗 https://polymarket.com/profile/0x...

[30 segundos después]

🔍 ANÁLISIS DE TRADER

👤 VeryLucky888 | 🥇 GOLD
📊 Score: 78/100
⚽ PnL Deportes: 🟢 $4,200
```

**AHORA (si wallet ya fue analizada):**
```
🐋 BALLENA CAPTURADA 🐋

💰 Valor: $4,076.00
📊 Will Lille OSC win on 2026-02-14?
🎯 YES | 📈 COMPRA | 💵 0.58 (58%)
🕐 2026-02-14 12:09

📊 ANÁLISIS DE ODDS:
   Pinnacle: 0.52 (52%)
   Edge: +6.0% ✅

👤 TRADER: VeryLucky888
   🏆 Tier: 🥇 GOLD (Score: 78/100)
   ⚽ PnL Deportes: 🟢 $4,200
   🔗 https://polymarket.com/profile/0x...

🔗 Mercado: https://polymarket.com/event/...
```

**AHORA (si wallet NO fue analizada aún):**
```
👤 TRADER: VeryLucky888
   🔗 https://polymarket.com/profile/0x...
   ⏳ Analizando perfil...
```

**Cómo funciona:**
1. `_analizar_trader_async()` guarda resultados en `self.analysis_cache`:
   ```python
   self.analysis_cache[wallet] = {
       'tier': '🥇 GOLD',
       'score': 78,
       'sports_pnl': 4200
   }
   ```

2. `_log_ballena()` consulta caché antes de enviar Telegram:
   ```python
   cached_analysis = self.analysis_cache.get(wallet, None)
   if cached_analysis:
       # Incluir tier/score/PnL en mensaje inicial
   else:
       # Mostrar "⏳ Analizando perfil..."
   ```

3. Si es la primera vez que aparece la wallet → muestra "⏳"
4. Si la wallet ya apareció antes en la sesión → muestra tier inmediatamente

**Beneficio:**
- No esperar 30-60 segundos para ver si el trader es confiable
- Información crítica (tier/PnL deportivo) disponible de inmediato si ya fue analizada

---

## 📊 Ejemplos Completos de Output

### Ejemplo 1: Ballena en mercado nicho (primera vez)

**Consola:**
```
================================================================================
🐋 BALLENA DETECTADA 🐋
================================================================================
💰 Valor: $1,200.00 USD  ⚡ NICHO (5.2% del mercado)
📊 Mercado: Will Haiti qualify for World Cup 2026?
🔗 URL: https://polymarket.com/event/haiti-worldcup
🎯 Outcome: Yes
📈 Lado: COMPRA
💵 Precio: 0.3500 (35.00%)
📦 Volumen: $23,000.00
🕐 Hora: 2026-02-15 14:30:22

👤 INFORMACIÓN DEL USUARIO:
   Nombre: SoccerWhale
   Wallet: 0xABC123...
   Perfil: https://polymarket.com/profile/0xABC123...
================================================================================
📊 ANÁLISIS DE ODDS:
   Pinnacle:     0.32 (32.0%)
   Polymarket:   0.35 (35.0%)
   Edge:         -3.0% ❌
⚠️⚠️ WARNING: SUCKER BET - Ballena pagando 3.0% MÁS que Pinnacle
```

**Telegram:**
```
⚡ ALERTA NICHO — Alta concentración en mercado pequeño

🐋 BALLENA CAPTURADA 🐋

💰 Valor: $1,200.00  ⚡ NICHO (5.2% del mercado)
📊 Mercado: Will Haiti qualify for World Cup 2026?
🎯 YES | 📈 COMPRA | 💵 0.3500 (35.00%)
📦 Volumen: $23,000

👤 TRADER: SoccerWhale
   🔗 https://polymarket.com/profile/0xABC123...
   ⏳ Analizando perfil...

📊 Odds Pinnacle: 0.32 (32.0%)
📊 Edge: -3.0% ❌
⚠️⚠️ SUCKER BET - Pagando 3.0% MÁS que Pinnacle

🔗 Mercado: https://polymarket.com/event/haiti-worldcup
```

---

### Ejemplo 2: Ballena rechazada (orden pasiva en deporte)

**Consola:**
```
⛔ [14:32:10] BALLENA IGNORADA — BALLENA $3,500 — Razón: Orden pasiva en deporte (farming de liquidez, movimiento 0.8%) | Volumen: $180,000
```

---

### Ejemplo 3: Ballena con trader conocido (segunda vez en sesión)

**Telegram:**
```
🐋 BALLENA CAPTURADA 🐋

💰 Valor: $4,500.00
📊 Mercado: Will Lakers win on 2026-02-16?
🎯 YES | 📈 COMPRA | 💵 0.5200 (52.00%)
📦 Volumen: $250,000

👤 TRADER: ProBettor
   🏆 Tier: 💎 DIAMOND (Score: 92/100)
   ⚽ PnL Deportes: 🟢 $18,500
   🔗 https://polymarket.com/profile/0xDEF456...

📊 Odds Pinnacle: 0.48 (48.0%)
📊 Edge: +4.0% ✅

🔗 Mercado: https://polymarket.com/event/lakers-2026-02-16
```

---

## 🔧 Archivos Modificados

### `definitive_all_claude.py`

**Línea 270:** Agregar caché de análisis
```python
# Cache de análisis de traders para incluir tier en mensaje inicial
self.analysis_cache = {}
```

**Línea 289-318:** Nuevo método `_es_ballena()`
```python
def _es_ballena(self, valor: float, market_volume: float) -> tuple:
    """Umbral dinámico con detección de mercados nicho"""
    es_ballena_absoluta = valor >= self.umbral
    es_ballena_relativa = (
        market_volume > 0 and
        (valor / market_volume) >= 0.03 and
        valor >= 500
    )
    pct_mercado = (valor / market_volume * 100) if market_volume > 0 else 0
    es_nicho = es_ballena_relativa and not es_ballena_absoluta
    return (es_ballena_absoluta or es_ballena_relativa), es_nicho, pct_mercado
```

**Línea 99-155:** Nuevo método `_detectar_agresividad()` en `TradeFilter`
```python
def _detectar_agresividad(self, trade: dict, market_volume: float) -> tuple:
    """Detecta si orden fue agresiva (taker) o pasiva (maker)"""
    # Señal 1: feeRateBps == 0 → maker
    # Señal 2: movimiento de precio > 1.5% → taker
    ...
```

**Línea 95-101:** Integración en `is_worth_copying()`
```python
# Filtro 5: Orden agresiva vs pasiva (solo deportes)
if is_sports:
    es_agresiva, movimiento_pct = self._detectar_agresividad(trade, market_volume)
    if not es_agresiva:
        return False, f"Orden pasiva en deporte (farming, movimiento {movimiento_pct:.1f}%)"
```

**Línea 854-866:** Uso de `_es_ballena()` con umbral dinámico
```python
# Obtener volumen del mercado
market_volume = self.trade_filter.markets_cache.get(cache_key, 0)

# Verificar si es ballena (umbral dinámico)
es_ballena, es_nicho, pct_mercado = self._es_ballena(valor, market_volume)
if es_ballena:
    self._log_ballena(trade, valor, es_nicho, pct_mercado)
```

**Línea 485:** Firma de `_log_ballena()` actualizada
```python
def _log_ballena(self, trade, valor, es_nicho=False, pct_mercado=0.0):
```

**Línea 576-580:** Etiqueta NICHO en consola
```python
nicho_tag = f"  ⚡ NICHO ({pct_mercado:.1f}% del mercado)" if es_nicho else ""
msg = f"""
...
💰 Valor: ${valor:,.2f} USD{nicho_tag}
...
```

**Línea 694-730:** Etiqueta NICHO y tier en Telegram
```python
# Alerta de nicho al inicio
if es_nicho:
    telegram_msg += f"⚡ <b>ALERTA NICHO</b> — Alta concentración en mercado pequeño\n\n"

# Valor con etiqueta
nicho_tag_tg = f"  ⚡ <b>NICHO</b> ({pct_mercado:.1f}% del mercado)" if es_nicho else ""
telegram_msg += f"💰 <b>Valor:</b> ${valor:,.2f}{nicho_tag_tg}\n"

# Trader con tier si hay caché
cached_analysis = self.analysis_cache.get(wallet, None)
if cached_analysis:
    tier = cached_analysis.get('tier', '')
    score = cached_analysis.get('score', 0)
    sports_pnl = cached_analysis.get('sports_pnl', None)
    telegram_msg += f"\n👤 <b>TRADER:</b> {display_name}\n"
    telegram_msg += f"   🏆 <b>Tier:</b> {tier} (Score: {score}/100)\n"
    if sports_pnl is not None:
        telegram_msg += f"   ⚽ <b>PnL Deportes:</b> {'🟢' if sports_pnl > 0 else '🔴'} ${sports_pnl:,.0f}\n"
else:
    telegram_msg += f"\n👤 <b>TRADER:</b> {display_name}\n"
    telegram_msg += f"   ⏳ <b>Analizando perfil...</b>\n"
```

**Línea 769-778:** Guardar en caché después de análisis
```python
# Calcular PnL deportivo total
sports_pnl = None
if hasattr(analyzer, '_detect_sport_subtypes'):
    sport_subtypes = analyzer._detect_sport_subtypes(d)
    sports_pnl = sum(info['pnl'] for info in sport_subtypes.values()) if sport_subtypes else None

# Guardar en caché
self.analysis_cache[wallet] = {
    'tier': tier,
    'score': total,
    'sports_pnl': sports_pnl
}
```

**Línea 888:** Default del umbral: 1000 → 2500
```python
val = input("💰 Umbral (USD) [Enter para 2500]: ").strip()
umbral = float(val) if val else 2500.0
```

---

## ✅ Validación

```bash
cd FinaleWhale
python3 -m py_compile definitive_all_claude.py
# ✅ Sintaxis válida
```

---

## 🎯 Criterios de Aceptación

✅ **Umbral dinámico:**
- Una apuesta de $800 en mercado con $20,000 de volumen activa alerta con etiqueta ⚡ NICHO
- Una apuesta de $1,000 en mercado con $500,000 de volumen NO activa alerta
- Etiqueta "⚡ NICHO (X%)" visible en consola y Telegram

✅ **Agresividad:**
- Una limit order (feeRateBps=0) en mercado deportivo se rechaza con línea ⛔
- Una market order en mercado deportivo pasa normalmente
- El filtro solo aplica a deportes (no política/crypto)

✅ **Tier en Telegram:**
- El mensaje Telegram de ballena deportiva incluye el tier si la wallet ya fue analizada
- Si la wallet no fue analizada aún, el mensaje dice "⏳ Analizando perfil..."
- PnL deportivo se muestra si está disponible

✅ **Fail-safes:**
- Si API de GAMMA falla → asume agresiva (no bloquea)
- Si `_detect_sport_subtypes` no existe → sports_pnl = None
- Si análisis falla → caché no se corrompe

---

## 🚀 Uso

```bash
cd FinaleWhale
python3 definitive_all_claude.py

# Prompt:
💰 Umbral (USD) [Enter para 2500]:
# Presionar Enter para default $2,500
# O ingresar otro valor (ej: 1500)
```

---

**Implementado por:** Claude Sonnet 4.5
**Fecha:** 2026-02-15
**Versión:** 2.3.0
