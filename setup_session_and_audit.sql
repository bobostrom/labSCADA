-- Setup Session Lifecycle, Door Events, and Cryo Maintenance Holds

CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.cleanroom_door_events (
    id SERIAL PRIMARY KEY,
    door_name VARCHAR(64) NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    lab_mode VARCHAR(32) NOT NULL DEFAULT 'IN_SESSION',
    alarm_tripped BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.lab_operational_mode (
    id SERIAL PRIMARY KEY,
    current_mode VARCHAR(32) NOT NULL DEFAULT 'IN_SESSION',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(64) DEFAULT 'Lab Staff',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.cryo_maintenance_holds (
    id SERIAL PRIMARY KEY,
    equipment_name VARCHAR(64) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    initiated_by VARCHAR(64) DEFAULT 'Lab Staff',
    duration_minutes INTEGER DEFAULT 15,
    cancelled_early BOOLEAN DEFAULT FALSE
);

INSERT INTO mod_arc_postgre_sql.lab_operational_mode (current_mode, updated_by, notes)
SELECT 'IN_SESSION', 'System Init', 'Default operational mode'
WHERE NOT EXISTS (SELECT 1 FROM mod_arc_postgre_sql.lab_operational_mode);

GRANT ALL ON mod_arc_postgre_sql.cleanroom_door_events TO postgres, grafana_reader;
GRANT ALL ON mod_arc_postgre_sql.lab_operational_mode TO postgres, grafana_reader;
GRANT ALL ON mod_arc_postgre_sql.cryo_maintenance_holds TO postgres, grafana_reader;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA mod_arc_postgre_sql TO postgres, grafana_reader;
