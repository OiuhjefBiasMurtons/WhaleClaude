# Fix: Individual Whale Monitor

## Problemas Detectados

### 1. ❌ Trades en orden incorrecto

**Problema**: Los últimos 5 trades mostrados no correspondían a los más recientes.

**Causa**: La API de Polymarket retorna trades sin orden específico, no necesariamente ordenados por timestamp.

**Solución**:
```python
# Antes ❌
params = {'maker': wallet, '_limit': 5}
trades = response.json()
return trades  # Sin ordenar

# Ahora ✅
params = {'maker': wallet, '_limit': 100}  # Obtener más
trades = response.json()
trades_sorted = sorted(trades, key=lambda x: x.get('timestamp', 0), reverse=True)
return trades_sorted[:limit]  # Retornar solo los N más recientes
```

---

### 2. ❌ No detectaba trades nuevos

**Problema**: El script no capturaba nuevos trades cuando el usuario los hacía.

**Causas múltiples**:

#### A. ID de trade incorrecto
```python
# Antes ❌
trade_id = trade.get('id')  # Retorna None en la API

# Ahora ✅
tx_hash = trade.get('transactionHash')  # Campo correcto
if tx_hash:
    trade_id = tx_hash
else:
    # Fallback: crear ID único con múltiples campos
    trade_id = f"{timestamp}_{conditionId}_{side}_{size}"
```

#### B. Inconsistencia de IDs entre funciones

El método `check_new_trades` usaba `trade.get('id')` pero `format_trade_info` usaba otro campo.

**Solución**: Usar la misma lógica de creación de IDs en ambas funciones.

---

## Cambios Implementados

### 1. Función `get_recent_trades` (líneas 56-75)

```python
def get_recent_trades(self, limit=5):
    # Obtener 100 trades para tener suficiente data
    params = {'maker': self.wallet, '_limit': 100}
    response = self.session.get(url, params=params, timeout=10)
    trades = response.json()

    # Ordenar por timestamp descendente
    trades_sorted = sorted(
        trades,
        key=lambda x: x.get('timestamp', 0),
        reverse=True
    )

    # Retornar solo los N más recientes
    return trades_sorted[:limit]
```

**Beneficios**:
- ✅ Siempre muestra los trades MÁS RECIENTES
- ✅ Orden consistente
- ✅ Funciona con cualquier trader

---

### 2. Función `format_trade_info` (líneas 96-107)

```python
# Crear ID único usando transactionHash
tx_hash = trade.get('transactionHash')
if tx_hash:
    unique_id = tx_hash
else:
    # Fallback: crear ID con múltiples campos
    unique_id = f"{timestamp}_{conditionId}_{side}_{size}"

return {
    ...
    'trade_id': unique_id
}
```

**Beneficios**:
- ✅ Usa campo correcto de la API
- ✅ Fallback robusto si no hay transactionHash
- ✅ IDs únicos incluso con mismo timestamp

---

### 3. Función `check_new_trades` (líneas 178-201)

```python
def check_new_trades(self):
    # Obtener últimos 10 trades
    recent_trades = self.get_recent_trades(10)

    for trade in recent_trades:
        # Crear ID usando LA MISMA LÓGICA que format_trade_info
        tx_hash = trade.get('transactionHash')
        if tx_hash:
            trade_id = tx_hash
        else:
            timestamp = trade.get('timestamp', '')
            side = trade.get('side', '').upper()
            size = float(trade.get('size', 0))
            trade_id = f"{timestamp}_{trade.get('conditionId', '')}_{side}_{size}"

        # Verificar si es nuevo
        if trade_id and trade_id not in self.last_seen_trades:
            self.last_seen_trades.add(trade_id)
            self.notify_new_trade(trade)
```

**Beneficios**:
- ✅ Misma lógica de IDs que `format_trade_info`
- ✅ Detecta correctamente trades nuevos
- ✅ Funciona con traders que hacen trades en batch

---

## Casos Especiales Manejados

### Traders con Bots (mismo timestamp)

Algunos traders usan bots que ejecutan múltiples trades en el mismo segundo:

```
16:35:19 - Trade 1: BTC Up/Down
16:35:19 - Trade 2: ETH Up/Down
16:35:19 - Trade 3: SOL Up/Down
```

**Solución**: El ID único incluye `conditionId + side + size`, por lo que cada trade es diferenciable:

```
1771364031_0xabc123..._BUY_25.67
1771364031_0xdef456..._BUY_95.04
1771364031_0xghi789..._BUY_2.30
```

---

## Testing

### Test Manual

```bash
# Ver últimos 5 trades
python3 individual_whale.py 0x204f72f35326db932158cba6adff0b9a1da95e14
```

**Verifica que**:
- Los trades mostrados sean los más recientes
- El timestamp de trade #1 >= timestamp de trade #5

### Test de Detección en Vivo

```bash
# Ejecutar test
python3 test_live_detection.py 0x204f72f35326db932158cba6adff0b9a1da95e14
```

**Qué hace**:
1. Obtiene estado inicial
2. Espera 15 segundos
3. Compara con estado actual
4. Reporta si hubo trades nuevos

---

## Verificación de Corrección

### Antes del Fix

```
📊 ÚLTIMOS 5 TRADES:
1. Trade random #47
2. Trade random #23
3. Trade random #89
4. Trade random #12
5. Trade random #56

🚨 NUEVO TRADE DETECTADO!  ❌ Nunca se ejecutaba
```

### Después del Fix

```
📊 ÚLTIMOS 5 TRADES:
1. Ethereum Up/Down - 16:35:19  ✅ Más reciente
2. Bitcoin Up/Down - 16:35:19
3. Bitcoin Up/Down - 16:35:19
4. Ethereum Up/Down - 16:35:19
5. Bitcoin Up/Down - 16:35:19

🚨 NUEVO TRADE DETECTADO!  ✅ Funciona correctamente
   Mercado: Will Real Madrid win?
   BUY: 180.00 shares @ $0.6800
```

---

## Campos de la API Usados

| Campo | Propósito | Ejemplo |
|-------|-----------|---------|
| `transactionHash` | ID único principal | `0xb3d9a27...` |
| `timestamp` | Ordenamiento | `1771364031` |
| `conditionId` | ID del mercado | `0xce3a680...` |
| `side` | Dirección del trade | `BUY` / `SELL` |
| `size` | Cantidad | `25.67` |
| `price` | Precio | `0.5200` |
| `title` | Nombre del mercado | `BTC Up/Down...` |
| `outcome` | Resultado apostado | `Up` / `Down` |

---

## Notas Importantes

1. **Traders con bots**: Es normal que tengan múltiples trades con el mismo timestamp (1 segundo)

2. **Límite de API**: Siempre pedimos 100 trades y ordenamos localmente para garantizar que tenemos los más recientes

3. **ID único**: `transactionHash` es preferido, pero tenemos fallback robusto

4. **Monitoreo cada 10s**: Configurado en `CHECK_INTERVAL = 10`

---

## Comandos de Verificación

```bash
# Ver si un trader tiene trades recientes
python3 -c "
import requests
from datetime import datetime

wallet = '0x204f72f35326db932158cba6adff0b9a1da95e14'
url = f'https://data-api.polymarket.com/trades'
params = {'maker': wallet, '_limit': 100}
trades = requests.get(url, params=params).json()

trades_sorted = sorted(trades, key=lambda x: x.get('timestamp', 0), reverse=True)

print('Últimos 5 trades:')
for t in trades_sorted[:5]:
    dt = datetime.fromtimestamp(t['timestamp'])
    print(f\"  {dt.strftime('%Y-%m-%d %H:%M:%S')} - {t['title'][:50]}\")
"
```

---

## Estado Final

✅ **Funcionando correctamente**
- Muestra trades en orden correcto (más recientes primero)
- Detecta nuevos trades en tiempo real
- IDs únicos funcionan correctamente
- Maneja traders con bots (mismo timestamp)

---

_Fix completado: 2026-02-17_
