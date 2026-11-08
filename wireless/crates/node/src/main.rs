#![no_std]
#![no_main]

extern crate alloc;

use esp_backtrace as _;
use esp_println::println;
use esp_hal::efuse::{self, InterfaceMacAddress};
use esp_hal::timer::timg::TimerGroup;
use esp_radio::esp_now::BROADCAST_ADDRESS;
use wireless_protocol::{DeviceTelemetry, DownlinkPacket, UplinkPacket};

pub mod config;
pub mod max31855;

esp_bootloader_esp_idf::esp_app_desc!();

#[esp_hal::main]
fn main() -> ! {
    esp_alloc::heap_allocator!(size: 64 * 1024);

    let peripherals = esp_hal::init(esp_hal::Config::default());

    println!("========================================");
    println!("  LabSCADA Wireless Node (ESP32-S3)     ");
    println!("  Universal Clinical Sensor Node        ");
    println!("========================================");

    // Initialize RTOS task scheduler required by esp-radio
    let timg0 = TimerGroup::new(peripherals.TIMG0);
    esp_rtos::start(timg0.timer0, peripherals.FROM_CPU_INTR0);

    // Initialize WiFi and ESP-NOW
    let controller = esp_radio::wifi::WifiController::new(peripherals.WIFI, Default::default()).unwrap();
    let esp_now = controller.esp_now();
    let (_manager, mut sender, receiver) = esp_now.split();

    // Read hardware MAC address
    let mac = efuse::interface_mac_address(InterfaceMacAddress::Station);
    let mac_bytes = mac.as_bytes();
    println!("Node MAC Address: {:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}",
        mac_bytes[0], mac_bytes[1], mac_bytes[2], mac_bytes[3], mac_bytes[4], mac_bytes[5]);

    let mut mac_arr = [0u8; 6];
    mac_arr.copy_from_slice(mac_bytes);

    let delay = esp_hal::delay::Delay::new();
    let mut seq: u32 = 1;
    let mut tx_buf = [0u8; 64];

    // Hardware pin mapping for Seeed Studio XIAO ESP32-S3:
    // D8 = GPIO 7 (SCK)
    // D9 = GPIO 8 (MISO / SO)
    // D1 = GPIO 2 (CS)
    let sck = esp_hal::gpio::Output::new(peripherals.GPIO7, esp_hal::gpio::Level::Low, esp_hal::gpio::OutputConfig::default());
    let cs = esp_hal::gpio::Output::new(peripherals.GPIO2, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());
    let miso = esp_hal::gpio::Input::new(peripherals.GPIO8, esp_hal::gpio::InputConfig::default());
    let mut sensor = max31855::Max31855::new(sck, cs, miso);

    loop {
        let reading = sensor.read(&delay);
        println!("MAX31855 [0x{:08X}]: Temp={}/10 C, Ambient={}/10 C, Fault={:?}",
            reading.raw, reading.temp_c_x10, reading.ambient_c_x10, reading.fault);

        let telemetry = DeviceTelemetry::Dewar {
            temp_c_x10: reading.temp_c_x10,
            battery_mv: 3845,
            sensor_fault: reading.fault as u8,
        };

        let uplink = UplinkPacket::new(1, mac_arr, seq, telemetry);
        if let Ok(payload) = uplink.serialize(&mut tx_buf) {
            println!("Transmitting ESP-NOW packet #{} (temp: {}/10 C)...", seq, reading.temp_c_x10);
            match sender.send(&BROADCAST_ADDRESS, payload) {
                Ok(waiter) => {
                    let _ = waiter.wait();
                    println!("  -> Sent successfully");
                }
                Err(_) => {
                    println!("  -> Send error");
                }
            }
        }

        // Check for downlink response from bridge for 20ms
        for _ in 0..20 {
            if let Some(rx_data) = receiver.receive() {
                if let Ok(downlink) = DownlinkPacket::deserialize(rx_data.data()) {
                    println!("  <- Received Downlink Command from Bridge: {:?}", downlink.command);
                }
            }
            delay.delay_millis(1);
        }

        delay.delay_millis(3000);
        seq = seq.wrapping_add(1);
    }
}
