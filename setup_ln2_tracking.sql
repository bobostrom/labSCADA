CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.ln2_tank_logs (
    id SERIAL PRIMARY KEY,
    tank_id VARCHAR(32) NOT NULL DEFAULT 'Cryo Tank 1',
    level_cm NUMERIC(5, 2) NOT NULL,
    was_filled BOOLEAN DEFAULT FALSE,
    frost_condition VARCHAR(32) DEFAULT 'Good',
    initials VARCHAR(16) NOT NULL,
    notes TEXT,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ln2_tank_logs_tank_time 
ON mod_arc_postgre_sql.ln2_tank_logs (tank_id, logged_at DESC);

GRANT SELECT, INSERT, UPDATE ON mod_arc_postgre_sql.ln2_tank_logs TO grafana_reader;
GRANT USAGE, SELECT ON SEQUENCE mod_arc_postgre_sql.ln2_tank_logs_id_seq TO grafana_reader;

-- Seed an initial baseline log for Cryo Tank 1 if table is empty
INSERT INTO mod_arc_postgre_sql.ln2_tank_logs (tank_id, level_cm, was_filled, frost_condition, initials, notes, logged_at)
SELECT 'Cryo Tank 1', 22.0, TRUE, 'Good', 'BO', 'Baseline initial calibration entry', NOW()
WHERE NOT EXISTS (SELECT 1 FROM mod_arc_postgre_sql.ln2_tank_logs);
