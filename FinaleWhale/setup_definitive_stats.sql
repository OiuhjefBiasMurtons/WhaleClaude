-- ============================================================
-- setup_definitive_stats.sql
-- Crear tablas signal_stats y trader_stats para la DB Whales
-- (usada por definitive_all_claude.py)
--
-- Ejecutar en el SQL Editor de Supabase (proyecto enacybjlovvzvyoleeic)
-- ============================================================

-- ------------------------------------------------------------
-- TABLA: trader_stats
-- Agrega resultados por trader (display_name)
-- is_auto_whitelisted = true si WR >= 60% con N >= 15 trades
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trader_stats (
    id              bigserial PRIMARY KEY,
    display_name    text UNIQUE NOT NULL,
    n_total         int     DEFAULT 0,
    n_wins          int     DEFAULT 0,
    win_rate        float   DEFAULT 0.0,
    pnl_total       float   DEFAULT 0.0,
    is_auto_whitelisted boolean DEFAULT false,
    last_updated    timestamptz DEFAULT now()
);

-- ------------------------------------------------------------
-- TABLA: signal_stats
-- Agrega resultados por tier + rango de valor_usd
-- (Definitive no tiene signal_id S1-S8, así que el eje de
--  análisis es tier x tamaño de trade)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signal_stats (
    id          bigserial PRIMARY KEY,
    tier        text,
    valor_range text,
    n_total     int   DEFAULT 0,
    n_wins      int   DEFAULT 0,
    win_rate    float DEFAULT 0.0,
    pnl_total   float DEFAULT 0.0,
    last_updated timestamptz DEFAULT now()
);

-- Índice único para evitar duplicados al refrescar
CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_stats_tier_range
    ON signal_stats (tier, valor_range);

-- ------------------------------------------------------------
-- FUNCIÓN: refresh_trader_stats()
-- Borra y recalcula trader_stats desde whale_signals resueltos
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION refresh_trader_stats()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    TRUNCATE trader_stats;

    INSERT INTO trader_stats (
        display_name, n_total, n_wins, win_rate, pnl_total,
        is_auto_whitelisted, last_updated
    )
    SELECT
        display_name,
        COUNT(*)                                              AS n_total,
        COUNT(*) FILTER (WHERE result = 'WIN')               AS n_wins,
        ROUND(
            (100.0 * COUNT(*) FILTER (WHERE result = 'WIN')
             / NULLIF(COUNT(*), 0))::numeric, 2
        )                                                     AS win_rate,
        ROUND(COALESCE(SUM(pnl_teorico), 0)::numeric, 2)     AS pnl_total,
        CASE
            WHEN COUNT(*) >= 15
             AND 100.0 * COUNT(*) FILTER (WHERE result = 'WIN')
                 / NULLIF(COUNT(*), 0) >= 60.0
            THEN true
            ELSE false
        END                                                   AS is_auto_whitelisted,
        NOW()
    FROM whale_signals
    WHERE result IS NOT NULL
      AND display_name IS NOT NULL
      AND display_name != ''
    GROUP BY display_name;
END;
$$;

-- ------------------------------------------------------------
-- FUNCIÓN: refresh_signal_stats()
-- Borra y recalcula signal_stats agrupado por tier + valor_range
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION refresh_signal_stats()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    TRUNCATE signal_stats;

    INSERT INTO signal_stats (
        tier, valor_range, n_total, n_wins, win_rate, pnl_total, last_updated
    )
    SELECT
        COALESCE(NULLIF(tier, ''), 'sin_tier') AS tier,
        CASE
            WHEN valor_usd >= 20000 THEN '$20K+'
            WHEN valor_usd >= 5000  THEN '$5K-$20K'
            WHEN valor_usd >= 1000  THEN '$1K-$5K'
            ELSE                         '$500-$1K'
        END                                                   AS valor_range,
        COUNT(*)                                              AS n_total,
        COUNT(*) FILTER (WHERE result = 'WIN')               AS n_wins,
        ROUND(
            (100.0 * COUNT(*) FILTER (WHERE result = 'WIN')
             / NULLIF(COUNT(*), 0))::numeric, 2
        )                                                     AS win_rate,
        ROUND(COALESCE(SUM(pnl_teorico), 0)::numeric, 2)     AS pnl_total,
        NOW()
    FROM whale_signals
    WHERE result IS NOT NULL
    GROUP BY
        COALESCE(NULLIF(tier, ''), 'sin_tier'),
        CASE
            WHEN valor_usd >= 20000 THEN '$20K+'
            WHEN valor_usd >= 5000  THEN '$5K-$20K'
            WHEN valor_usd >= 1000  THEN '$1K-$5K'
            ELSE                         '$500-$1K'
        END;
END;
$$;

-- ------------------------------------------------------------
-- GRANT para que el rol anon/authenticated pueda llamar las RPCs
-- (ajustar según los roles que uses en Supabase)
-- ------------------------------------------------------------
GRANT EXECUTE ON FUNCTION refresh_trader_stats() TO service_role;
GRANT EXECUTE ON FUNCTION refresh_signal_stats() TO service_role;
GRANT SELECT ON trader_stats TO anon, authenticated;
GRANT SELECT ON signal_stats TO anon, authenticated;
