#!/bin/bash
# Script de prueba rápida para individual_whale.py

echo "🧪 TEST - Individual Whale Monitor"
echo "=================================="
echo ""

# Verificar que el script existe
if [ ! -f "individual_whale.py" ]; then
    echo "❌ Error: individual_whale.py no encontrado"
    exit 1
fi

# Ejemplo de wallet (puedes cambiarlo por uno real)
# Esta es una wallet de ejemplo, reemplázala con una real del log
WALLET_EJEMPLO="0x1234567890123456789012345678901234567890"

echo "Este script de prueba te mostrará cómo usar el monitor."
echo ""
echo "Para usarlo con una wallet real, ejecuta:"
echo "  python3 individual_whale.py <wallet_address>"
echo ""
echo "Ejemplos de wallets que puedes encontrar en whale_detector.log:"
grep -oP '0x[a-fA-F0-9]{40}' whale_detector.log | sort | uniq | head -5
echo ""
echo "Para monitorear a alguno de estos traders, copia su wallet y ejecuta:"
echo "  python3 individual_whale.py <wallet_copiado>"
echo ""
echo "Presiona Ctrl+C para detener el monitoreo cuando quieras."
