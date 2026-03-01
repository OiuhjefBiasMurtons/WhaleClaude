#!/bin/bash
# Script para configurar cron job de validación automática de ballenas

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_PATH=$(which python3)
VALIDATE_SCRIPT="$SCRIPT_DIR/validate_whale_results.py"

echo "=================================================="
echo "🕐 CONFIGURACIÓN DE CRON JOB"
echo "=================================================="
echo ""
echo "Directorio: $SCRIPT_DIR"
echo "Python:     $PYTHON_PATH"
echo "Script:     $VALIDATE_SCRIPT"
echo ""

# Crear entrada de cron
CRON_ENTRY="0 * * * * cd $SCRIPT_DIR && $PYTHON_PATH $VALIDATE_SCRIPT >> $SCRIPT_DIR/cron_output.log 2>&1"

echo "La siguiente línea se agregará a tu crontab:"
echo ""
echo "$CRON_ENTRY"
echo ""
echo "Esto ejecutará el validador cada hora en punto."
echo ""

read -p "¿Deseas continuar? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]
then
    # Agregar a crontab
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    echo "✅ Cron job configurado correctamente"
    echo ""
    echo "Para verificar:"
    echo "  crontab -l"
    echo ""
    echo "Para ver logs:"
    echo "  tail -f $SCRIPT_DIR/whale_validation.log"
    echo "  tail -f $SCRIPT_DIR/cron_output.log"
else
    echo "❌ Configuración cancelada"
    echo ""
    echo "Para configurar manualmente, ejecuta:"
    echo "  crontab -e"
    echo ""
    echo "Y agrega esta línea:"
    echo "  $CRON_ENTRY"
fi
