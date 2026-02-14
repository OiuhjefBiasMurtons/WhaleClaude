# 🐋 Polymarket Analyzer V3.0 - Upgrade Blueprint

## 📋 Overview
**MEJORA INCREMENTAL de `claude_individual.py`**

El script actual (`claude_individual.py` V2.2) funciona bien para análisis comportamental, pero tiene problemas calculando métricas financieras (PnL, ROI, Win Rate, valores de apuestas, etc) desde la API de Polymarket.

**Solución**: Agregar scraping de `polymarketanalytics.com` para obtener métricas financieras **verificadas y precisas**.

## 🎯 Objetivo

**Mantener toda la lógica existente** de `claude_individual.py` pero:

❌ **ELIMINAR**: `calculate_market_pnl()` - Cálculo manual problemático  
✅ **AGREGAR**: `scrape_financial_metrics()` - Scraping de polymarketanalytics.com  
✅ **CONSERVAR**: Todo el análisis comportamental (experiencia, disciplina, especialización)  
✅ **MEJORAR**: Scoring de performance usando datos scraped

## 🔧 Configuración Inicial del Entorno

**ANTES DE CUALQUIER CÓDIGO**, configurar entorno virtual:

```bash
# 1. Crear entorno virtual en la raíz del proyecto
python -m venv venv

# 2. Activar entorno virtual
# En Linux/Mac:
source venv/bin/activate

# En Windows:
venv\Scripts\activate

# 3. Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

# 4. Verificar instalación
python --version
pip list
```

**IMPORTANTE**: 
- ✅ TODO el trabajo debe realizarse DENTRO del entorno virtual
- ✅ Claude Code debe activar el venv antes de ejecutar cualquier script
- ✅ El venv debe estar en `.gitignore` si usas git

## 📁 Project Structure

```
polymarket-analyzer/
├── venv/                         # ✅ Entorno virtual (auto-generado)
├── claude_individual.py          # ✅ Script original (backup)
├── polywhale_v3.py               # ✅ Nueva versión mejorada
├── requirements.txt              # ✅ Dependencias
├── .gitignore                    # ✅ Ignorar venv/
└── README.md                     # Documentación de cambios
```

**No necesitas carpetas complejas** - Solo mejorar el script existente.

## 🔧 Dependencies to Add

**Crear/Actualizar `requirements.txt`**:

```txt
# Dependencias existentes (ya usadas en claude_individual.py)
requests>=2.31.0
urllib3>=2.0.0

# Nuevas dependencias para scraping
beautifulsoup4>=4.12.0
lxml>=4.9.0
tenacity>=8.2.0
```

**Instalación**:
```bash
# Dentro del entorno virtual
pip install -r requirements.txt
```

## 📊 Changes to Data Sources

### ✅ CONSERVAR (Ya funciona bien en claude_individual.py)
```python
# Polymarket API - SEGUIR USANDO IGUAL
GET /positions?user={wallet}      # Posiciones actuales
GET /activity?user={wallet}       # Historial de trades
```

**Estos datos son correctos para**:
- Trading behavior (frecuencia, patrones)
- Market preferences (sectores, especialización)
- Position sizing y concentración
- Detección de bots

### ✅ NUEVO: Scraping de polymarketanalytics.com

**URL**: `https://polymarketanalytics.com/traders/{wallet_address}`

**Reemplazar estos cálculos problemáticos**:
- ❌ `calculate_market_pnl()` → ✅ `scrape_financial_metrics()`

**Extraer del HTML**:
```python
{
    'total_pnl': float,        # Total Profit/Loss (verificado)
    'volume': float,           # Volume Traded (real)
    'win_rate': float,         # Win Rate % (preciso)
    'markets_won': int,        # Markets ganados
    'markets_lost': int,       # Markets perdidos
    'markets_traded': int,     # Total markets
    'roi': float               # ROI % (si disponible)
}
```

**Beneficios**:
- ✅ PnL correcto (incluye liquidaciones, fees, todo)
- ✅ Win Rate verificado
- ✅ Volumen real (no hay que sumar BUY+SELL manualmente)
- ✅ Datos consistentes con lo que ve el usuario en Polymarket

## 🔨 Specific Code Changes

### 1. Agregar Método de Scraping

**NUEVO MÉTODO** en la clase `TraderAnalyzer`:

```python
def scrape_financial_metrics(self):
    """
    ✅ NUEVO: Obtiene métricas financieras de polymarketanalytics.com
    Reemplaza el problemático calculate_market_pnl()
    """
    from bs4 import BeautifulSoup
    import time
    
    url = f"https://polymarketanalytics.com/traders/{self.wallet}"
    
    print("🔹 Obteniendo métricas verificadas de polymarketanalytics.com...")
    
    try:
        # Delay para respetar rate limits
        time.sleep(2)
        
        response = session.get(url, timeout=15)
        
        # Trader no encontrado
        if response.status_code == 404:
            print("   ⚠️  Trader no encontrado en polymarketanalytics.com")
            return None
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        
        # ✅ PARSEAR HTML - Estructura a determinar inspeccionando la página
        # Buscar elementos con clases/IDs comunes para métricas
        
        metrics = {
            'total_pnl': self._extract_pnl(soup),
            'volume': self._extract_volume(soup),
            'win_rate': self._extract_win_rate(soup),
            'markets_traded': self._extract_markets_count(soup),
            'markets_won': self._extract_markets_won(soup),
            'markets_lost': self._extract_markets_lost(soup),
            'roi': None  # Calcular como (pnl/volume)*100 si no está disponible
        }
        
        # Calcular ROI si no viene en la página
        if metrics['volume'] and metrics['volume'] > 0 and metrics['total_pnl'] is not None:
            metrics['roi'] = (metrics['total_pnl'] / metrics['volume']) * 100
        
        print(f"   ✅ Métricas obtenidas: PnL=${metrics['total_pnl']:,.2f}, Vol=${metrics['volume']:,.2f}")
        
        return metrics
        
    except Exception as e:
        print(f"   ⚠️  Error scraping analytics: {e}")
        return None

def _extract_pnl(self, soup):
    """Extrae Total PnL del HTML"""
    # IMPLEMENTAR: Buscar elemento con texto "Total PnL" o similar
    # Ejemplo: soup.find('span', text=re.compile('Total PnL')).find_next('span').text
    try:
        # Placeholder - ajustar según estructura real
        pnl_element = soup.find(text=re.compile(r'Total PnL|Net Profit'))
        if pnl_element:
            value_text = pnl_element.find_next('span').text
            return self._parse_currency(value_text)
    except:
        pass
    return None

def _extract_volume(self, soup):
    """Extrae Total Volume del HTML"""
    try:
        vol_element = soup.find(text=re.compile(r'Volume|Total Volume'))
        if vol_element:
            value_text = vol_element.find_next('span').text
            return self._parse_currency(value_text)
    except:
        pass
    return None

def _extract_win_rate(self, soup):
    """Extrae Win Rate del HTML"""
    try:
        wr_element = soup.find(text=re.compile(r'Win Rate'))
        if wr_element:
            value_text = wr_element.find_next('span').text
            # Convertir "64.5%" → 64.5
            return float(value_text.replace('%', '').strip())
    except:
        pass
    return None

def _extract_markets_count(self, soup):
    """Extrae número total de mercados"""
    try:
        markets_element = soup.find(text=re.compile(r'Markets Traded|Markets'))
        if markets_element:
            value_text = markets_element.find_next('span').text
            return int(value_text.replace(',', '').strip())
    except:
        pass
    return None

def _extract_markets_won(self, soup):
    """Extrae markets ganados"""
    # Similar pattern
    return None

def _extract_markets_lost(self, soup):
    """Extrae markets perdidos"""
    # Similar pattern
    return None

def _parse_currency(self, text):
    """
    Convierte "$1,234.56" o "-$1,234.56" → 1234.56 o -1234.56
    """
    try:
        cleaned = text.replace('$', '').replace(',', '').strip()
        return float(cleaned)
    except:
        return None
```

### 2. Modificar `calculate_current_performance_score()`

**REEMPLAZAR** la función existente para usar datos scraped:

```python
def calculate_current_performance_score(self):
    """RENDIMIENTO (40 puntos) - USANDO DATOS SCRAPED"""
    score = 0
    
    # ✅ PRIMERO: Intentar obtener métricas de polymarketanalytics.com
    scraped = self.scrape_financial_metrics()
    
    if scraped and scraped['total_pnl'] is not None:
        # ✅ USAR DATOS SCRAPED (más confiables)
        self.net_total = scraped['total_pnl']
        self.total_volume = scraped['volume'] if scraped['volume'] else self.total_volume
        self.overall_win_rate = scraped['win_rate'] / 100 if scraped['win_rate'] else None
        
        print(f"   ✅ Usando métricas de polymarketanalytics.com")
    else:
        # ⚠️ FALLBACK: Calcular manualmente (menos preciso)
        print(f"   ⚠️  Usando cálculo manual (puede ser impreciso)")
        self.calculate_market_pnl()  # Método original
        
        if self.market_pnl:
            self.total_gain = sum(pnl for pnl in self.market_pnl.values() if pnl > 0)
            self.total_loss = sum(pnl for pnl in self.market_pnl.values() if pnl < 0)
            self.net_total = self.total_gain + self.total_loss
    
    # ✅ SCORING CON ROI (igual que antes)
    if hasattr(self, 'net_total') and hasattr(self, 'total_volume') and self.total_volume > 0:
        roi_pct = (self.net_total / self.total_volume * 100)
        
        if roi_pct > 20: 
            score += 20
            self.strengths.append(f"✓ ROI excepcional ({roi_pct:.1f}%)")
        elif roi_pct > 12: score += 19
        elif roi_pct > 8: 
            score += 18
            self.strengths.append(f"✓ ROI sólido ({roi_pct:.1f}%)")
        elif roi_pct > 5: score += 15
        elif roi_pct > 3: score += 12
        elif roi_pct > 1: score += 9
        elif roi_pct > 0: score += 6
        elif roi_pct > -5: score += 3
        elif roi_pct <= -10:
            self.red_flags.append(f"⚠️ ROI negativo ({roi_pct:.1f}%)")
        
        self.roi = roi_pct
    
    # ✅ SCORING CON WIN RATE
    if self.overall_win_rate is not None:
        if self.overall_win_rate > 0.75: 
            score += 15
            self.strengths.append(f"✓ Win rate excepcional ({self.overall_win_rate*100:.0f}%)")
        elif self.overall_win_rate > 0.65: 
            score += 14
            if "Win rate" not in str(self.strengths):
                self.strengths.append(f"✓ Win rate excelente ({self.overall_win_rate*100:.0f}%)")
        elif self.overall_win_rate > 0.55: score += 12
        elif self.overall_win_rate > 0.50: score += 10
        elif self.overall_win_rate > 0.45: score += 8
        elif self.overall_win_rate > 0.40: score += 6
        elif self.overall_win_rate > 0.30: score += 4
        elif self.overall_win_rate > 0.20: score += 2
    
    # ✅ RESTO IGUAL (actividad reciente)
    now = time.time()
    recent_activity = [a for a in self.activity if now - a.get('timestamp', 0) < 30*86400]
    
    if len(recent_activity) > 20: score += 5
    elif len(recent_activity) > 10: score += 4
    elif len(recent_activity) > 5: score += 3
    elif len(recent_activity) > 0: score += 2
    else:
        self.red_flags.append("⚠️ Sin actividad en último mes")
    
    self.recent_trades = len(recent_activity)
    
    self.metrics['current_performance_score'] = score
    return score
```

### 3. Actualizar Imports

**AL INICIO DEL ARCHIVO** agregar:

```python
from bs4 import BeautifulSoup
import re  # Ya existe pero asegurar que esté
```

### 4. Modificar `generate_report()`

**AGREGAR DISCLAIMER** en la sección de Performance:

```python
# Dentro de generate_report(), en la sección "💰 PERFORMANCE HISTÓRICO"

if hasattr(self, 'net_total'):
    self.report(f"\n💰 PERFORMANCE HISTÓRICO")
    
    # ✅ AGREGAR: Indicar fuente de datos
    data_source = "polymarketanalytics.com" if hasattr(self, 'scraped_metrics_used') else "API calculation"
    self.report(f"   • Fuente de datos:    {data_source}")
    
    self.report(f"   • Volume Traded:      ${self.total_volume:,.2f}")
    # ... resto igual
```

## 🚨 Critical Implementation Rules

### Rule 1: Scraping primero, cálculo manual como fallback

```python
# ✅ CORRECTO
scraped = self.scrape_financial_metrics()
if scraped:
    self.net_total = scraped['total_pnl']  # Datos verificados
else:
    self.calculate_market_pnl()  # Fallback al método original
```

### Rule 2: Inspeccionar HTML antes de implementar

**ANTES de escribir los métodos `_extract_*`**:

1. Abre en navegador: `https://polymarketanalytics.com/traders/0x166ad16e04d1a969cc9b98b8c40250579f75e675`
2. Click derecho → "Inspect Element"
3. Busca los elementos que contienen PnL, Volume, Win Rate
4. Anota las clases CSS o estructura HTML
5. Implementa los parsers basándote en la estructura real

**Ejemplo de estructura típica**:
```html
<div class="stat-card">
  <div class="stat-label">Total PnL</div>
  <div class="stat-value">$45,234.56</div>
</div>
```

### Rule 3: Manejo robusto de errores

```python
try:
    metrics = self.scrape_financial_metrics()
    if metrics:
        # Usar datos scraped
    else:
        # Fallback a cálculo manual
except Exception as e:
    print(f"⚠️ Error scraping: {e}")
    # Continuar con método original
```

### Rule 4: Respetar rate limits

```python
import time
time.sleep(2)  # Esperar 2 segundos antes de scraping
```

## 🎯 Testing Strategy

### Test con wallet conocida

```bash
# Wallet de ejemplo con datos buenos
python polywhale_v3.py 0x166ad16e04d1a969cc9b98b8c40250579f75e675

# Verificar que:
# 1. Los datos scraped coincidan con lo visible en polymarketanalytics.com
# 2. El PnL sea coherente
# 3. El Win Rate tenga sentido
# 4. El script no crashee si el scraping falla
```

### Test de fallback

```bash
# Wallet que NO existe en polymarketanalytics
python polywhale_v3.py 0xINVALIDWALLET

# Debe usar el cálculo manual sin crashear
```

## 📝 Output Format

**EL MISMO QUE `claude_individual.py`** pero con datos más precisos:

```
═══════════════════════════════════════════════════════════
🦈 POLYMARKET TRADER ANALYSIS V3.0
═══════════════════════════════════════════════════════════

💰 PERFORMANCE HISTÓRICO
   • Fuente de datos:    polymarketanalytics.com ← NUEVO
   • Volume Traded:      $825,120.00
   • Net Total:          🟢 $45,234.56
   • ROI:                🟢 27.31%
   • Win Rate:           64.5%
   • Markets Traded:     156

📊 TRADER SCORE: 92/100 (💎 DIAMOND)
   • Rendimiento:        38.0/40  ← Basado en datos scraped
   • Especialización:    22.0/25
   • Disciplina:         18.0/20
   • Experiencia:        14.0/15
```

**Diferencias con V2.2**:
- ✅ PnL correcto (scraped vs calculado)
- ✅ Win Rate preciso
- ✅ Volumen verificado
- ✅ Indicador de fuente de datos

## 🚀 Step-by-Step Implementation

### Paso 0: Configurar Entorno Virtual (PRIMERO)

```bash
# CRÍTICO: Hacer esto ANTES de cualquier cosa

# 1. Crear entorno virtual
python -m venv venv

# 2. Activar entorno virtual
source venv/bin/activate  # Linux/Mac
# O en Windows: venv\Scripts\activate

# 3. Verificar que estás en el venv
which python  # Debe mostrar ruta dentro de venv/
pip --version  # Debe mostrar ruta dentro de venv/

# 4. Crear .gitignore
echo "venv/" > .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "TraderAnalysis/" >> .gitignore
```

### Paso 1: Inspeccionar HTML de polymarketanalytics.com

**DENTRO del entorno virtual activado**:

```bash
# Abre en navegador
https://polymarketanalytics.com/traders/0x166ad16e04d1a969cc9b98b8c40250579f75e675

# Inspecciona elementos (F12 o click derecho → Inspect)

# Busca los elementos que contienen:
#    - Total PnL
#    - Volume Traded
#    - Win Rate
#    - Markets Traded
#    - Markets Won/Lost

# Anota las clases CSS, IDs o estructura HTML

# SOLO ENTONCES implementa los parsers
```

### Paso 2: Crear requirements.txt

```bash
# Dentro del venv activado
cat > requirements.txt << EOF
requests>=2.31.0
urllib3>=2.0.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
tenacity>=8.2.0
EOF
```

### Paso 3: Instalar dependencias

```bash
# Asegúrate de estar en el venv
pip install --upgrade pip
pip install -r requirements.txt

# Verificar instalación
pip list | grep -E "(beautifulsoup|lxml|tenacity)"
```

### Paso 4: Crear `polywhale_v3.py`

```bash
# Copiar el script original
cp claude_individual.py polywhale_v3.py

# Modificar polywhale_v3.py según los cambios especificados
```

### Paso 5: Implementar el scraper

**En `polywhale_v3.py`**, agregar:

1. ✅ Imports nuevos (BeautifulSoup)
2. ✅ Método `scrape_financial_metrics()`
3. ✅ Métodos helper `_extract_*()` y `_parse_currency()`
4. ✅ Modificar `calculate_current_performance_score()` para usar scraping

### Paso 6: Probar (DENTRO del venv)

```bash
# Verificar que el venv está activo
which python  # Debe estar en venv/

# Test básico
python polywhale_v3.py 0x166ad16e04d1a969cc9b98b8c40250579f75e675

# Verificar:
# 1. ¿Los datos scraped aparecen?
# 2. ¿Coinciden con lo que se ve en polymarketanalytics.com?
# 3. ¿El script funciona si el scraping falla?
```

### Paso 7: Comparar resultados

```bash
# Ejecutar ambas versiones con la misma wallet (dentro del venv)
python claude_individual.py 0xWALLET > v2_output.txt
python polywhale_v3.py 0xWALLET > v3_output.txt

# Comparar PnL y ROI
diff v2_output.txt v3_output.txt
```

## 📋 Checklist de Completitud

- [ ] **Entorno virtual creado** (`python -m venv venv`)
- [ ] **Entorno virtual activado** (verificar con `which python`)
- [ ] **requirements.txt creado** con todas las dependencias
- [ ] **Dependencias instaladas** (`pip install -r requirements.txt`)
- [ ] **.gitignore creado** (incluye `venv/`, `__pycache__/`, etc.)
- [ ] BeautifulSoup funcionando en el venv
- [ ] HTML de polymarketanalytics.com inspeccionado
- [ ] Método `scrape_financial_metrics()` implementado
- [ ] Parsers `_extract_*()` funcionando
- [ ] Fallback a cálculo manual si scraping falla
- [ ] Rate limiting implementado (sleep 2s)
- [ ] Probado con wallet real (DENTRO del venv)
- [ ] Datos scraped coinciden con la web
- [ ] Script funciona sin crashear si scraping falla
- [ ] README actualizado con cambios

## ⚠️ Recordatorios Importantes

**SIEMPRE trabajar dentro del entorno virtual**:
```bash
# Antes de ejecutar cualquier comando Python
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows

# Verificar que estás en el venv
which python  # Debe mostrar ruta en venv/bin/python
```

**Si cierras la terminal y vuelves**:
```bash
cd polymarket-analyzer
source venv/bin/activate  # Reactivar venv
python polywhale_v3.py 0xWALLET  # Ahora sí ejecutar
```