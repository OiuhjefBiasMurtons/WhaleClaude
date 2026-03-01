-- ====================================================================
-- ACTUALIZACIÓN DE TABLA: whale_signals
-- Cambiar columna "wallet" por "display_name"
-- ====================================================================

-- Paso 1: Renombrar columna existente
ALTER TABLE whale_signals
RENAME COLUMN wallet TO display_name;

-- Paso 2 (Opcional): Verificar registros existentes
SELECT
    display_name,
    COUNT(*) as trades,
    COUNT(CASE WHEN result = 'WIN' THEN 1 END) as wins,
    COUNT(CASE WHEN result IS NOT NULL THEN 1 END) as resueltos
FROM whale_signals
GROUP BY display_name
ORDER BY trades DESC;

-- Paso 3 (Opcional): Ver últimos 10 registros
SELECT
    detected_at,
    display_name,
    market_title,
    side,
    tier,
    result
FROM whale_signals
ORDER BY detected_at DESC
LIMIT 10;
