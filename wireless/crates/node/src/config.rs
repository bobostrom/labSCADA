use wireless_protocol::DeviceType;

pub struct NodeConfig {
    pub slot_id: u8,
    pub device_type: DeviceType,
    pub sleep_interval_sec: u16,
    pub low_battery_threshold_mv: u16,
}

impl Default for NodeConfig {
    fn default() -> Self {
        Self {
            slot_id: 1, // Default slot
            device_type: DeviceType::DewarCryo,
            sleep_interval_sec: 30, // 30-second reporting by default
            low_battery_threshold_mv: 3300,
        }
    }
}

