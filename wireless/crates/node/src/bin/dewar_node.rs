#![no_std]
#![no_main]

extern crate alloc;

use esp_backtrace as _;
use esp_println::println;
use esp_hal::efuse::{self, InterfaceMacAddress};
use esp_hal::timer::timg::TimerGroup;
use esp_hal::rtc_cntl::sleep::{LowPower, RtcSleepConfig};
use esp_hal::analog::adc::{Adc, AdcConfig, Attenuation};
use esp_radio::esp_now::BROADCAST_ADDRESS;
use wireless_protocol::{DeviceTelemetry, DownlinkPacket, UplinkPacket};
use wireless_node::max31855;

esp_bootloader_esp_idf::esp_app_desc!();

const REPORT_INTERVAL_SECS: u64 = 20; // 20-second clinical reporting interval

#[esp_hal::ram(unstable(rtc_fast, persistent))]
static mut BOOT_SEQ: u32 = 1;

#[esp_hal::main]
fn main() -> ! {
    esp_alloc::heap_allocator!(size: 64 * 1024);

    let peripherals = esp_hal::init(esp_hal::Config::default());
    let mut lpwr = LowPower::new(peripherals.LPWR);

    let seq = unsafe {
        let s = BOOT_SEQ;
        BOOT_SEQ = BOOT_SEQ.wrapping_add(1);
        if s == 0 || s > 500_000_000 { 1 } else { s }
    };

    println!("========================================");
    println!("  LabSCADA Wireless Node (ESP32-S3)     ");
    println!("  Profile: Cryogenic Dewar (MAX31855)   ");
    println!("  Mode: Low-Power Cycle #{}", seq);
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
    let mut tx_buf = [0u8; 64];

    // Hardware pin mapping for Seeed Studio XIAO ESP32-S3:
    // D8 = GPIO 7 (SCK)
    // D9 = GPIO 8 (MISO / SO)
    // D1 = GPIO 2 (CS)
    // User LED = GPIO 21 (Active-Low: Low = ON, High = OFF)
    let sck = esp_hal::gpio::Output::new(peripherals.GPIO7, esp_hal::gpio::Level::Low, esp_hal::gpio::OutputConfig::default());
    let cs = esp_hal::gpio::Output::new(peripherals.GPIO2, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());
    let miso = esp_hal::gpio::Input::new(peripherals.GPIO8, esp_hal::gpio::InputConfig::default());
    let mut sensor = max31855::Max31855::new(sck, cs, miso);

    let mut led = esp_hal::gpio::Output::new(peripherals.GPIO21, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());

    loop {
        // Activity pulse: LED ON during sample & transmit
        led.set_level(esp_hal::gpio::Level::Low);

        let reading = sensor.read(&delay);
        println!("MAX31855 [0x{:08X}]: Temp={}/10 C, Ambient={}/10 C, Fault={:?}",
            reading.raw, reading.temp_c_x10, reading.ambient_c_x10, reading.fault);

        // Read Battery Voltage via ADC1 on GPIO 1 (A0)
        let mut adc1_config = AdcConfig::new();
        let mut batt_pin = adc1_config.enable_pin(peripherals.GPIO1, Attenuation::_11dB);
        let mut adc1 = Adc::new(peripherals.ADC1, adc1_config);
        let raw_adc: u16 = adc1.read_blocking(&mut batt_pin);
        println!("Battery ADC (GPIO 1): raw = {}", raw_adc);

        // 12-bit ADC (0..4095) with 11dB attenuation (~3100 mV full scale).
        // External 2:1 divider: V_batt = V_pin * 2 = raw * (3100 * 2) / 4095 = raw * 6200 / 4095.
        let calculated_mv = ((raw_adc as u32 * 6200) / 4095) as u16;
        let battery_mv = if calculated_mv >= 2500 && calculated_mv <= 4500 {
            calculated_mv
        } else {
            3845 // Nominal baseline fallback if on USB power or divider not fitted
        };

        let telemetry = DeviceTelemetry::Dewar {
            temp_c_x10: reading.temp_c_x10,
            battery_mv,
            sensor_fault: reading.fault as u8,
        };

        let uplink = UplinkPacket::new(1, mac_arr, seq, telemetry);
        if let Ok(payload) = uplink.serialize(&mut tx_buf) {
            println!("Transmitting ESP-NOW packet #{} (temp: {}/10 C, batt: {} mV)...", seq, reading.temp_c_x10, battery_mv);
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

        // Brief 40ms pulse duration, then turn LED OFF
        delay.delay_millis(40);
        led.set_level(esp_hal::gpio::Level::High);

        // Check for downlink response from bridge for 20ms
        for _ in 0..20 {
            if let Some(rx_data) = receiver.receive() {
                if let Ok(downlink) = DownlinkPacket::deserialize(rx_data.data()) {
                    println!("  <- Received Downlink Command from Bridge: {:?}", downlink.command);
                }
            }
            delay.delay_millis(1);
        }

        // Enter Low-Power Deep Sleep for reporting interval (20 seconds)
        println!("Entering Ultra-Low-Power Deep Sleep ({}s)...", REPORT_INTERVAL_SECS);
        let deadline = esp_hal::time::Instant::now() + esp_hal::time::Duration::from_secs(REPORT_INTERVAL_SECS);
        lpwr.set_wakeup_deadline(deadline);
        lpwr.sleep_deep(RtcSleepConfig::deep());
    }
}

