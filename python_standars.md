# 🐍 Estándares de Proyectos Python para Claude Code

## 📜 Regla Universal

**EN TODO PROYECTO PYTHON, SIEMPRE:**

1. ✅ Crear entorno virtual en la raíz del proyecto
2. ✅ Activar el entorno virtual ANTES de cualquier instalación
3. ✅ Trabajar exclusivamente DENTRO del entorno virtual
4. ✅ Crear `.gitignore` apropiado
5. ✅ Documentar cómo activar el entorno en README

---

## 🚀 Workflow Estándar

### Paso 1: Inicializar Proyecto

```bash
# 1. Crear directorio del proyecto (si no existe)
mkdir nombre-proyecto
cd nombre-proyecto

# 2. Crear entorno virtual
python -m venv venv

# 3. Activar entorno virtual
# En Linux/Mac:
source venv/bin/activate

# En Windows:
venv\Scripts\activate

# 4. Verificar activación
which python    # Debe mostrar: /ruta/proyecto/venv/bin/python
pip --version   # Debe mostrar: /ruta/proyecto/venv/lib/...
```

### Paso 2: Configurar Dependencias

```bash
# 1. Actualizar pip dentro del venv
pip install --upgrade pip

# 2. Crear requirements.txt
cat > requirements.txt << EOF
# Lista de dependencias aquí
requests>=2.31.0
beautifulsoup4>=4.12.0
# etc...
EOF

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Verificar instalación
pip list
```

### Paso 3: Crear .gitignore

```bash
# Crear .gitignore apropiado
cat > .gitignore << EOF
# Entorno virtual
venv/
env/
ENV/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python

# Archivos de output/logs
*.log
*.csv
*.json
output/
logs/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
EOF
```

### Paso 4: Documentar en README

```markdown
# Nombre del Proyecto

## 🛠️ Setup

### Requisitos
- Python 3.12+

### Instalación

1. Clonar el repositorio (si aplica)
2. Crear y activar entorno virtual:

\`\`\`bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows
\`\`\`

3. Instalar dependencias:

\`\`\`bash
pip install -r requirements.txt
\`\`\`

### Uso

\`\`\`bash
# SIEMPRE activar el venv primero
source venv/bin/activate

# Ejecutar script
python main.py
\`\`\`
```

---

## ✅ Verificaciones Obligatorias

**ANTES de ejecutar cualquier código Python**, verificar:

```bash
# ¿Estoy en el entorno virtual?
which python
# ✅ CORRECTO: /ruta/proyecto/venv/bin/python
# ❌ INCORRECTO: /usr/bin/python o /usr/local/bin/python

# ¿Las dependencias están instaladas en el venv?
pip list
# Debe mostrar las dependencias del proyecto

# ¿El venv está activado en el prompt?
# Tu prompt debe mostrar algo como: (venv) usuario@host:~/proyecto$
```

---

## 🎯 Estructura de Proyecto Python Típica

```
nombre-proyecto/
├── venv/                   # ✅ Entorno virtual (auto-generado)
├── .gitignore             # ✅ Ignorar venv, __pycache__, etc.
├── requirements.txt       # ✅ Dependencias del proyecto
├── README.md              # ✅ Documentación
├── main.py                # Script principal
├── src/                   # Código fuente (opcional)
│   ├── __init__.py
│   └── modulos.py
├── tests/                 # Tests (opcional)
│   └── test_main.py
└── data/                  # Datos (opcional)
    └── sample.csv
```

---

## ⚠️ Errores Comunes a Evitar

### ❌ ERROR 1: Instalar paquetes sin activar venv

```bash
# ❌ MAL - Instala en Python del sistema
pip install requests

# ✅ BIEN - Activa venv primero
source venv/bin/activate
pip install requests
```

### ❌ ERROR 2: Ejecutar scripts sin activar venv

```bash
# ❌ MAL - Usa Python del sistema
python main.py

# ✅ BIEN - Activa venv primero
source venv/bin/activate
python main.py
```

### ❌ ERROR 3: Commitear el venv a git

```bash
# ❌ MAL - venv/ está en el repositorio
git add .
git commit -m "Added project"

# ✅ BIEN - venv/ está en .gitignore
echo "venv/" >> .gitignore
git add .
git commit -m "Added project"
```

### ❌ ERROR 4: No documentar el setup

```markdown
# ❌ MAL README
## Usage
Run `python main.py`

# ✅ BUEN README
## Setup
1. Create virtual environment: `python -m venv venv`
2. Activate: `source venv/bin/activate`
3. Install deps: `pip install -r requirements.txt`
4. Run: `python main.py`
```

---

## 🔄 Comandos Útiles de Mantenimiento

```bash
# Ver paquetes instalados en el venv
pip list

# Actualizar requirements.txt con paquetes actuales
pip freeze > requirements.txt

# Desinstalar un paquete
pip uninstall nombre-paquete

# Actualizar un paquete específico
pip install --upgrade nombre-paquete

# Desactivar el venv (volver al Python del sistema)
deactivate

# Eliminar el venv (para recrearlo)
deactivate
rm -rf venv/
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 🎓 Mejores Prácticas Adicionales

### 1. Versiones específicas en requirements.txt

```txt
# ✅ BIEN - Versiones fijas para reproducibilidad
requests==2.31.0
beautifulsoup4==4.12.3

# ⚠️ ACEPTABLE - Permite actualizaciones menores
requests>=2.31.0,<3.0.0

# ❌ EVITAR - Muy permisivo, puede romper
requests
```

### 2. Separar dependencias de desarrollo

```txt
# requirements.txt - Solo runtime
requests==2.31.0
beautifulsoup4==4.12.3

# requirements-dev.txt - Incluye tools de desarrollo
-r requirements.txt
pytest==7.4.0
black==23.7.0
flake8==6.1.0
```

### 3. Usar Python específico

```bash
# Si tienes múltiples versiones de Python
python3.11 -m venv venv  # Crear con Python 3.11 específico

# Verificar versión en el venv
source venv/bin/activate
python --version
```

---

## 📚 Recursos

- [Python venv docs](https://docs.python.org/3/library/venv.html)
- [pip requirements.txt](https://pip.pypa.io/en/stable/reference/requirements-file-format/)
- [Python .gitignore templates](https://github.com/github/gitignore/blob/main/Python.gitignore)

---

## 🎯 TL;DR - Checklist Rápido

Cada vez que empieces un proyecto Python:

- [ ] `python -m venv venv`
- [ ] `source venv/bin/activate` (o `venv\Scripts\activate` en Windows)
- [ ] Verificar: `which python` → debe estar en venv/
- [ ] Crear `requirements.txt`
- [ ] `pip install -r requirements.txt`
- [ ] Crear `.gitignore` con `venv/`
- [ ] Documentar setup en README
- [ ] **SIEMPRE activar venv antes de trabajar**

---

**Recuerda**: Un entorno virtual limpio = proyecto reproducible = menos dolores de cabeza 🎉