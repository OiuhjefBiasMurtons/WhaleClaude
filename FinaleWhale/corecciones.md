# FIXES PARA `gold_all_claude.py` — v3.0 Correcciones

Este documento detalla **10 correcciones** sobre el script actual.
Están ordenadas por prioridad. Cada una incluye el problema exacto,
el fragmento de código que cambia, y qué NO tocar.

No se añade ninguna clase nueva, no se cambia la interfaz pública,
no se tocan los modos CLI. Solo cambios quirúrgicos en funciones existentes.

---

## FIX 1 — CRÍTICO: Recalcular `classify()` con tier real después del análisis async

### Problema
En `_log_ballena()`, el orden actual es:
1. Buscar tier en `analysis_cache` → casi siempre vacío en el primer encuentro con un trader
2. Llamar `classify(tier='')` → S1, S2 y S5 NO se activan porque dependen del tier
3. Llamar `_analizar_trader_async(esperar_resultado=True)` → espera hasta 20s
4. Si completa, actualiza el mensaje de Telegram pero **no recalcula `classification`**

En la práctica, **S1 nunca se activa** porque requiere `'HIGH RISK' in tier_upper`
y `tier_upper` siempre es `''` en el primer encuentro con un trader nuevo.

### Localización
Función `_log_ballena()`. Buscar el bloque:

```python
# --- CLASIFICACIÓN v3.0 ---
classification = classify(
    market_title=trade.get('title', ''),
    tier=trader_tier,
    ...
)

# Consenso multi-ballena
...

# Evaluar S2+ si hay consenso de 3+
...

# Detección de coordinación
...

# Notificación por Telegram
if TELEGRAM_ENABLED:
    ...
    self._analizar_trader_async(
        wallet, display_name, ...
        esperar_resultado=True,
        ...
    )

    # Revisar si el análisis completó y actualizar mensaje
    cached_analysis = self.analysis_cache.get(wallet, None)
    if cached_analysis and ...:
        ...
```

### Cambio
Mover `_analizar_trader_async` ANTES del `classify()`,
y recalcular `classification` con el tier real una vez completado.

Reemplazar el bloque completo desde `# --- CLASIFICACIÓN v3.0 ---`
hasta el final de `_log_ballena()` con esta versión:

```python
        # --- ANÁLISIS DEL TRADER PRIMERO (para obtener tier real) ---
        # Se espera hasta 20s antes de clasificar para que S1/S2/S5
        # puedan activarse con el tier correcto.
        if TELEGRAM_ENABLED:
            self._analizar_trader_async(
                wallet, display_name, trade.get('title', '').lower(),
                esperar_resultado=True,
                trade_data=trade,
                valor=valor,
                price=price,
                edge_result=edge_result,
                es_nicho=es_nicho,
                classification=None  # Se recalculará abajo
            )

        # Leer tier actualizado del cache (puede seguir vacío si tardó >20s)
        cached_analysis = self.analysis_cache.get(wallet, None)
        if cached_analysis:
            trader_tier = cached_analysis.get('tier', '')

        # --- CLASIFICACIÓN v3.0 (con tier real si está disponible) ---
        classification = classify(
            market_title=trade.get('title', ''),
            tier=trader_tier,
            poly_price=price,
            is_nicho=es_nicho,
            valor_usd=valor,
            side=side,
            display_name=display_name,
            edge_pct=edge_result.get('edge_pct', 0.0),
        )

        # Consenso multi-ballena
        condition_id = trade.get('conditionId', trade.get('market', ''))
        self.consensus.add(condition_id, side, valor, wallet, price, trader_tier, display_name)
        is_consensus, count, consensus_side, total_value = self.consensus.get_signal(condition_id)

        # Evaluar S2+ si hay consenso de 3+
        s2plus_result = None
        if is_consensus and count >= 3:
            whale_entries = self.consensus.get_whale_entries(condition_id)
            s2plus_result = classify_consensus(trade.get('title', ''), whale_entries)
            if s2plus_result.get('signal_id') == 'S2+':
                classification = {
                    **classification,
                    'signal_id': 'S2+',
                    'action': 'FOLLOW',
                    'confidence': 'HIGH',
                    'win_rate_hist': 78.1,   # ← FIX 4: era 85.0
                    'reasoning': s2plus_result['reasoning'],
                }

        # Detección de coordinación
        self.coordination.add_trade(condition_id, wallet, side, valor)
        is_coordinated, coord_count, coord_desc, coord_wallets = self.coordination.detect_coordination(
            condition_id, wallet, side
        )
```

Luego continuar con el bloque de URLs, mensaje de consola, y notificación Telegram
**SIN** llamar de nuevo a `_analizar_trader_async` (ya se llamó arriba).

Eliminar el bloque Telegram que llama a `_analizar_trader_async` al final.
El bloque de construcción del mensaje Telegram queda igual, solo que ya no
necesita re-verificar el cache porque se hizo arriba.

### Qué NO tocar
- La función `_analizar_trader_async()` en sí misma no cambia
- Los parámetros de `classify()` no cambian
- El bloque de consola (`print(msg)`) no cambia

---

## FIX 2 — CRÍTICO: Corregir warning de `edge_pct` en `classify()`

### Problema
El warning actual dice:
```python
if edge_pct > 0:
    result["warnings"].append("edge_pct > 0 es paradójicamente negativo...")
```

El CSV del backtest usaba la convención `edge_pct = (poly_price - pinnacle_price) * 100`,
donde `edge_pct > 0` significaba que Poly era MÁS CARO que Pinnacle (malo).

Pero `sports_edge_detector.py` calcula:
```python
edge_pct = (pinnacle_price - poly_price) * 100
```
Aquí `edge_pct > 0` significa que Poly es MÁS BARATO (bueno).
El warning se dispara en el caso correcto y silencia el malo.

`sports_edge_detector` ya maneja esto correctamente con `is_sucker_bet=True`
cuando `edge_pct < 0`. Añadir un warning duplicado y al revés solo genera ruido.

### Localización
En `classify()`, bloque de warnings globales:

```python
# Warning: edge_pct > 0 es paradójicamente negativo
if edge_pct > 0:
    result["warnings"].append(
        "edge_pct > 0 es paradójicamente negativo (WR 30.6%). Ignorar como factor positivo."
    )
```

### Cambio
Reemplazar ese bloque completo por:

```python
# NOTA: edge_pct llega de sports_edge_detector con convención (pinnacle - poly)*100
# edge_pct < 0 = poly más caro que Pinnacle = sucker bet (ya marcado por is_sucker_bet)
# No añadimos warning aquí: sports_edge_detector lo comunica vía is_sucker_bet
# y se muestra explícitamente en el output de Telegram.
```

### Qué NO tocar
- La lógica de `is_sucker_bet` en `sports_edge_detector.py` no cambia
- El bloque Telegram que muestra el edge no cambia
- Los otros warnings de `classify()` no cambian

---

## FIX 3 — CRÍTICO: `_resolve_conflicts` Caso 3 nunca puede activarse

### Problema
El Caso 3 del árbol de decisión (dos HIGH RISK apostando lados opuestos → IGNORAR)
está implementado así:

```python
high_risk_signals = [s for s in signals if 'HIGH RISK' in tier_upper]
if len(high_risk_signals) >= 2:
    ...
```

`tier_upper` es el tier del trade **actual** (un solo trade).
Esta lista siempre tendrá 0 o 1 elemento. Nunca puede ser `>= 2`.
El Caso 3 es una imposibilidad lógica con la implementación actual.

El conflicto de dos HIGH RISK opuestos ocurre cuando llegan dos trades
de distintos traders en el mismo mercado. Esa información está en el
`ConsensusTracker`, no en `_resolve_conflicts`.

### Localización
En `classify()`, al final, antes de los ajustes post-señal:

```python
else:
    result = _resolve_conflicts(signals, result, tier_upper, poly_price)
```

Y en `_resolve_conflicts()`:

```python
high_risk_signals = [s for s in signals if 'HIGH RISK' in tier_upper]
if len(high_risk_signals) >= 2:
    result["action"] = "IGNORE"
    ...
```

### Cambio
**Parte A**: Añadir parámetro `opposite_tier` a `_resolve_conflicts`.
Este parámetro lo pasa `_log_ballena()` cuando detecta que hay ballenas
del lado contrario en el consenso.

Cambiar la firma de la función:
```python
def _resolve_conflicts(signals: list, result: dict, tier_upper: str, poly_price: float,
                       opposite_tier: str = "") -> dict:
```

Reemplazar el bloque del Caso 3 dentro de `_resolve_conflicts`:
```python
    # CASO 3: Dos HIGH RISK en lados opuestos → IGNORAR
    # opposite_tier viene de ConsensusTracker cuando hay ballenas del lado contrario
    if 'HIGH RISK' in tier_upper and 'HIGH RISK' in opposite_tier.upper():
        result["action"] = "IGNORE"
        result["signal_id"] = "NONE"
        result["confidence"] = "—"
        result["reasoning"].append(
            "Conflicto HIGH RISK en ambos lados — IGNORAR (ver árbol de decisión v3.0)"
        )
        return result
```

**Parte B**: En `_log_ballena()`, obtener el tier del lado contrario del ConsensusTracker
antes de llamar a `classify()`. Añadir estas líneas después de `self.consensus.add(...)`:

```python
        # Obtener tier del lado contrario para detección de conflicto HIGH RISK
        whale_entries_all = self.consensus.get_whale_entries(condition_id)
        opposite_entries = [e for e in whale_entries_all
                           if e['side'] != side and 'HIGH RISK' in e.get('tier', '').upper()]
        opposite_tier_for_conflict = opposite_entries[0]['tier'] if opposite_entries else ""
```

Y pasar `opposite_tier_for_conflict` a `classify()` como parámetro adicional.
Actualizar la firma de `classify()`:

```python
def classify(
    market_title: str,
    tier: str,
    poly_price: float,
    is_nicho: bool = False,
    valor_usd: float = 5000,
    side: str = "BUY",
    display_name: str = "Unknown",
    edge_pct: float = 0.0,
    opposite_tier: str = "",          # ← NUEVO parámetro opcional
) -> dict:
```

Y pasar `opposite_tier` al llamar a `_resolve_conflicts`:
```python
        result = _resolve_conflicts(signals, result, tier_upper, poly_price, opposite_tier)
```

### Qué NO tocar
- Los Casos 1, 2 y 4 de `_resolve_conflicts` no cambian
- `ConsensusTracker.get_whale_entries()` ya existe y funciona
- `classify_consensus()` no cambia
- Los modos CLI (`--demo`, `--csv`, etc.) siguen funcionando porque `opposite_tier` tiene default `""`

---

## FIX 4 — CRÍTICO: S2+ `win_rate_hist` es 85.0, debe ser 78.1

### Problema
En `_log_ballena()`, el merge de S2+ tiene hardcodeado `85.0`:

```python
classification = {
    **classification,
    'signal_id': 'S2+',
    'action': 'FOLLOW',
    'confidence': 'HIGH',
    'win_rate_hist': 85.0,    # ← INCORRECTO
    'reasoning': s2plus_result['reasoning'],
}
```

El valor real del dataset es **78.1%** (7 mercados NBA con 3+ ballenas y precio promedio 0.50–0.60).
85.0% no tiene respaldo estadístico.

### Cambio
Cambiar solo ese valor:
```python
    'win_rate_hist': 78.1,    # ← 7 mercados NBA consensus, Feb 2026
```

### Qué NO tocar
Nada más en ese bloque.

---

## FIX 5 — CRÍTICO: Implementar `TRADER_MIN_TRADES_FOR_SIGNAL`

### Problema
La constante está declarada:
```python
TRADER_MIN_TRADES_FOR_SIGNAL = 15
```
Pero ninguna función la usa. Era la regla clave aprendida del caso Spurs/Pistons:
no desempatar por WR individual de un trader si tiene menos de 15 trades resueltos.

### Localización
En `_analizar_trader_async()`, dentro de la función `_run_analysis()`,
después de `analyzer.calculate_final_score()`.

### Cambio
Añadir estas líneas justo antes de construir el mensaje Telegram del análisis:

```python
                # Verificar umbral mínimo de trades para señal confiable
                total_resolved = d.get('total_trades', 0)
                if total_resolved < TRADER_MIN_TRADES_FOR_SIGNAL:
                    # Añadir aviso al mensaje pero no bloquear el análisis
                    low_trades_warning = (
                        f"\n⚠️ <b>MUESTRA INSUFICIENTE</b>: {total_resolved} trades resueltos "
                        f"(mínimo recomendado: {TRADER_MIN_TRADES_FOR_SIGNAL})\n"
                        f"WR histórico no es señal confiable todavía."
                    )
                else:
                    low_trades_warning = ""
```

Y luego incluir `low_trades_warning` en el mensaje Telegram, después de la línea del Win Rate:

```python
                tg += f"<b>Win Rate:</b> {d.get('win_rate', 0):.1f}%\n"
                tg += low_trades_warning  # ← añadir aquí
                tg += f"<b>Trades:</b> {d.get('total_trades', 0):,}\n"
```

### Qué NO tocar
- No bloquear el análisis cuando N < 15 (solo informar)
- No cambiar la lógica de scoring del `WhaleScorer`
- No cambiar nada en `classify()` por este fix (el desempate por tier ya usa el valor del cache)

---

## FIX 6 — MEDIO: Detección NBA por `'vs'` captura MMA y boxeo

### Problema
En `_detect_category()`, el fallback `' vs'` hace que partidos de MMA, boxeo
o cualquier mercado con "vs" que no tenga keywords deportivos específicos
se clasifique como NBA y dispare S2 erróneamente.

```python
if ' vs' in title_lower or ' vs.' in title_lower:
    return "NBA"   # ← muy agresivo
```

### Localización
Función `_detect_category()`, últimas líneas antes del `return "OTHER"`.

### Cambio
Añadir keywords de deportes de combate antes del fallback `vs`,
y hacer el fallback más conservador:

```python
MMA_KEYWORDS = ['ufc', 'mma', 'boxing', 'bellator', 'one fc', 'fight night',
                'flyweight', 'bantamweight', 'featherweight', 'lightweight',
                'welterweight', 'middleweight', 'heavyweight', 'knockout', 'ko']
```

Añadir esta detección en `_detect_category()` antes del bloque `if ' vs'`:

```python
    if any(kw in title_lower for kw in MMA_KEYWORDS):
        return "MMA"

    # Fallback 'vs' solo si tiene palabras típicas de partidos NBA
    # No usar para cualquier "vs" genérico
    nba_vs_indicators = ['spread:', 'o/u', 'over/under', 'moneyline']
    if (' vs' in title_lower or ' vs.' in title_lower):
        if any(ind in title_lower for ind in nba_vs_indicators):
            return "NBA"
        # Si contiene equipos NBA ya fue capturado arriba
        # Para "X vs Y" sin contexto claro: OTHER, no NBA
        return "OTHER"
```

Y añadir `"MMA"` como categoría que no activa ninguna señal automáticamente
(solo se muestra como categoría informativa).

### Qué NO tocar
- Los keywords de NBA (`NBA_KEYWORDS`) no cambian
- Las señales S1–S5 no cambian
- Solo se afecta el fallback de categorización

---

## FIX 7 — MEDIO: Whitelist A boost aplicado dos veces

### Problema
En `classify()`, el boost de Whitelist A se aplica dos veces:
1. Dentro de la detección de S2 (correcto)
2. En el bloque de "ajustes post-señal" al final de `classify()` (duplicado)

Resultado: el campo `reasoning` muestra la línea del boost duplicada.

### Localización
Al final de `classify()`, después del bloque `if len(signals) == 1:`:

```python
    # Stake multiplier para Whitelist A en S2
    if result["signal_id"] in ("S2", "S1+S2") and display_name in WHITELIST_A:
        if result["confidence"] != "HIGH":
            result["confidence"] = "HIGH"
        result["reasoning"].append(f"Whitelist A boost: {display_name} → stake 1.5x")
```

### Cambio
Eliminar ese bloque completo. Ya está manejado dentro de la detección de S2.

### Qué NO tocar
El boost dentro de la detección de S2 (dentro de `if category == "NBA" and 0.50 <= poly_price <= 0.60:`) se mantiene.

---

## FIX 8 — MEDIO: BLACKLIST/WHITELIST case-sensitive

### Problema
Si el nombre del trader llega como `"sovereign2013"` (minúsculas) o `"Sovereign2013"`,
no matchea `BLACKLIST = ['sovereign2013', ...]` cuando es `"Sovereign2013"`.
En Polymarket los display names pueden tener capitalización variable.

### Localización
En `classify()`, en el bloque de warnings globales:
```python
if display_name in BLACKLIST:
```

Y en la detección de S2 dentro de `classify()`:
```python
if display_name in WHITELIST_A:
```
y
```python
elif display_name in WHITELIST_B:
```

### Cambio
Añadir al inicio de `classify()`, después de `tier_upper = tier.upper()`:

```python
    display_name_lower = display_name.lower()
    whitelist_a_lower = [w.lower() for w in WHITELIST_A]
    whitelist_b_lower = [w.lower() for w in WHITELIST_B]
    blacklist_lower = [b.lower() for b in BLACKLIST]
```

Y reemplazar todas las comparaciones:
```python
if display_name in BLACKLIST:              → if display_name_lower in blacklist_lower:
if display_name in WHITELIST_A:            → if display_name_lower in whitelist_a_lower:
elif display_name in WHITELIST_B:          → elif display_name_lower in whitelist_b_lower:
```

### Qué NO tocar
Las listas `WHITELIST_A`, `WHITELIST_B`, `BLACKLIST` en sí mismas no cambian.
Solo se normaliza la comparación.

---

## FIX 9 — MEDIO: `edge_pct` en `sports_edge_detector` usa convención opuesta al CSV

### Problema
Dos convenciones distintas coexisten en el proyecto:

- **CSV del backtest**: `edge_pct = (poly_price - pinnacle_price) * 100`
  - `edge_pct > 0` = poly más caro = malo (WR 30.6%)

- **`sports_edge_detector.py`**: `edge_pct = (pinnacle_price - poly_price) * 100`
  - `edge_pct > 0` = poly más barato = bueno
  - `edge_pct < 0` = poly más caro = `is_sucker_bet = True`

El Fix 2 elimina el warning incorrecto en `classify()`.
Este fix añade un comentario en `sports_edge_detector.py` para que
la diferencia quede documentada y no genere confusión en el futuro.

### Localización
En `sports_edge_detector.py`, función `check_edge()`, justo donde se calcula `edge_pct`:

```python
edge_pct = (pinnacle_price - poly_price) * 100
result['edge_pct'] = edge_pct
```

### Cambio
Añadir comentario:
```python
        # Convención: edge_pct = (pinnacle - poly) * 100
        # edge_pct > 0 → poly más barato que Pinnacle → edge real para el apostador
        # edge_pct < 0 → poly más caro → is_sucker_bet = True
        # NOTA: el CSV histórico (whale_signals) usa la convención OPUESTA.
        # No confundir al cruzar datos del CSV con valores en tiempo real.
        edge_pct = (pinnacle_price - poly_price) * 100
        result['edge_pct'] = edge_pct
```

### Qué NO tocar
La fórmula en sí no cambia. Solo se documenta.

---

## FIX 10 — LEVE: Indicar visualmente cuando ballena $2K–$3K no tiene señal

### Problema
Ballenas entre $2000 y $3000 pasan el filtro de `_es_ballena()` (umbral en `WHALE_TIERS`)
y disparan `_log_ballena()`, pero `classify()` las descarta con `IGNORE` por capital < $3K.
El usuario ve la alerta de ballena sin entender por qué no hay acción recomendada.

### Localización
En `classify()`, bloque del filtro de capital:

```python
    if valor_usd < 3000:
        result["reasoning"].append(f"Valor ${valor_usd:,.0f} < $3K mínimo. IGNORAR.")
        return result
```

### Cambio
Hacer el mensaje más informativo:

```python
    if valor_usd < 3000:
        result["reasoning"].append(
            f"Capital ${valor_usd:,.0f} < $3K mínimo para señal. "
            f"Ballena registrada pero sin acción recomendada."
        )
        return result
```

Y en `_log_ballena()`, añadir una línea informativa en el output de consola
cuando `classification['action'] == 'IGNORE'` y `valor < 3000`:

```python
        # En el bloque donde se construye `signal_detail`:
        if classification['signal_id'] == 'NONE' and valor < 3000:
            signal_detail = "  [Capital insuficiente para señal — mínimo $3K]\n"
```

### Qué NO tocar
El umbral de $3K no cambia. `WHALE_TIERS` no cambia. Solo se mejora el mensaje.

---

## RESUMEN DE CAMBIOS

| Fix | Archivo | Tipo | Impacto |
|-----|---------|------|---------|
| 1 | `gold_all_claude.py` | Mover bloque async antes de `classify()` y recalcular | S1/S5 ahora se activan correctamente |
| 2 | `gold_all_claude.py` | Eliminar warning de `edge_pct > 0` en `classify()` | Sin falsos positivos de edge |
| 3 | `gold_all_claude.py` | Añadir `opposite_tier` param a `_resolve_conflicts` | Caso 3 ahora funciona |
| 4 | `gold_all_claude.py` | Cambiar `85.0` → `78.1` en S2+ merge | WR correcto |
| 5 | `gold_all_claude.py` | Usar `TRADER_MIN_TRADES_FOR_SIGNAL` en `_analizar_trader_async` | Warning cuando N<15 |
| 6 | `gold_all_claude.py` | Añadir `MMA_KEYWORDS` y mejorar fallback `vs` | MMA no dispara S2 |
| 7 | `gold_all_claude.py` | Eliminar bloque Whitelist A post-señal duplicado | Reasoning sin duplicados |
| 8 | `gold_all_claude.py` | Normalizar case en comparaciones con listas | Traders case-insensitive |
| 9 | `sports_edge_detector.py` | Añadir comentario de convención de signo | Documentación |
| 10 | `gold_all_claude.py` | Mejorar mensaje cuando capital < $3K | UX más claro |

**Archivos que NO se tocan**: `whale_scorer.py`, `polywhale_v5_adjusted.py`,
todos los modos CLI, la interfaz pública de `classify()` (parámetros existentes).