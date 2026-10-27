CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.channel_config (
    cnl_num integer PRIMARY KEY,
    name character varying(255) NOT NULL
);

INSERT INTO mod_arc_postgre_sql.channel_config (cnl_num, name) VALUES
    (101, 'Lab Ambient'),
    (102, 'Med Fridge'),
    (103, 'Med Freezer'),
    (104, 'Dewar 2'),
    (105, 'Temperature_05'),
    (106, 'Temperature_06'),
    (107, 'Temperature_07'),
    (108, 'Temperature_08'),
    (109, 'Temperature_09'),
    (110, 'Temperature_10'),
    (111, 'Med Fridge Alarm'),
    (112, 'Med Freezer Alarm'),
    (113, 'Dewar 1 Alarm'),
    (114, 'Dewar 2 Alarm'),
    (115, 'Med Fridge Warn'),
    (116, 'Med Freezer Warn'),
    (117, 'Dewar 1 Warn'),
    (118, 'Dewar 2 Warn'),
    (119, 'Main Door Contact'),
    (120, 'Cryo Door Contact'),
    (121, 'Main Door Alarm'),
    (122, 'Cryo Door Alarm'),
    (123, 'Incubator 01 Alarm'),
    (124, 'Incubator 02 Alarm'),
    (125, 'Dewar 1'),
    (126, 'MedFridgeAlarm'),
    (127, 'MedFreezerAlarm'),
    (128, 'DewarAlarm'),
    (129, 'DoorAlarm_01'),
    (130, 'DoorAlarm_02')
ON CONFLICT (cnl_num) DO UPDATE SET name = EXCLUDED.name;

CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.alarm_events (
    id SERIAL PRIMARY KEY,
    cnl_num INTEGER NOT NULL,
    equipment_name VARCHAR(64) NOT NULL,
    alarm_type VARCHAR(255) NOT NULL,
    priority INTEGER DEFAULT 2,
    excursion_val DOUBLE PRECISION,
    triggered_at TIMESTAMPTZ NOT NULL,
    pushover_receipt VARCHAR(64),
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(64),
    acknowledged_by_token VARCHAR(64),
    acknowledged_at TIMESTAMPTZ,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    corrective_action_notes TEXT
);

GRANT USAGE ON SCHEMA mod_arc_postgre_sql TO grafana_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mod_arc_postgre_sql TO grafana_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA mod_arc_postgre_sql GRANT SELECT ON TABLES TO grafana_reader;
