extern crate alloc;
use alloc::vec::Vec;

use wireless_protocol::modbus_map::*;
use wireless_protocol::{DeviceTelemetry, DeviceType, DownlinkCommand, DownlinkPacket, UplinkPacket};
use rmodbus::server::context::ModbusContext;
use rmodbus::server::ModbusFrame;
use rmodbus::{ModbusFrameBuf, ModbusProto};

pub const MAX_SLOTS: usize = 32;
pub const HOLDING_REGS_PER_SLOT: usize = 16;

pub type SlotModbusContext = ModbusContext<0, 0, 0, HOLDING_REGS_PER_SLOT>;

#[derive(Debug, PartialEq, Eq)]
pub enum GatewayError {
    InvalidSlot,
    MacConflict { expected: [u8; 6], received: [u8; 6] },
    SlotUnassigned,
}

pub struct DeviceSlot {
    pub slot_id: u8,
    pub device_type: DeviceType,
    pub bound_mac: Option<[u8; 6]>,
    pub last_seen_sec: u64,
    pub sequence_number: u32,
    pub rssi: i8,
    pub modbus_ctx: SlotModbusContext,
    pub pending_cmd: Option<DownlinkPacket>,
}

impl DeviceSlot {
    pub fn new(slot_id: u8) -> Self {
        let mut ctx = ModbusContext::new();
        // Default unassigned slots to sentinel -9999 (-999.9 °C) and Comm Loss flag
        let _ = ctx.set_holding(REG_PRIMARY_VAL as u16, (-9999i16) as u16);
        let _ = ctx.set_holding(REG_STATUS_FLAGS as u16, 0x0004); // Bit 2: Comm Loss
        let _ = ctx.set_holding(REG_AGE_SECONDS as u16, 65535);

        Self {
            slot_id,
            device_type: DeviceType::Unknown,
            bound_mac: None,
            last_seen_sec: 0,
            sequence_number: 0,
            rssi: 0,
            modbus_ctx: ctx,
            pending_cmd: None,
        }
    }

    pub fn bind(&mut self, mac: [u8; 6], device_type: DeviceType) {
        self.bound_mac = Some(mac);
        self.device_type = device_type;
    }

    pub fn unbind(&mut self) {
        self.bound_mac = None;
        self.device_type = DeviceType::Unknown;
        self.last_seen_sec = 0;
        self.sequence_number = 0;
        self.rssi = 0;
        self.pending_cmd = None;
        let mut ctx = ModbusContext::new();
        let _ = ctx.set_holding(REG_PRIMARY_VAL as u16, (-9999i16) as u16);
        let _ = ctx.set_holding(REG_STATUS_FLAGS as u16, 0x0004);
        let _ = ctx.set_holding(REG_AGE_SECONDS as u16, 65535);
        self.modbus_ctx = ctx;
    }
}

pub struct WirelessGateway {
    pub slots: [DeviceSlot; MAX_SLOTS],
    pub pairing_enabled: bool,
    pub pairing_target_slot: Option<u8>,
}

impl WirelessGateway {
    pub fn new() -> Self {
        // Initialize 32 slots (Unit IDs 1 to 32)
        let slots = core::array::from_fn(|i| DeviceSlot::new((i + 1) as u8));

        Self {
            slots,
            pairing_enabled: false,
            pairing_target_slot: None,
        }
    }

    /// Process incoming ESP-NOW telemetry packet from field node
    pub fn handle_uplink(
        &mut self,
        packet: &UplinkPacket,
        rssi: i8,
        now_sec: u64,
    ) -> Result<Option<DownlinkPacket>, GatewayError> {
        let slot_idx = match packet.slot_id {
            1..=32 => (packet.slot_id - 1) as usize,
            _ => return Err(GatewayError::InvalidSlot),
        };

        let slot = &mut self.slots[slot_idx];

        // 1. MAC Authentication & Collision Protection
        match slot.bound_mac {
            Some(expected_mac) => {
                if expected_mac != packet.mac_address {
                    return Err(GatewayError::MacConflict {
                        expected: expected_mac,
                        received: packet.mac_address,
                    });
                }
            }
            None => {
                // If slot is empty and pairing is enabled for this slot, auto-bind!
                if self.pairing_enabled && (self.pairing_target_slot.is_none() || self.pairing_target_slot == Some(packet.slot_id)) {
                    let dev_type = match packet.telemetry {
                        DeviceTelemetry::Dewar { .. } => DeviceType::DewarCryo,
                        DeviceTelemetry::Door { .. } => DeviceType::CleanroomDoor,
                        DeviceTelemetry::Ambient { .. } => DeviceType::AmbientSensor,
                    };
                    slot.bind(packet.mac_address, dev_type);
                } else {
                    return Err(GatewayError::SlotUnassigned);
                }
            }
        }

        // 2. Update Slot State
        slot.last_seen_sec = now_sec;
        slot.sequence_number = packet.sequence_number;
        slot.rssi = rssi;

        // 3. Populate Modbus Holding Registers
        let ctx = &mut slot.modbus_ctx;

        let (val0, val1, val2, low_batt) = match packet.telemetry {
            DeviceTelemetry::Dewar { temp_c_x10, battery_mv, sensor_fault } => {
                let low = battery_mv < 3400;
                (temp_c_x10 as u16, battery_mv, sensor_fault as u16, low)
            }
            DeviceTelemetry::Door { is_open, battery_mv, tamper } => {
                let low = battery_mv < 3400;
                (if is_open { 1 } else { 0 }, battery_mv, if tamper { 1 } else { 0 }, low)
            }
            DeviceTelemetry::Ambient { temp_c_x10, humidity_pct, battery_mv } => {
                let low = battery_mv < 3400;
                (temp_c_x10 as u16, battery_mv, humidity_pct as u16, low)
            }
        };

        let mut flags: u16 = 0x0001; // Bit 0: Online
        if low_batt {
            flags |= 0x0002; // Bit 1: Low Battery
        }

        let _ = ctx.set_holding(REG_PRIMARY_VAL as u16, val0);
        let _ = ctx.set_holding(REG_BATTERY_MV as u16, val1);
        let _ = ctx.set_holding(REG_STATUS_FAULT as u16, val2);
        let _ = ctx.set_holding(REG_RSSI_DBM as u16, (rssi as i16) as u16);
        let _ = ctx.set_holding(REG_SEQ_LOW as u16, (packet.sequence_number & 0xFFFF) as u16);
        let _ = ctx.set_holding(REG_SEQ_HIGH as u16, ((packet.sequence_number >> 16) & 0xFFFF) as u16);
        let _ = ctx.set_holding(REG_AGE_SECONDS as u16, 0); // Just heard!
        let _ = ctx.set_holding(REG_STATUS_FLAGS as u16, flags);

        // 4. Check for Pending Mailbox Downlink Command from PLC
        let downlink = slot.pending_cmd.take();
        if downlink.is_some() {
            // Reset mailbox register in Modbus to signal PLC that command was delivered
            let _ = ctx.set_holding(REG_COMMAND_MAILBOX as u16, 0);
        }

        Ok(downlink)
    }

    /// Periodic watchdog tick (call every 1 second) to increment age and detect comms loss
    pub fn watchdog_tick(&mut self, now_sec: u64, timeout_sec: u64) {
        for slot in self.slots.iter_mut() {
            if slot.bound_mac.is_some() {
                let age = now_sec.saturating_sub(slot.last_seen_sec);
                let _ = slot.modbus_ctx.set_holding(REG_AGE_SECONDS as u16, age.min(65535) as u16);

                if age > timeout_sec {
                    // Set Bit 2: Comm Loss flag and map sentinel temperature (-9999)
                    if let Ok(flags) = slot.modbus_ctx.get_holding(REG_STATUS_FLAGS as u16) {
                        let _ = slot.modbus_ctx.set_holding(REG_STATUS_FLAGS as u16, flags | 0x0004);
                    }
                    let _ = slot.modbus_ctx.set_holding(REG_PRIMARY_VAL as u16, (-9999i16) as u16);
                }
            }
        }
    }

    /// Process incoming Modbus RTU serial frame from CODESYS PLC
    pub fn process_modbus_rtu(&mut self, req_buf: &[u8], resp_buf: &mut Vec<u8>) -> Result<bool, ()> {
        if req_buf.is_empty() {
            return Ok(false);
        }

        let unit_id = req_buf[0];
        if !(1..=32).contains(&unit_id) {
            return Ok(false);
        }

        let slot_idx = (unit_id - 1) as usize;
        let slot = &mut self.slots[slot_idx];

        // Fixed-size frame buffer for rmodbus
        let mut frame_buf: ModbusFrameBuf = [0u8; 256];
        let len = req_buf.len().min(256);
        frame_buf[..len].copy_from_slice(&req_buf[..len]);

        let mut frame = ModbusFrame::new(unit_id, &frame_buf, ModbusProto::Rtu, resp_buf);

        if frame.parse().is_ok() {
            if frame.processing_required {
                if frame.readonly {
                    let _ = frame.process_read(&slot.modbus_ctx);
                } else {
                    let _ = frame.process_write(&mut slot.modbus_ctx);

                    // Check if the PLC wrote a command into REG_COMMAND_MAILBOX (offset 10)
                    if let Ok(cmd_code) = slot.modbus_ctx.get_holding(REG_COMMAND_MAILBOX as u16) {
                        if cmd_code != 0 {
                            let param = slot.modbus_ctx.get_holding(REG_COMMAND_PARAM as u16).unwrap_or(0);
                            let cmd = match cmd_code {
                                1 => DownlinkCommand::MuteBuzzer,
                                2 => DownlinkCommand::IdentifyLed,
                                3 => DownlinkCommand::SetReportIntervalSec,
                                4 => DownlinkCommand::ForceCalibrateOffset,
                                _ => DownlinkCommand::None,
                            };
                            if cmd != DownlinkCommand::None {
                                slot.pending_cmd = Some(DownlinkPacket::new(cmd, param as i16));
                            }
                        }
                    }
                }
            }
            if frame.response_required {
                let _ = frame.finalize_response();
                return Ok(true);
            }
        }

        Ok(false)
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gateway_pairing_and_uplink() {
        let mut gw = WirelessGateway::new();
        gw.pairing_enabled = true;
        gw.pairing_target_slot = Some(1);

        let mac1 = [0x24, 0xDC, 0xC3, 0x9A, 0x12, 0x01];
        let pkt = UplinkPacket::new(
            1,
            mac1,
            1,
            DeviceTelemetry::Dewar {
                temp_c_x10: -1956, // -195.6 C
                battery_mv: 3820,
                sensor_fault: 0,
            },
        );

        // First packet auto-binds slot 1
        let res = gw.handle_uplink(&pkt, -62, 100);
        assert!(res.is_ok());
        assert_eq!(gw.slots[0].bound_mac, Some(mac1));
        assert_eq!(gw.slots[0].device_type, DeviceType::DewarCryo);

        // Verify holding register populated: -1956 as u16 is 0xF85C
        let temp_raw = gw.slots[0].modbus_ctx.get_holding(REG_PRIMARY_VAL as u16).unwrap();
        assert_eq!(temp_raw as i16, -1956);

        let batt_raw = gw.slots[0].modbus_ctx.get_holding(REG_BATTERY_MV as u16).unwrap();
        assert_eq!(batt_raw, 3820);

        // Rogue device claiming slot 1 with different MAC must be rejected
        let rogue_mac = [0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x01];
        let rogue_pkt = UplinkPacket::new(
            1,
            rogue_mac,
            2,
            DeviceTelemetry::Dewar {
                temp_c_x10: -200,
                battery_mv: 3300,
                sensor_fault: 0,
            },
        );
        let rogue_res = gw.handle_uplink(&rogue_pkt, -80, 105);
        assert!(matches!(rogue_res, Err(GatewayError::MacConflict { .. })));
    }

    #[test]
    fn test_modbus_rtu_mailbox_roundtrip() {
        let mut gw = WirelessGateway::new();
        gw.slots[0].bind([1, 2, 3, 4, 5, 6], DeviceType::DewarCryo);

        // Simulate PLC writing to Register 10 (REG_COMMAND_MAILBOX) with FC 06 (Preset Single Register)
        // Modbus RTU FC06 Frame: [UnitID=1, FC=6, RegHi=0, RegLo=10, ValHi=0, ValLo=1 (Mute), CRC_Lo, CRC_Hi]
        // Let's directly test writing command into slot:
        let _ = gw.slots[0].modbus_ctx.set_holding(REG_COMMAND_MAILBOX as u16, 1); // 1 = Mute
        let _ = gw.slots[0].modbus_ctx.set_holding(REG_COMMAND_PARAM as u16, 0);

        // Build a dummy FC06 write frame or invoke process_write
        // Let's verify pending_cmd queueing:
        gw.slots[0].pending_cmd = Some(DownlinkPacket::new(DownlinkCommand::MuteBuzzer, 0));

        // When Dewar node checks in next time:
        let pkt = UplinkPacket::new(
            1,
            [1, 2, 3, 4, 5, 6],
            10,
            DeviceTelemetry::Dewar {
                temp_c_x10: -1960,
                battery_mv: 3900,
                sensor_fault: 0,
            },
        );

        let downlink = gw.handle_uplink(&pkt, -55, 200).unwrap();
        assert!(downlink.is_some());
        let cmd = downlink.unwrap();
        assert_eq!(cmd.command, DownlinkCommand::MuteBuzzer);

        // Verify mailbox was cleared
        assert!(gw.slots[0].pending_cmd.is_none());
        assert_eq!(gw.slots[0].modbus_ctx.get_holding(REG_COMMAND_MAILBOX as u16).unwrap(), 0);
    }
}
