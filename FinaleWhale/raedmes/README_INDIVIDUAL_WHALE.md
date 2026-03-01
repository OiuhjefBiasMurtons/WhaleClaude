# 🐋 Individual Whale Monitor

Monitor de trades en tiempo real para traders específicos de Polymarket.

## Quick Start

```bash
# 1. Configurar Telegram en .env
API_INDIVIDUAL=tu_token_de_bot
CHAT_ID=tu_chat_id

# 2. Ejecutar monitor
python3 individual_whale.py 0x<wallet_address>
```

## Ejemplo de Uso

```bash
# Monitorear a un trader
python3 individual_whale.py 0x2c335066FE58fe9237c3d3Dc7b275C2a034a0563
```

### Output:

```
================================================================================
🐋 MONITOR DE TRADER INDIVIDUAL - POLYMARKET
================================================================================

👤 Usuario: 5kl4f3ju
📍 Wallet: 0x2c335066FE58fe9237c3d3Dc7b275C2a034a0563

📊 ÚLTIMOS 5 TRADES:
--------------------------------------------------------------------------------

1. Will Cade Cunningham win the 2025–2026 NBA MVP?
   Outcome: No
   BUY: 52.11 shares @ $0.9520 (Valor: $49.61)
   Hora: 2026-02-17 16:18:51

2. Solana Up or Down - February 17, 4:15PM-4:30PM ET
   Outcome: Up
   BUY: 25.50 shares @ $0.3600 (Valor: $9.18)
   Hora: 2026-02-17 16:18:51

...

================================================================================
🔍 Iniciando monitoreo activo... (Ctrl+C para detener)
================================================================================

🚨 NUEVO TRADE DETECTADO!
   Mercado: Will FC Barcelona win on 2026-02-17?
   Outcome: Yes
   BUY: 180.00 shares @ $0.6800
   Valor: $122.40
   Hora: 2026-02-17 15:45:10
```

## Características

✅ **Info del trader**: Nombre de usuario + wallet
✅ **Últimos 5 trades**: Mercado, outcome, side, cantidad, precio, valor, hora
✅ **Monitoreo activo**: Verifica nuevos trades cada 10 segundos
✅ **Alertas Telegram**: Notificaciones automáticas de nuevos trades
✅ **Simple y efectivo**: Un comando, un trader

## Encontrar Wallets de Traders

### Desde los logs del detector:
```bash
# Ver wallets de ballenas GOLD/PLATINUM
grep "GOLD\|PLATINUM" whale_detector.log | grep -oP '0x[a-fA-F0-9]{40}' | sort | uniq

# Ejemplos reales:
0x2c335066FE58fe9237c3d3Dc7b275C2a034a0563
0x163EfF4d251dF4BFC95C49f4D90Cd1bF224eDC5B
```

### Desde Polymarket.com:
1. Ve al perfil del trader: `https://polymarket.com/@nombre_trader`
2. Copia el wallet address de la URL

## Configuración

### Archivo .env

```bash
# Token del bot de Telegram (diferente al del detector principal si quieres)
API_INDIVIDUAL=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# ID del chat (mismo que el detector principal)
CHAT_ID=-1001234567890
```

### Intervalo de monitoreo

Edita `individual_whale.py` línea 15:

```python
CHECK_INTERVAL = 10  # segundos (default: 10)
```

## Casos de Uso

1. **Copytrade manual**: Sigue a un trader exitoso
2. **Análisis de estrategia**: Estudia patrones de ballenas
3. **Alertas de oportunidades**: Notificaciones cuando un experto entra a un mercado
4. **Tracking de competencia**: Monitorea a otros traders top

## Ejecutar Múltiples Monitores

```bash
# Terminal 1
python3 individual_whale.py 0x1111...

# Terminal 2
python3 individual_whale.py 0x2222...

# En background
nohup python3 individual_whale.py 0x3333... > trader1.log 2>&1 &
```

## Detener el Monitor

```
Ctrl+C
```

Enviará notificación por Telegram de que se detuvo el monitoreo.

## Ver Documentación Completa

Para más detalles, ejemplos y troubleshooting:

```bash
cat INDIVIDUAL_WHALE_GUIDE.md
```

---

**Created by**: Whale Detection System
**Compatible con**: Polymarket Data API
**Última actualización**: 2026-02-17
