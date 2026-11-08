#![cfg_attr(not(feature = "std"), no_std)]

use serde::{Deserialize, Serialize};

/// Maximum wireless packet size for ESP-NOW framing
pub const MAX_PACKET_LEN: usize = 64;

/// Protocol magic header bytes to reject accidental noise or foreign radios
pub const PROTOCOL_MAGIC: u16 = 0x4C53; // 'L' 'S' (LabSCADA)
pub const PROTOCOL_VERSION: u8 = 1;

/// Device profile types supported in the cleanroom ecosystem
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum DeviceType {
    Unknown = 0,
    DewarCryo = 1,
    CleanroomDoor = 2,
    AmbientSensor = 3,
}

impl Default for DeviceType {
    fn default() -> Self {
        DeviceType::Unknown
    }
}

/// Device-specific telemetry payloads (type-safe, compact)
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum DeviceTelemetry {
    Dewar {
        /// Temperature in Celsius * 10 (-1960 = -196.0 C)
        temp_c_x10: i16,
        /// Battery voltage in millivolts (e.g. 3850 = 3.85V)
        battery_mv: u16,
        /// Sensor health: 0 = OK, 1 = Probe Disconnected, 2 = Short, 3 = Hardware Fault
        sensor_fault: u8,
    },
    Door {
        /// Primary contact state: false = Closed, true = Open
        is_open: bool,
        /// Battery voltage in millivolts
        battery_mv: u16,
        /// Tamper or vibration detected
        tamper: bool,
    },
    Ambient {
        /// Temperature in Celsius * 10 (225 = 22.5 C)
        temp_c_x10: i16,
        /// Relative humidity percentage (0 - 100%)
        humidity_pct: u8,
        /// Battery voltage in millivolts
        battery_mv: u16,
    },
}

/// Over-the-air packet transmitted from sensor node to bridge
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct UplinkPacket {
    pub magic: u16,
    pub version: u8,
    pub slot_id: u8,
    pub mac_address: [u8; 6],
    pub sequence_number: u32,
    pub telemetry: DeviceTelemetry,
}

impl UplinkPacket {
    pub fn new(slot_id: u8, mac_address: [u8; 6], sequence_number: u32, telemetry: DeviceTelemetry) -> Self {
        Self {
            magic: PROTOCOL_MAGIC,
            version: PROTOCOL_VERSION,
            slot_id,
            mac_address,
            sequence_number,
            telemetry,
        }
    }

    /// Serialize to binary buffer using postcard
    pub fn serialize<'a>(&self, buf: &'a mut [u8]) -> Result<&'a [u8], postcard::Error> {
        postcard::to_slice(self, buf).map(|s| &*s)
    }

    /// Deserialize from binary buffer
    pub fn deserialize(buf: &[u8]) -> Result<Self, postcard::Error> {
        let pkt: Self = postcard::from_bytes(buf)?;
        if pkt.magic != PROTOCOL_MAGIC || pkt.version != PROTOCOL_VERSION {
            return Err(postcard::Error::DeserializeBadEncoding);
        }
        Ok(pkt)
    }
}

/// Downlink command returned in the same wake window (Mailbox response)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum DownlinkCommand {
    None = 0,
    MuteBuzzer = 1,
    IdentifyLed = 2,
    SetReportIntervalSec = 3,
    ForceCalibrateOffset = 4,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct DownlinkPacket {
    pub magic: u16,
    pub command: DownlinkCommand,
    pub parameter: i16,
}

impl DownlinkPacket {
    pub fn new(command: DownlinkCommand, parameter: i16) -> Self {
        Self {
            magic: PROTOCOL_MAGIC,
            command,
            parameter,
        }
    }

    pub fn serialize<'a>(&self, buf: &'a mut [u8]) -> Result<&'a [u8], postcard::Error> {
        postcard::to_slice(self, buf).map(|s| &*s)
    }

    pub fn deserialize(buf: &[u8]) -> Result<Self, postcard::Error> {
        let pkt: Self = postcard::from_bytes(buf)?;
        if pkt.magic != PROTOCOL_MAGIC {
            return Err(postcard::Error::DeserializeBadEncoding);
        }
        Ok(pkt)
    }
}

/// Standardized Modbus register offsets for each virtual device
pub mod modbus_map {
    pub const REG_PRIMARY_VAL: usize = 0;   // Temp * 10 (Dewar/Ambient) or Open/Closed (Door)
    pub const REG_BATTERY_MV: usize = 1;     // Battery voltage (e.g. 3850 mV)
    pub const REG_STATUS_FAULT: usize = 2;   // Fault/Tamper/Quality code
    pub const REG_RSSI_DBM: usize = 3;       // Signal RSSI (as signed integer in u16)
    pub const REG_SEQ_LOW: usize = 4;        // Sequence counter low word
    pub const REG_SEQ_HIGH: usize = 5;       // Sequence counter high word
    pub const REG_AGE_SECONDS: usize = 6;    // Seconds since last received packet (watchdog)
    pub const REG_STATUS_FLAGS: usize = 7;   // Bit 0 = Online, Bit 1 = Low Battery, Bit 2 = Comm Loss

    pub const REG_COMMAND_MAILBOX: usize = 10; // Supervisory command written by PLC
    pub const REG_COMMAND_PARAM: usize = 11;   // Supervisory command parameter
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_serialization_roundtrip_dewar() {
        let pkt = UplinkPacket::new(
            1,
            [0x24, 0xDC, 0xC3, 0x9A, 0x12, 0x4E],
            1042,
            DeviceTelemetry::Dewar {
                temp_c_x10: -1954,
                battery_mv: 3820,
                sensor_fault: 0,
            },
        );

        let mut buf = [0u8; MAX_PACKET_LEN];
        let bytes = pkt.serialize(&mut buf).unwrap();

        // Ensure compact size (< 25 bytes)
        assert!(bytes.len() <= 25, "Packet too large: {} bytes", bytes.len());

        let decoded = UplinkPacket::deserialize(bytes).unwrap();
        assert_eq!(pkt, decoded);
    }

    #[test]
    fn test_serialization_roundtrip_door() {
        let pkt = UplinkPacket::new(
            2,
            [0x40, 0x22, 0xD8, 0x11, 0xAB, 0x05],
            45,
            DeviceTelemetry::Door {
                is_open: true,
                battery_mv: 3950,
                tamper: false,
            },
        );

        let mut buf = [0u8; MAX_PACKET_LEN];
        let bytes = pkt.serialize(&mut buf).unwrap();
        let decoded = UplinkPacket::deserialize(bytes).unwrap();
        assert_eq!(pkt, decoded);
    }
}

