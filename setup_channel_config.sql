CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.channel_config (
    cnl_num integer PRIMARY KEY,
    name character varying(255) NOT NULL
);

INSERT INTO mod_arc_postgre_sql.channel_config (cnl_num, name) VALUES
    (101, 'Lab Ambient'),
    (102, 'Med Fridge'),
    (103, 'Med Freezer'),
    (104, 'Temperature_04'),
    (105, 'Temperature_05'),
    (106, 'Temperature_06'),
    (107, 'Temperature_07'),
    (108, 'Temperature_08'),
    (109, 'Temperature_09'),
    (110, 'Temperature_10'),
    (111, 'SensorStatus_01'),
    (112, 'SensorStatus_02'),
    (113, 'SensorStatus_03'),
    (114, 'SensorStatus_04'),
    (115, 'SensorStatus_05'),
    (116, 'SensorStatus_06'),
    (117, 'SensorStatus_07'),
    (118, 'SensorStatus_08'),
    (119, 'SensorStatus_09'),
    (120, 'SensorStatus_10'),
    (121, 'DoorOpen_01'),
    (122, 'DoorOpen_02'),
    (123, 'IncubatorAlarm_01'),
    (124, 'IncubatorAlarm_02'),
    (125, 'Cryo Tank 1'),
    (126, 'MedFridgeAlarm'),
    (127, 'MedFreezerAlarm'),
    (128, 'CryoTankAlarm'),
    (129, 'DoorAlarm_01'),
    (130, 'DoorAlarm_02')
ON CONFLICT (cnl_num) DO UPDATE SET name = EXCLUDED.name;

CREATE TABLE IF NOT EXISTS mod_arc_postgre_sql.alarm_events (
    id SERIAL PRIMARY KEY,
    cnl_num INTEGER NOT NULL,
    equipment_name VARCHAR(64) NOT NULL,
    alarm_type VARCHAR(64) NOT NULL,
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
