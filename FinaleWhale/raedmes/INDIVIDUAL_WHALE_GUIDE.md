# 🐋 Individual Whale Monitor - Guía de Uso

Script para monitorear trades de un trader específico de Polymarket en tiempo real.

## Características

✅ Muestra información del trader (nombre de usuario, wallet)
✅ Lista los últimos 5 trades del trader
✅ Monitoreo activo en tiempo real (cada 10 segundos)
✅ Alertas por Telegram cuando el trader hace nuevos trades
✅ Información detallada de cada trade (mercado, outcome, side, precio, cantidad, valor)
✅ Simple y fácil de usar

---

## Instalación

### 1. Configurar Telegram (opcional pero recomendado)

Edita tu archivo `.env` y agrega:

```bash
API_INDIVIDUAL=tu_token_de_bot_telegram
CHAT_ID=tu_chat_id
```

**Nota:** Si ya tienes configurado `API_TOKEN` y `CHAT_ID` para el detector principal, puedes usar los mismos valores o crear un bot separado para este script.

### 2. Verificar dependencias

El script usa las mismas dependencias que el detector principal:
- `requests`
- `python-dotenv`

---

## Uso

### Sintaxis básica

```bash
python3 individual_whale.py <wallet_address>
```

### Ejemplo con wallet real

```bash
python3 individual_whale.py 0x1234567890abcdef1234567890abcdef12345678
```

---

## Cómo obtener el wallet address de un trader

### Método 1: Desde el perfil en Polymarket

1. Ve a Polymarket.com
2. Busca al trader que quieres monitorear
3. Entra a su perfil (ej: `https://polymarket.com/@nombre_trader`)
4. En la URL aparecerá algo como `https://polymarket.com/profile/0x1234...`
5. Copia esa dirección (0x...)

### Método 2: Desde un trade específico

1. Ve al historial de trades de un mercado
2. Haz clic en un trade del usuario que quieres monitorear
3. Verás su wallet address en la información del trade

### Método 3: Desde explorer de trades

1. Ve a los logs del detector principal (`whale_detector.log`)
2. Busca trades del usuario que te interesa
3. Copia su `proxyWallet` o wallet address

---

## Qué muestra el script

### 1. Información Inicial

Al ejecutar el script, muestra:

```
================================================================================
🐋 MONITOR DE TRADER INDIVIDUAL - POLYMARKET
================================================================================

👤 Usuario: NombreDelTrader
📍 Wallet: 0x1234567890abcdef...

📊 ÚLTIMOS 5 TRADES:
--------------------------------------------------------------------------------

1. Counter-Strike: FaZe vs Vitality (BO3) - IEM Katowice
   Outcome: FaZe
   BUY: 150.50 shares @ $0.6500 (Valor: $97.83)
   Hora: 2026-02-17 14:30:45

2. Will Real Madrid CF win on 2026-02-17?
   Outcome: Yes
   BUY: 200.00 shares @ $0.7200 (Valor: $144.00)
   Hora: 2026-02-17 13:15:22
...

================================================================================
🔍 Iniciando monitoreo activo... (Ctrl+C para detener)
================================================================================
```

### 2. Monitoreo Activo

El script verifica cada 10 segundos si hay nuevos trades:

```
🚨 NUEVO TRADE DETECTADO!
   Mercado: Will FC Barcelona win on 2026-02-17?
   Outcome: Yes
   BUY: 180.00 shares @ $0.6800
   Valor: $122.40
   Hora: 2026-02-17 15:45:10
```

### 3. Alertas por Telegram

Cuando se detecta un nuevo trade, envía mensaje por Telegram:

```
🚨 NUEVO TRADE - NombreDelTrader

📈 BUY
📊 Mercado: Will FC Barcelona win on 2026-02-17?
🎯 Outcome: Yes
💰 Cantidad: 180.00 shares
💵 Precio: $0.6800
💸 Valor: $122.40
🕐 Hora: 2026-02-17 15:45:10

👤 Trader: NombreDelTrader
📍 0x1234567890...abcdef12
```

---

## Ejemplos de Uso

### Monitorear a un trader específico que te interesa

```bash
# Trader con buen historial que encontraste en el detector principal
python3 individual_whale.py 0xabcdef1234567890abcdef1234567890abcdef12
```

### Monitorear a varios traders simultáneamente

Abre múltiples terminales:

```bash
# Terminal 1
python3 individual_whale.py 0x1111111111111111111111111111111111111111

# Terminal 2
python3 individual_whale.py 0x2222222222222222222222222222222222222222

# Terminal 3
python3 individual_whale.py 0x3333333333333333333333333333333333333333
```

### Ejecutar en background (servidor)

```bash
# Con nohup
nohup python3 individual_whale.py 0x1234... > trader_monitor.log 2>&1 &

# Ver el log
tail -f trader_monitor.log

# Detener el proceso
ps aux | grep individual_whale.py
kill <PID>
```

---

## Configuración Avanzada

### Cambiar intervalo de monitoreo

Edita `individual_whale.py` línea 15:

```python
CHECK_INTERVAL = 5  # Cambiar de 10 a 5 segundos (más rápido)
```

**Recomendaciones:**
- 10 segundos (default): Balance óptimo
- 5 segundos: Para traders muy activos
- 30 segundos: Para ahorrar API calls

### Mostrar más trades iniciales

Edita la línea donde dice `get_recent_trades(5)` y cambia el número:

```python
trades = self.get_recent_trades(10)  # Mostrar últimos 10 trades
```

---

## Troubleshooting

### ❌ Error: No se encontraron trades

**Posibles causas:**
1. Wallet address incorrecto
2. El usuario nunca ha hecho trades
3. El usuario no ha hecho trades recientemente

**Solución:** Verifica que el wallet address sea correcto.

### ⚠️ Sin alertas de Telegram

**Causa:** `API_INDIVIDUAL` o `CHAT_ID` no configurados en `.env`

**Solución:**
```bash
# Agrega al .env
API_INDIVIDUAL=tu_token_de_bot
CHAT_ID=tu_chat_id
```

### 🐌 Script muy lento

**Causa:** API de Polymarket puede ser lenta a veces

**Solución:** Aumentar el `CHECK_INTERVAL` a 15-30 segundos

---

## Casos de Uso Recomendados

### 1. Copytrade Manual
Monitorea a un trader exitoso y copia sus trades manualmente

### 2. Análisis de Estrategia
Estudia los patrones de trading de ballenas específicas

### 3. Alerta de Oportunidades
Recibe notificaciones cuando un trader experto entra en un mercado

### 4. Tracking de Competencia
Si eres trader, monitorea a otros traders top

---

## Comandos Útiles

```bash
# Ver trades en tiempo real
python3 individual_whale.py 0x1234...

# Detener el monitoreo
Ctrl+C

# Ver logs del detector principal para encontrar wallets interesantes
grep "GOLD\|PLATINUM" whale_detector.log | grep "0x" -o | head -10

# Ejecutar múltiples monitores
./run_multiple_monitors.sh  # (crear script personalizado)
```

---

## Comparación con el Detector Principal

| Característica | Detector Principal | Individual Whale |
|---------------|-------------------|------------------|
| Alcance | Todos los mercados | Un trader específico |
| Filtros | Múltiples filtros | Sin filtros |
| Análisis | Scoring completo | Info básica |
| Objetivo | Descubrir ballenas | Seguir trader conocido |
| Frecuencia | Continuo (3s) | Cada 10s |
| Alertas | Solo trades buenos | Todos los trades |

**Cuándo usar cada uno:**
- **Detector principal**: Para descubrir nuevas ballenas y oportunidades
- **Individual whale**: Para seguir de cerca a traders específicos que ya identificaste

---

## Tips y Mejores Prácticas

1. **Combina ambos scripts**: Usa el detector principal para encontrar buenos traders, luego usa este script para seguirlos de cerca

2. **No monitorees demasiados traders**: Máximo 3-5 simultáneos para no saturar

3. **Verifica historial primero**: Antes de monitorear a alguien, revisa sus últimos 5 trades para confirmar que es interesante

4. **Configura Telegram**: Las alertas son clave para no perderte trades importantes

5. **Usa en servidor**: Para monitoreo 24/7, ejecuta en un VPS o servidor

---

## Próximas Mejoras Posibles

- [ ] Agregar filtro por tipo de mercado
- [ ] Mostrar estadísticas del trader (win rate, PnL)
- [ ] Soporte para monitorear múltiples wallets desde un solo script
- [ ] Integración con base de datos para histórico
- [ ] Dashboard web para visualización

---

## Soporte

Si tienes problemas o sugerencias:
1. Revisa los logs del script
2. Verifica tu configuración de `.env`
3. Consulta la documentación del detector principal

---

**¡Feliz trading! 🚀**
