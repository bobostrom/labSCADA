#![no_std]
#![no_main]

extern crate alloc;

use alloc::vec::Vec;
use esp_backtrace as _;
use esp_hal::timer::timg::TimerGroup;
use esp_radio::esp_now::BROADCAST_ADDRESS;
use wireless_protocol::{DeviceTelemetry, DownlinkPacket, UplinkPacket};

pub mod gateway;

esp_bootloader_esp_idf::esp_app_desc!();

pub struct DirectUsbSerial {
    regs: &'static esp32s3::usb_device::RegisterBlock,
}

impl DirectUsbSerial {
    pub fn new() -> Self {
        let regs = unsafe { &*esp32s3::USB_DEVICE::PTR };
        Self { regs }
    }

    pub fn read_byte(&self) -> Option<u8> {
        if self.regs.ep1_conf().read().serial_out_ep_data_avail().bit_is_set() {
            Some(self.regs.ep1().read().rdwr_byte().bits())
        } else {
            None
        }
    }

    pub fn write_bytes(&self, bytes: &[u8]) {
        for &b in bytes {
            while self.regs.ep1_conf().read().serial_in_ep_data_free().bit_is_clear() {}
            self.regs.ep1().write(|w| unsafe { w.rdwr_byte().bits(b) });
        }
        self.regs.ep1_conf().write(|w| w.wr_done().set_bit());
    }
}

#[esp_hal::main]
fn main() -> ! {
    esp_alloc::heap_allocator!(size: 64 * 1024);

    let peripherals = esp_hal::init(esp_hal::Config::default());

    // 1. Initialize RTOS task scheduler for radio
    let timg0 = TimerGroup::new(peripherals.TIMG0);
    esp_rtos::start(timg0.timer0, peripherals.FROM_CPU_INTR0);

    // 2. Initialize WiFi and ESP-NOW
    let controller = esp_radio::wifi::WifiController::new(peripherals.WIFI, Default::default()).unwrap();
    let esp_now = controller.esp_now();
    let (_manager, mut sender, receiver) = esp_now.split();

    let usb = DirectUsbSerial::new();
    let mut gw = gateway::WirelessGateway::new();

    // Auto-bind Slot 1 for Dewar 1 with 2.8" Touch Display Node MAC: B8:1F:3F:C3:A0:CC
    let node_mac = [0xB8, 0x1F, 0x3F, 0xC3, 0xA0, 0xCC];
    gw.slots[0].bind(node_mac, wireless_protocol::DeviceType::DewarCryo);

    // Auto-bind Slot 2 for Fridge/Freezer with known Node MAC: 20:6E:F1:86:F2:C8
    let fridge_mac = [0x20, 0x6E, 0xF1, 0x86, 0xF2, 0xC8];
    gw.slots[1].bind(fridge_mac, wireless_protocol::DeviceType::FridgeFreezer);
    gw.pairing_enabled = true;

    // Initial baseline: -195.6 C, 3.82V
    let initial_pkt = UplinkPacket::new(
        1,
        node_mac,
        1,
        DeviceTelemetry::Dewar {
            temp_c_x10: -1956,
            battery_mv: 3820,
            sensor_fault: 0,
            access_mode: false,
        },
    );
    let _ = gw.handle_uplink(&initial_pkt, -58, 1);

    let mut rx_buf = [0u8; 256];
    let mut rx_len: usize = 0;
    let mut tx_buf: Vec<u8> = Vec::with_capacity(256);
    let mut idle_count: u32 = 0;
    let mut downlink_buf = [0u8; 64];

    // Modbus RTU 3.5 character silence delimiter (~1.5-2.5 ms)
    const INTER_FRAME_IDLE_CYCLES: u32 = 30_000;

    let mut tick_counter: u32 = 0;
    let mut uptime_sec: u32 = 1;

    loop {
        // A. Process Over-The-Air ESP-NOW Burst Packets
        if let Some(rx_data) = receiver.receive() {
            if let Ok(pkt) = UplinkPacket::deserialize(rx_data.data()) {
                let rssi: i8 = rx_data.info.rx_control.rssi as i8;

                if let Ok(downlink_opt) = gw.handle_uplink(&pkt, rssi, uptime_sec as u64) {
                    if let Some(downlink) = downlink_opt {
                        if let Ok(payload) = downlink.serialize(&mut downlink_buf) {
                            let _ = sender.send(&pkt.mac_address, payload);
                            let _ = sender.send(&BROADCAST_ADDRESS, payload);
                        }
                    }
                }
            }
        }

        // B. Process Incoming Modbus RTU Serial Frames from PLC
        if let Some(byte) = usb.read_byte() {
            if rx_len < rx_buf.len() {
                rx_buf[rx_len] = byte;
                rx_len += 1;
            }
            idle_count = 0;
        } else if rx_len > 0 {
            idle_count += 1;
            if idle_count > INTER_FRAME_IDLE_CYCLES {
                if rx_len >= 4 {
                    tx_buf.clear();
                    if let Ok(true) = gw.process_modbus_rtu(&rx_buf[..rx_len], &mut tx_buf) {
                        usb.write_bytes(&tx_buf);

                        // If Modbus write queued a pending command in any slot, transmit immediately!
                        for slot in &mut gw.slots {
                            if let Some(downlink) = slot.pending_cmd.take() {
                                if let Ok(payload) = downlink.serialize(&mut downlink_buf) {
                                    if let Some(mac) = slot.bound_mac {
                                        let _ = sender.send(&mac, payload);
                                    }
                                    let _ = sender.send(&BROADCAST_ADDRESS, payload);
                                }
                                let _ = slot.modbus_ctx.set_holding(wireless_protocol::modbus_map::REG_COMMAND_MAILBOX as u16, 0);
                            }
                        }
                    }
                }
                rx_len = 0;
                idle_count = 0;
            }
        }

        // C. Periodic Watchdog Ticks
        tick_counter += 1;
        if tick_counter >= 1_000_000 {
            tick_counter = 0;
            uptime_sec = uptime_sec.saturating_add(1);
            gw.watchdog_tick(uptime_sec as u64, 60);
        }
    }
}
