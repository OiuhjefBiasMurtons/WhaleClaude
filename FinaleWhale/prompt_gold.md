# PROMPT PARA CLAUDE CODE — Actualizar `definitive_all_claude.py` a v3.0

## Contexto

Tengo un script ` definitive_all_claude.py` que clasifica señales de ballenas en Polymarket. Necesito crear una nueva version actualizada con los siguientes parametros, que consolida todos los aprendizajes del análisis de 460 señales (332 resueltas) de Feb 2026.


---

## CAMBIOS REQUERIDOS

### 1. ELIMINAR estas reglas (obsoletas / refutadas por datos)

```
❌ edge_pct > 0 como bonus positivo
   Motivo: WR=30.6% cuando edge>0 vs 47.9% sin él. Es señal NEGATIVA.
   Acción: eliminar cualquier lógica que mejore confianza por edge_pct > 0.

❌ Tier blacklist para señal S2 (Follow NBA)
   Motivo: En NBA precio 0.50-0.60, tiers "malos" rinden MEJOR:
   HIGH RISK → 74%, RISKY → 100% vs SILVER → 60%, BRONZE → 58%
   Acción: no aplicar blacklist de tiers cuando señal S2 esté activa.

❌ Regla "counter al trader con peor WR en conflicto"
   Motivo: Refutado por caso Spurs vs Pistons (Feb 2026).
   daschnoodle WR=25% apostó Spurs → GANÓ.
   auggl00p WR=43.8% apostó Pistons → PERDIÓ.
   Con N < 15 trades resueltos, WR individual no es señal confiable.
   Acción: eliminar esta regla completamente.

❌ Jerarquía de capital como predictor de WR
   Motivo: Capital >$10K no mejora WR ($10K+ WR=47.6% vs $3-10K WR=51.5%).
   Acción: mantener solo el mínimo de $3K como filtro de corte.
```

### 2. ACTUALIZAR señales con rangos corregidos

**S1: Counter HIGH RISK**
- Límite superior: precio < 0.45 (sin cambio)
- Nueva sub-zona: precio 0.40–0.44 → WR counter = 88.2% (N=17) ← zona más fuerte
- Sub-zona baja: precio < 0.40 → WR counter = 71.4% (N=14)
- Reportar esta distinción en `reasoning` y ajustar `win_rate_hist` según zona

**S2: Follow NBA 0.50–0.60**
- Sin cambios en el rango
- Eliminar cualquier penalización por tier en NBA (todos los tiers son válidos para S2)

**S2+: Consensus boost**
- Condición: 3+ ballenas mismo mercado NBA mismo lado
- SOLO aplicar boost si precio promedio 0.50–0.60 Y todas las ballenas dentro del rango
- Si alguna ballena está fuera del rango 0.50–0.60: NO aplicar boost (dispersión alta)

**S3: Follow Nicho fuera de NBA**
- Sin cambios. Mantener stake_multiplier = 0.5

**S4: Counter Crypto**
- Aplicar automáticamente solo a mercados "Up/Down" intraday (título contiene "up or down")
- Para otros mercados crypto: generar warning pero no activar S4 automáticamente

**S5: Counter Fútbol SILVER**
- Sin cambios en condición
- Actualizar win_rate_hist a 66.7% (antes 80%, ahora N=6)

### 3. ACTUALIZAR listas de traders

```python
# WHITELIST_A (stake 1.5x si pasa filtro de precio):
WHITELIST_A = ['hioa', 'KeyTransporter']
# synnet baja a B: N=1, insuficiente para auto-ejecutar

# WHITELIST_B (ejecutar normal):
WHITELIST_B = ['elkmonkey', 'gmanas', 'swisstony', 'synnet']
# swisstony nuevo: WR 71.4% con N=7

# BLACKLIST (nunca seguir, evaluar counter):
BLACKLIST = ['sovereign2013', 'BITCOINTO500K', '432614799197', 'xdoors']
# daschnoodle: NO añadir — N<10, falso negativo confirmado
# RN1: mantener neutralizado (WR 50%, sin señal)

# NUEVO PARÁMETRO:
TRADER_MIN_TRADES_FOR_SIGNAL = 15
# Umbral mínimo para usar WR individual como señal independiente
```

### 4. ACTUALIZAR resolución de conflictos

Reemplazar la lógica actual de conflictos por este árbol:

```
CASO 1: S1 + S2 apuntan al MISMO equipo
→ DOBLE CONFIRMACIÓN
→ action = el de ambas señales, confidence = "HIGH", stake_multiplier = 1.5
→ reasoning: "DOBLE CONFIRMACIÓN S1+S2 — WR histórico combinado ~85%"

CASO 2: S1 (counter) vs S2 (follow) apuntan a equipos DISTINTOS
→ S1 PREVALECE
→ action = COUNTER (S1), reasoning: "S1 prevalece sobre S2 (80% vs 72% WR)"

CASO 3: Dos señales HIGH RISK en lados opuestos
→ IGNORAR siempre
→ NO desempatar por WR del trader si N < TRADER_MIN_TRADES_FOR_SIGNAL
→ reasoning: "Conflicto HIGH RISK sin resolución — IGNORAR"
→ Solo considerar WR individual si ambos traders tienen N >= 15 resueltos

CASO 4: Conflicto sin HIGH RISK
→ Prevalece la señal con precio más cercano a 0.55
```

### 5. AÑADIR nuevos warnings

```python
# Si mercado tiene "crypto" pero NO "up or down":
"⚠️  S4 aplica solo a crypto intraday Up/Down. Para crypto largo plazo, validar manualmente."

# Si trader tiene N < 15 trades resueltos (cuando se tiene este dato):
"⚠️  Trader con N<15 trades resueltos. WR histórico no es señal confiable todavía."

# Si precio > 0.75:
"🔴 Precio >0.75: WR bueno (78.6%) pero payout destruye EV. $10 a 0.80 gana solo $2.50."

# Si precio 0.45–0.49 (zona muerta):
"⚠️  Precio en zona 0.45–0.49: underdog sin señal activa. No activa S1 ni S2."

# Si edge_pct > 0 aparece en los datos:
"🔴 edge_pct > 0 es paradójicamente negativo (WR 30.6%). Ignorar como factor positivo."
```

---

## INTERFAZ QUE DEBE MANTENERSE EXACTAMENTE IGUAL

```python
# Función pública — mismos parámetros, mismo output:
def classify(
    market_title: str,
    tier: str,
    poly_price: float,
    is_nicho: bool = False,
    valor_usd: float = 5000,
    side: str = "BUY",
    display_name: str = "Unknown",
    edge_pct: float = 0.0,
) -> dict:
    # Retorna:
    {
        "action":          str,   # "FOLLOW" | "COUNTER" | "IGNORE"
        "signal_id":       str,   # "S1" | "S2" | "S2+" | "S3" | "S4" | "S5" | "S1+S2" | "NONE"
        "confidence":      str,   # "HIGH" | "MEDIUM" | "LOW" | "—"
        "win_rate_hist":   float,
        "expected_roi":    float,
        "payout_mult":     float,
        "reasoning":       list,
        "warnings":        list,
        "category":        str,   # "NBA" | "CRYPTO" | "SOCCER" | "ESPORTS" | "TENNIS" | "OTHER"
    }
```

Los modos CLI (`--csv`, `--interactive`, `--single`, demo por defecto) deben seguir funcionando sin cambios.

---

## CASOS DE TEST OBLIGATORIOS

```python
# Test 1: S1 zona fuerte (0.40–0.44)
classify("Jazz vs. Grizzlies", "💀 HIGH RISK", 0.42, False, 8000)
# → action="COUNTER", signal_id="S1", win_rate_hist=88.2

# Test 2: S1 zona normal (<0.40)
classify("Nuggets vs Warriors", "💀 HIGH RISK", 0.35, False, 12000)
# → action="COUNTER", signal_id="S1", win_rate_hist=71.4

# Test 3: S2 con tier HIGH RISK — DEBE PASAR (antes era bloqueado)
classify("Celtics vs. Lakers", "💀 HIGH RISK", 0.55, False, 9000)
# → action="FOLLOW", signal_id="S2"

# Test 4: Crypto intraday
classify("Bitcoin Up or Down - March 1, 2AM ET", "🥇 GOLD", 0.52, False, 4500)
# → action="COUNTER", signal_id="S4"

# Test 5: Crypto NO intraday — debe ser IGNORE con warning
classify("Will Bitcoin reach $100K by March 2026?", "🥈 SILVER", 0.55, False, 5000)
# → action="IGNORE", warnings contiene nota sobre crypto no intraday

# Test 6: Fútbol SILVER con WR actualizado
classify("Will FC Barcelona win on 2026-03-01?", "🥈 SILVER", 0.62, False, 6000)
# → action="COUNTER", signal_id="S5", win_rate_hist=66.7

# Test 7: zona muerta 0.45–0.49
classify("Magic vs. Suns", "💀 HIGH RISK", 0.48, False, 5500)
# → action="IGNORE", warnings contiene aviso zona muerta

# Test 8: precio > 0.75
classify("Spurs vs Pistons", "🥈 SILVER", 0.80, False, 8000)
# → action="IGNORE", warnings contiene aviso payout trampa

# Test 9: Whitelist A boost
classify("Pacers vs. Wizards", "🤖 BOT/MM", 0.55, False, 7000, "BUY", "hioa")
# → action="FOLLOW", signal_id="S2", confidence="HIGH"
# → reasoning menciona whitelist A y stake 1.5x

# Test 10: Blacklist no cancela S2 pero genera warning
classify("Knicks vs. Bulls", "🥉 BRONZE", 0.58, False, 4000, "BUY", "sovereign2013")
# → action="FOLLOW" (S2 activa en NBA)
# → warnings contiene alerta de trader blacklist
```

---

## CHANGELOG A AÑADIR EN DOCSTRING

```
CHANGELOG:
  v3.0 (Feb 2026):
    - ELIMINADO: edge_pct > 0 como bonus (refutado por datos: WR 30.6%)
    - ELIMINADO: tier blacklist para S2 en NBA (HIGH RISK/RISKY ganan más en NBA 0.50-0.60)
    - ELIMINADO: regla counter por peor WR trader (refutado por caso Spurs/Pistons)
    - ELIMINADO: jerarquía de capital como predictor de WR
    - ACTUALIZADO: S1 tiene dos sub-zonas de WR diferente (88.2% en 0.40-0.44, 71.4% en <0.40)
    - ACTUALIZADO: S5 WR corregido a 66.7% (N=6)
    - ACTUALIZADO: S4 solo activa automáticamente en Up/Down intraday
    - ACTUALIZADO: resolución de conflictos — dos HIGH RISK opuestos siempre IGNORAR
    - AÑADIDO: TRADER_MIN_TRADES_FOR_SIGNAL = 15 como umbral mínimo para WR confiable
    - AÑADIDO: swisstony a WHITELIST_B (WR 71.4%, N=7)
    - AÑADIDO: synnet baja de WHITELIST_A a WHITELIST_B (N=1, insuficiente)
    - AÑADIDO: warnings para zona muerta 0.45-0.49, precio >0.75, edge_pct>0
```