# Fix: Parámetro Incorrecto en API de Trades

## Problema

El script `individual_whale.py` mostraba trades incorrectos para todos los usuarios:
- **Esperado**: Trades específicos del usuario (ej. Prexpect → Elon Musk tweets)
- **Obtenido**: Trades genéricos de Bitcoin Up/Down para todos los usuarios

## Causa Raíz

**Parámetro incorrecto en la API**: Se usaba `maker` en lugar de `user`.

```python
# Antes ❌
params = {'maker': self.wallet, '_limit': 100}
```

El parámetro `maker` **NO filtra** por wallet del usuario en la API pública de Polymarket. Retorna trades generales sin filtro.

## Solución

Cambiar a parámetro **`user`**:

```python
# Ahora ✅
params = {'user': self.wallet, '_limit': 100}
```

## Cambios Implementados

### 1. Función `get_recent_trades` (línea 75-82)

```python
def get_recent_trades(self, limit=5):
    try:
        url = f"{DATA_API}/trades"
        params = {
            'user': self.wallet,  # ✅ Parámetro correcto (no 'maker')
            '_limit': 100
        }
        # ...
```

### 2. Función `get_user_info` - Fallback (línea 57-59)

```python
# Fallback: usar nombre de los trades
trades_url = f"{DATA_API}/trades"
params = {'user': self.wallet, '_limit': 1}  # ✅ Parámetro correcto
trades_response = self.session.get(trades_url, params=params, timeout=10)
```

## Verificación

### Test con usuario Prexpect

**Wallet**: `0xa59c570a9eca148da55f6e1f47a538c0c600bb62`
**Especialidad**: Mercados de tweets de Elon Musk

#### Antes ❌
```
1. Bitcoin Up or Down - February 17, 7:25PM-7:30PM ET
2. Bitcoin Up or Down - February 17, 7:25PM-7:30PM ET
3. Bitcoin Up or Down - February 17, 7:25PM-7:30PM ET
```

#### Después ✅
```
1. Will Elon Musk post 240-259 tweets from February 10 to February 16?
   BUY @ 0.999
2. Will Elon Musk post 260-279 tweets from February 10 to February 16?
   SELL @ 0.001
3. Will Elon Musk post 240-259 tweets from February 10 to February 16?
   BUY @ 0.999
```

### Test con usuario ShouShouKKos

**Wallet**: `0xc2fb2890612ac30ee3547b28020bcc0ce3c6b9f0`

#### Resultado ✅
```
Username: ShouShouKKos
Trades encontrados: 5
1. Ethereum Up or Down - February 17, 4:35PM-4:40PM ET
2. Bitcoin Up or Down - February 17, 4:35PM-4:40PM ET
3. Bitcoin Up or Down - February 17, 4:35PM-4:40PM ET
```

## API de Polymarket - Parámetros Correctos

| Endpoint | Parámetro | Descripción |
|----------|-----------|-------------|
| `/trades` | `user` | Filtra por wallet del usuario ✅ |
| `/trades` | `maker` | ❌ NO funciona en API pública |
| `/trades` | `_limit` | Límite de resultados |
| `/trades` | `_offset` | Paginación |

## Impacto del Fix

**Antes**:
- ❌ Todos los usuarios mostraban trades genéricos (BTC Up/Down)
- ❌ Imposible seguir traders específicos
- ❌ Alertas no útiles

**Ahora**:
- ✅ Cada usuario muestra sus trades reales
- ✅ Seguimiento correcto de estrategias individuales
- ✅ Alertas relevantes por tipo de mercado

## Otros Usuarios Verificados

| Usuario | Wallet | Mercados | Status |
|---------|--------|----------|--------|
| Prexpect | `0xa59c...` | Elon Musk tweets | ✅ |
| ShouShouKKos | `0xc2fb...` | Crypto Up/Down | ✅ |
| 5kl4f3ju | `0x2c33...` | NBA MVP, Crypto | ✅ |

## Comandos de Prueba

```bash
# Test manual del fix
python3 -c "
import requests
wallet = '0xa59c570a9eca148da55f6e1f47a538c0c600bb62'

# Método INCORRECTO (maker)
url = 'https://data-api.polymarket.com/trades'
resp_wrong = requests.get(url, params={'maker': wallet, '_limit': 3}).json()
print('Con maker:', [t['title'][:30] for t in resp_wrong[:2]])

# Método CORRECTO (user)
resp_correct = requests.get(url, params={'user': wallet, '_limit': 3}).json()
print('Con user:', [t['title'][:30] for t in resp_correct[:2]])
"

# Output esperado:
# Con maker: ['Bitcoin Up or Down...', 'Bitcoin Up or Down...']
# Con user: ['Will Elon Musk post 240-259...', 'Will Elon Musk post 260-279...']
```

## Estado Final

✅ **Fix completado y verificado**
- Parámetro API corregido: `maker` → `user`
- Todos los usuarios muestran sus trades correctos
- Script `individual_whale.py` funcionando como esperado

---

**Fix completado**: 2026-02-17
**Archivos modificados**: `individual_whale.py` (líneas 59, 79)
