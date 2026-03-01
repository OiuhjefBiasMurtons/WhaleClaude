# 🔧 Cambios: Timeout 20s + Inclusión de BOT/MM con Advertencia

## 📅 Fecha: 2026-02-15

---

## ✨ Cambios Implementados

### 1. ⏱️ Incremento de Timeout: 10s → 20s

**Problema:**
- Con timeout de 10s, casi ningún análisis completaba a tiempo (~0%)
- Promedio de duración de análisis: **30-35 segundos**
- Los mensajes iniciales raramente incluían tier del trader

**Solución:**
- Incrementar timeout a **20 segundos**
- Mayor probabilidad de incluir tier en mensaje inicial (~15-25% de casos)
- Sin impacto en latencia (detección sigue siendo inmediata)

**Cambio en código:**
```python
# Antes (línea 958):
future.result(timeout=10)
logger.info(f"✅ Análisis completado en <10s para {wallet[:10]}...")

# Ahora:
future.result(timeout=20)
logger.info(f"✅ Análisis completado en <20s para {wallet[:10]}...")
```

**Logs esperados:**
```
✅ Análisis completado en <20s para 0xABC123...  → Tier incluido en mensaje inicial
⏱️ Análisis tomando >20s para 0xDEF456...       → Continuará en background
```

---

### 2. 🤖 Inclusión de BOT/MM con Advertencia

**Problema:**
- Traders con tier BOT/MM se filtraban completamente
- A veces los bots tienen información valiosa (liquidez institucional, patrones)
- Usuario no sabía que había traders clasificados como bots

**Solución:**
- Incluir BOT/MM en reportes de Telegram
- Agregar advertencia clara de que es un bot
- Recomendar explícitamente NO copiar

**Cambio en código:**
```python
# Antes (línea 886-889):
tiers_validos = ['SILVER', 'GOLD', 'DIAMOND']
if not any(t in tier.upper() for t in tiers_validos):
    logger.info(f"🔍 Trader {display_name} ({wallet[:10]}...) → {tier} (score: {total}) — No se envía a Telegram")
    return

# Ahora (línea 885-896):
tiers_buenos = ['SILVER', 'GOLD', 'DIAMOND']
tiers_advertencia = ['BOT', 'MM']

es_tier_bueno = any(t in tier.upper() for t in tiers_buenos)
es_bot_mm = any(t in tier.upper() for t in tiers_advertencia)

if not (es_tier_bueno or es_bot_mm):
    logger.info(f"🔍 Trader {display_name} ({wallet[:10]}...) → {tier} (score: {total}) — No se envía a Telegram")
    return

# Encabezado especial para BOT/MM
if es_bot_mm and not es_tier_bueno:
    tg = f"<b>⚠️ ANÁLISIS DE TRADER - BOT/MARKET MAKER</b>\n\n"
    tg += f"⚠️ <b>ADVERTENCIA:</b> Este trader muestra patrones de bot o market maker\n"
    tg += f"💡 <b>Recomendación:</b> No copiar - posible farming de liquidez o arbitraje automatizado\n\n"
else:
    tg = f"<b>🔍 ANÁLISIS DE TRADER</b>\n\n"
```

---

## 📊 Tiers y Comportamiento

### Tiers que se envían a Telegram:

| Tier | Score | Comportamiento | Mensaje |
|------|-------|----------------|---------|
| 💎 **DIAMOND** | 85-100 | ✅ Enviar análisis completo | `🔍 ANÁLISIS DE TRADER` |
| 🥇 **GOLD** | 75-84 | ✅ Enviar análisis completo | `🔍 ANÁLISIS DE TRADER` |
| 🥈 **SILVER** | 65-74 | ✅ Enviar análisis completo | `🔍 ANÁLISIS DE TRADER` |
| 🤖 **BOT/MM** | < 30 | ⚠️ Enviar con advertencia | `⚠️ ANÁLISIS DE TRADER - BOT/MARKET MAKER` |

### Tiers que NO se envían:

| Tier | Score | Razón |
|------|-------|-------|
| 📊 **STANDARD** | 50-64 | Trader promedio, sin edge especial |
| 🥉 **BRONZE** | 45-64 | Principiante o inconsistente |
| ⚠️ **RISKY** | 30-44 | Alto riesgo, mal historial |

---

## 🎯 Ejemplos de Mensajes

### Caso 1: Trader GOLD (normal)
```
🔍 ANÁLISIS DE TRADER

👤 JhonAlexanderHinestroza | 🥇 GOLD
📊 Score: 78/100
📈 PnL: $12,450
🎯 Win Rate: 68.5%
📊 Trades: 245
🏆 Ranking: #123

🧠 ESPECIALIZACIÓN:
  🟢 #12 Sports: +$8,200
  🟢 #45 Politics: +$3,100
  🔴 #234 Crypto: -$1,200

⚽ DETALLE DEPORTIVO:
  🟢 Soccer: +$4,500 (85 trades)
  🟢 Basketball: +$2,800 (42 trades)
  🔴 Tennis: -$600 (18 trades)

🏆 Top Wins:
  +$1,240 — Will Lakers win on 2026-02-10?
  +$980 — Will Real Madrid win La Liga?
  +$750 — NBA Championship winner 2026?

💡 Fuerte en deportes, evitar crypto

🔗 Ver perfil | Analytics
```

### Caso 2: Trader BOT/MM (advertencia)
```
⚠️ ANÁLISIS DE TRADER - BOT/MARKET MAKER

⚠️ ADVERTENCIA: Este trader muestra patrones de bot o market maker
💡 Recomendación: No copiar - posible farming de liquidez o arbitraje automatizado

👤 swisstony | 🤖 BOT/MM
📊 Score: 27/100
📈 PnL: $2,140
🎯 Win Rate: 52.3%
📊 Trades: 1,842
🏆 Ranking: #567

🧠 ESPECIALIZACIÓN:
  🟢 #234 Sports: +$1,200
  🟢 #456 Politics: +$800
  🔴 #789 Crypto: -$500

🏆 Top Wins:
  +$320 — Will Napoli win on 2026-02-15?
  +$280 — US Elections 2026
  +$190 — BTC price prediction

💡 Actividad automatizada detectada - muchos trades pequeños, patrones repetitivos

🔗 Ver perfil | Analytics
```

**Diferencias clave en mensaje BOT/MM:**
- ⚠️ Encabezado con advertencia
- 💡 Recomendación explícita de NO copiar
- Explicación del comportamiento (farming, arbitraje)

---

## 📈 Estadísticas Esperadas

### Con timeout de 20s:

**Escenario conservador:**
- ~20% de análisis completan en <20s → Tier en mensaje inicial
- ~80% de análisis completan en 20-35s → Tier en mensaje separado

**Distribución de tiers (basado en tus logs):**
```
🤖 BOT/MM:    ~30%  → Ahora se envían con advertencia
📊 STANDARD:  ~25%  → No se envían
🥉 BRONZE:    ~20%  → No se envían
⚠️ RISKY:     ~10%  → No se envían
🥈 SILVER:    ~8%   → Se envían
🥇 GOLD:      ~5%   → Se envían
💎 DIAMOND:   ~2%   → Se envían
```

**Antes:**
- Mensajes de análisis enviados: ~15% (solo SILVER+)

**Ahora:**
- Mensajes de análisis enviados: ~45% (SILVER+ y BOT/MM)
- De esos, ~30% son advertencias de BOT/MM

---

## 🔍 Logs de Diagnóstico

### Ver análisis completados:
```bash
cd FinaleWhale
grep "Análisis completado" whale_detector.log | tail -20
```

**Output esperado:**
```
2026-02-15 14:30:15 - INFO - ✅ Análisis completado en <20s para 0xABC123...
2026-02-15 14:32:48 - INFO - ⏱️ Análisis tomando >20s para 0xDEF456... (continuará en background)
2026-02-15 14:35:12 - INFO - ✅ Análisis completado en <20s para 0xGHI789...
```

### Ver traders enviados a Telegram:
```bash
grep "Enviando a Telegram" whale_detector.log | tail -20
```

**Output esperado:**
```
2026-02-15 14:30:22 - INFO - 🔍 Trader ProBettor (0xABC123...) → 🥇 GOLD (score: 78) — Enviando a Telegram
2026-02-15 14:32:56 - INFO - 🔍 Trader swisstony (0xDEF456...) → 🤖 BOT/MM (score: 27) — Enviando a Telegram
2026-02-15 14:35:20 - INFO - 🔍 Trader Newbie (0xGHI789...) → 🥉 BRONZE (score: 48) — No se envía a Telegram
```

### Ver errores de análisis:
```bash
grep "❌ Error en análisis" whale_detector.log | tail -10
```

---

## ⚙️ Configuración Recomendada

### Si recibes demasiados BOT/MM:

**Opción 1: Desactivar BOT/MM temporalmente**
```python
# En línea 887, comentar BOT/MM:
tiers_advertencia = []  # ← Desactiva BOT/MM
```

**Opción 2: Incrementar max_workers para análisis más rápidos**
```python
# En línea 335:
self.analysis_executor = ThreadPoolExecutor(max_workers=3)  # ← era 2
```

**Opción 3: Incrementar timeout a 30s para más tiers en mensaje inicial**
```python
# En línea 972:
future.result(timeout=30)  # ← era 20
```

---

## 🎯 Casos de Uso

### Caso 1: Trader GOLD completa en <20s
```
13:30:00 - 🐋 BALLENA DETECTADA: $5,000 en Will Lakers win?
13:30:00 - ⏱️ Iniciando análisis de ProBettor...
13:30:18 - ✅ Análisis completado en <20s para 0xABC123...
13:30:18 - 📱 Enviando a Telegram mensaje INICIAL con tier GOLD incluido

Mensaje inicial:
🐋 BALLENA CAPTURADA 🐋
💰 Valor: $5,000.00
📊 Mercado: Will Lakers win on 2026-02-16?

👤 TRADER: ProBettor
   🏆 Tier: 🥇 GOLD (Score: 78/100)
   ⚽ PnL Deportes: 🟢 $8,200
   🔗 Ver perfil
```

### Caso 2: Trader BOT/MM completa en 32s
```
13:35:00 - 🐋 BALLENA DETECTADA: $7,200 en Will Napoli win?
13:35:00 - ⏱️ Iniciando análisis de swisstony...
13:35:20 - ⏱️ Análisis tomando >20s para 0xDEF456... (continuará en background)
13:35:20 - 📱 Enviando a Telegram mensaje INICIAL sin tier

Mensaje inicial (13:35:20):
🐋 BALLENA CAPTURADA 🐋
💰 Valor: $7,200.00
📊 Mercado: Will Napoli win on 2026-02-15?

👤 TRADER: swisstony
   🔗 Ver perfil

---

13:35:32 - 🔍 Trader swisstony → 🤖 BOT/MM (score: 27) — Enviando a Telegram
13:35:32 - 📱 Enviando a Telegram análisis completo BOT/MM

Mensaje secundario (13:35:32):
⚠️ ANÁLISIS DE TRADER - BOT/MARKET MAKER

⚠️ ADVERTENCIA: Este trader muestra patrones de bot o market maker
💡 Recomendación: No copiar - posible farming de liquidez o arbitraje automatizado

👤 swisstony | 🤖 BOT/MM
📊 Score: 27/100
...
```

### Caso 3: Trader BRONZE no se envía
```
13:40:00 - 🐋 BALLENA DETECTADA: $3,000 en Will Heat win?
13:40:00 - ⏱️ Iniciando análisis de Newbie...
13:40:28 - ⏱️ Análisis tomando >20s para 0xGHI789... (continuará en background)
13:40:28 - 📱 Enviando a Telegram mensaje INICIAL sin tier

Mensaje inicial (13:40:28):
🐋 BALLENA CAPTURADA 🐋
💰 Valor: $3,000.00
📊 Mercado: Will Heat win on 2026-02-17?

👤 TRADER: Newbie
   🔗 Ver perfil

---

13:40:35 - 🔍 Trader Newbie → 🥉 BRONZE (score: 48) — No se envía a Telegram
(No mensaje secundario)
```

---

## ✅ Validación de Cambios

```bash
cd FinaleWhale

# Validar sintaxis
python3 -m py_compile definitive_all_claude.py
# ✅ Sintaxis válida

# Ejecutar detector
python3 definitive_all_claude.py

# En otra terminal, monitorear logs
tail -f whale_detector.log | grep -E "Análisis|Trader.*→"
```

**Output esperado:**
```
⏱️ Análisis tomando >20s para 0xABC123... (continuará en background)
🔍 Trader ProBettor (0xABC123...) → 🥇 GOLD (score: 78) — Enviando a Telegram
✅ Análisis completado en <20s para 0xDEF456...
🔍 Trader swisstony (0xDEF456...) → 🤖 BOT/MM (score: 27) — Enviando a Telegram
⏱️ Análisis tomando >20s para 0xGHI789... (continuará en background)
🔍 Trader Newbie (0xGHI789...) → 🥉 BRONZE (score: 48) — No se envía a Telegram
```

---

## 🚀 Próximos Pasos

1. **Monitorear logs** durante 2-4 horas para ver distribución de tiers
2. **Revisar mensajes de BOT/MM** en Telegram - si son demasiados, considerar desactivar
3. **Ajustar timeout** si es necesario (probar 25s o 30s)
4. **Incrementar max_workers** si el análisis se atrasa mucho con múltiples ballenas

---

## 📊 Métricas a Observar

**Después de 24 horas:**
1. ¿Cuántos análisis completan en <20s? (objetivo: 20-30%)
2. ¿Cuántos BOT/MM se envían? (típico: 30% de todos los traders)
3. ¿Hay retrasos en detección con múltiples ballenas? (si sí: incrementar max_workers)
4. ¿Los BOT/MM aportan valor o son ruido? (si ruido: desactivar)

---

**Implementado por:** Claude Sonnet 4.5
**Fecha:** 2026-02-15
**Versión:** 2.7.0
