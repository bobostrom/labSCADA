#![no_std]
#![no_main]

extern crate alloc;

use alloc::vec::Vec;
use esp_backtrace as _;
use esp_hal::delay::Delay;
use esp_hal::gpio::{Level, Output, OutputConfig};
use esp_hal::time::{Duration, Instant};
use esp_hal::timer::timg::TimerGroup;
use esp_hal::uart::{Config as UartConfig, Uart};
use esp_hal::Blocking;
use esp_radio::esp_now::BROADCAST_ADDRESS;
use wireless_protocol::{DeviceTelemetry, UplinkPacket};

pub mod gateway;

esp_bootloader_esp_idf::esp_app_desc!();

/// Modbus RTU T3.5 inter-frame silence delimiter at 115200 baud (spec minimum 1.75 ms).
const RTU_FRAME_GAP: Duration = Duration::from_micros(2_000);

/// Accumulates Modbus RTU bytes for a single serial interface and detects frame completion via T3.5 idle gap.
struct RtuFrameBuffer {
    buf: [u8; 256],
    len: usize,
    overflowed: bool,
    last_rx: Instant,
}

impl RtuFrameBuffer {
    fn new() -> Self {
        Self {
            buf: [0u8; 256],
            len: 0,
            overflowed: false,
            last_rx: Instant::now(),
        }
    }

    fn push_byte(&mut self, byte: u8, now: Instant) {
        if self.len < self.buf.len() {
            self.buf[self.len] = byte;
            self.len += 1;
        } else {
            self.overflowed = true;
        }
        self.last_rx = now;
    }

    /// Invokes `on_frame` once a complete non-overflowed frame has been idle for `RTU_FRAME_GAP`.
    fn poll_ready<F>(&mut self, mut on_frame: F)
    where
        F: FnMut(&[u8]),
    {
        if self.len > 0 && self.last_rx.elapsed() >= RTU_FRAME_GAP {
            if !self.overflowed && self.len >= 4 {
                on_frame(&self.buf[..self.len]);
            }
            self.len = 0;
            self.overflowed = false;
        }
    }
}

/// Half-duplex RS-485 port using UART1 with explicit ST485 DE / /RE transceiver direction control.
struct Rs485Port<'d> {
    uart: Uart<'d, Blocking>,
    de: Output<'d>,
    re_n: Output<'d>,
    delay: Delay,
}

impl<'d> Rs485Port<'d> {
    fn new(uart: Uart<'d, Blocking>, de: Output<'d>, re_n: Output<'d>) -> Self {
        Self {
            uart,
            de,
            re_n,
            delay: Delay::new(),
        }
    }

    /// Drains any buffered UART RX bytes into `frame_buf`. Returns true if at least one byte arrived.
    fn poll_rx(&mut self, frame_buf: &mut RtuFrameBuffer) -> bool {
        let mut received = false;
        let mut scratch = [0u8; 64];
        while self.uart.read_ready() {
            match self.uart.read_buffered(&mut scratch) {
                Ok(0) => break,
                Ok(n) => {
                    let now = Instant::now();
                    for &b in &scratch[..n] {
                        frame_buf.push_byte(b, now);
                    }
                    received = true;
                }
                Err(_) => {
                    // Discard corrupted partial frame after line noise/framing glitch.
                    frame_buf.len = 0;
                    frame_buf.overflowed = false;
                    break;
                }
            }
        }
        received
    }

    /// Drives DE + /RE high, shifts out the full Modbus RTU response, waits for idle, then restores RX mode.
    fn send_frame(&mut self, bytes: &[u8]) {
        self.re_n.set_high();
        self.de.set_high();
        self.delay.delay_micros(10);

        let mut offset = 0;
        while offset < bytes.len() {
            match self.uart.write(&bytes[offset..]) {
                Ok(n) if n > 0 => offset += n,
                _ => break,
            }
        }
        let _ = self.uart.flush();
        self.delay.delay_micros(10);

        self.de.set_low();
        self.re_n.set_low();
    }
}

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

/// Processes a completed Modbus RTU request frame, writes any reply via `send_reply`, and returns true if slots may have pending downlinks.
fn handle_rtu_frame<F>(
    frame_buf: &mut RtuFrameBuffer,
    gw: &mut gateway::WirelessGateway,
    tx_buf: &mut Vec<u8>,
    mut send_reply: F,
) -> bool
where
    F: FnMut(&[u8]),
{
    let mut processed_reply = false;
    frame_buf.poll_ready(|frame| {
        tx_buf.clear();
        if let Ok(true) = gw.process_modbus_rtu(frame, tx_buf) {
            send_reply(tx_buf);
            processed_reply = true;
        }
    });
    processed_reply
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

    // 3. Initialize both Modbus RTU interfaces: USB CDC and RS-485 (UART1 + ST485)
    // XIAO ESP32-S3 carrier PCB pinout: RO=D7(GPIO44), DI=D6(GPIO43), /RE=D3(GPIO4), DE=D2(GPIO3)
    let usb = DirectUsbSerial::new();
    let rs485_uart = Uart::new(peripherals.UART1, UartConfig::default().with_baudrate(115_200))
        .unwrap()
        .with_rx(peripherals.GPIO44)
        .with_tx(peripherals.GPIO43);
    let rs485_de = Output::new(peripherals.GPIO3, Level::Low, OutputConfig::default());
    let rs485_re_n = Output::new(peripherals.GPIO4, Level::Low, OutputConfig::default());
    let mut rs485 = Rs485Port::new(rs485_uart, rs485_de, rs485_re_n);

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

    let mut usb_rx_buf = RtuFrameBuffer::new();
    let mut rs485_rx_buf = RtuFrameBuffer::new();
    let mut tx_buf: Vec<u8> = Vec::with_capacity(256);
    let mut downlink_buf = [0u8; 64];

    let mut last_watchdog = Instant::now();
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

        // B. Drain Incoming Modbus RTU Bytes from USB CDC and RS-485
        while let Some(byte) = usb.read_byte() {
            usb_rx_buf.push_byte(byte, Instant::now());
        }
        rs485.poll_rx(&mut rs485_rx_buf);

        // C. Process Completed Modbus RTU Frames on Either Interface
        let mut dispatch_downlinks = false;
        if handle_rtu_frame(&mut usb_rx_buf, &mut gw, &mut tx_buf, |reply| {
            usb.write_bytes(reply);
        }) {
            dispatch_downlinks = true;
        }
        if handle_rtu_frame(&mut rs485_rx_buf, &mut gw, &mut tx_buf, |reply| {
            rs485.send_frame(reply);
        }) {
            dispatch_downlinks = true;
        }

        // If a Modbus write queued a pending command in any slot, transmit over ESP-NOW immediately.
        if dispatch_downlinks {
            for slot in &mut gw.slots {
                if let Some(downlink) = slot.pending_cmd.take() {
                    if let Ok(payload) = downlink.serialize(&mut downlink_buf) {
                        if let Some(mac) = slot.bound_mac {
                            let _ = sender.send(&mac, payload);
                        }
                        let _ = sender.send(&BROADCAST_ADDRESS, payload);
                    }
                    let _ = slot
                        .modbus_ctx
                        .set_holding(wireless_protocol::modbus_map::REG_COMMAND_MAILBOX as u16, 0);
                }
            }
        }

        // D. Periodic Watchdog Ticks (1 Hz)
        if last_watchdog.elapsed() >= Duration::from_secs(1) {
            last_watchdog = Instant::now();
            uptime_sec = uptime_sec.saturating_add(1);
            gw.watchdog_tick(uptime_sec as u64, 60);
        }
    }
}
