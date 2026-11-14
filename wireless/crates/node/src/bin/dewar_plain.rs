//! Headless Cryogenic Dewar #3 Wireless Node (`dewar_plain`)
//!
//! Reads a MAX31865 RTD (PT100, 430 Ohm Rref, 3-Wire) and battery voltage divider,
//! transmits `DeviceTelemetry::Dewar` over ESP-NOW on Slot 3, and enters deep sleep.
//!
//! Default target: **Adafruit QT Py ESP32-S3 (8 MB Flash / No PSRAM)**
//! - Battery A0 (Pin 1): `GPIO 18` (`ADC2_CH7`, sampled before radio startup)
//! - MAX31865 CS (SDA, Pin 5): `GPIO 7`
//! - MAX31865 SCK: `GPIO 36` | MOSI/SDI (`MO`): `GPIO 35` | MISO/SDO (`MI`): `GPIO 37`
//! - NeoPixel Power: `GPIO 38` (held LOW for 0 mA quiescent draw)
//!
//! Optional `--features xiao`: **Seeed Studio XIAO ESP32-S3** (identical footprint, XIAO GPIOs)
//! - Battery A0 (Pin 1): `GPIO 1` (`ADC1_CH0`)
//! - MAX31865 CS (D4/SDA, Pin 5): `GPIO 5`
//! - MAX31865 SCK (`D8`): `GPIO 7` | MOSI (`D10`): `GPIO 9` | MISO (`D9`): `GPIO 8`
//! - User LED: `GPIO 21` (Active-Low)

#![no_std]
#![no_main]

extern crate alloc;

use esp_backtrace as _;
use esp_hal::analog::adc::{Adc, AdcCalCurve, AdcConfig, Attenuation};
use esp_hal::delay::Delay;
use esp_hal::efuse::{self, InterfaceMacAddress};
use esp_hal::gpio::{Input, InputConfig, Level, Output, OutputConfig};
use esp_hal::rtc_cntl::sleep::{LowPower, RtcSleepConfig};
use esp_hal::timer::timg::TimerGroup;
use esp_println::println;
use esp_radio::esp_now::BROADCAST_ADDRESS;
use wireless_protocol::max31865::{self, eval_rtd_reading, Max31865, RtdType, WireMode};
use wireless_protocol::{DeviceTelemetry, DownlinkPacket, UplinkPacket};

esp_bootloader_esp_idf::esp_app_desc!();

// Node configuration auto-generated from equipment manifest by build.rs
include!(concat!(env!("OUT_DIR"), "/node_config.rs"));

const REPORT_INTERVAL_SECS: u64 = DEWAR3_REPORT_INTERVAL_SECS;

#[esp_hal::ram(unstable(rtc_fast, persistent))]
static mut BOOT_SEQ: u32 = 1;

#[cfg(not(feature = "xiao"))]
const BOARD_NAME: &str = "Adafruit QT Py ESP32-S3 (8MB/No PSRAM)";
#[cfg(feature = "xiao")]
const BOARD_NAME: &str = "Seeed Studio XIAO ESP32-S3";

/// Initialize MAX31865 (PT100, 430 Ohm Rref, 3-Wire), read temperature, and enter low-power standby.
fn read_max31865_sample<'d>(
    sck: Output<'d>,
    mosi: Output<'d>,
    miso: Input<'d>,
    cs: Output<'d>,
    delay: &mut Delay,
) -> (u8, max31865::Max31865Reading) {
    let mut sensor = Max31865::new(
        sck,
        mosi,
        miso,
        cs,
        RtdType::Pt100Rref430,
        WireMode::ThreeWire,
    );
    sensor.init(delay);
    let cfg = sensor.read_register(max31865::REG_CONFIG, delay);
    let reading = sensor.read_temperature(delay);
    // Cut RTD VBIAS excitation (~2 mA) before entering deep sleep
    sensor.shutdown(delay);
    (cfg, reading)
}

#[cfg(not(feature = "xiao"))]
fn sample_qtpy_battery_mv(
    adc2: esp_hal::peripherals::ADC2<'static>,
    gpio18: esp_hal::peripherals::GPIO18<'static>,
) -> u16 {
    let mut adc2_config = AdcConfig::new();
    let mut batt_pin =
        adc2_config.enable_pin_with_cal::<_, AdcCalCurve<esp_hal::peripherals::ADC2>>(gpio18, Attenuation::_11dB);
    let mut adc = Adc::new(adc2, adc2_config);
    adc.read_blocking(&mut batt_pin)
}

#[cfg(feature = "xiao")]
fn sample_xiao_battery_mv(
    adc1: esp_hal::peripherals::ADC1<'static>,
    gpio1: esp_hal::peripherals::GPIO1<'static>,
) -> u16 {
    let mut adc1_config = AdcConfig::new();
    let mut batt_pin =
        adc1_config.enable_pin_with_cal::<_, AdcCalCurve<esp_hal::peripherals::ADC1>>(gpio1, Attenuation::_11dB);
    let mut adc = Adc::new(adc1, adc1_config);
    adc.read_blocking(&mut batt_pin)
}

#[esp_hal::main]
fn main() -> ! {
    esp_alloc::heap_allocator!(size: 64 * 1024);

    let peripherals = esp_hal::init(esp_hal::Config::default());
    let mut delay = Delay::new();

    let seq = unsafe {
        let s = BOOT_SEQ;
        BOOT_SEQ = BOOT_SEQ.wrapping_add(1);
        if s == 0 || s > 500_000_000 { 1 } else { s }
    };

    println!("========================================");
    println!("  LabSCADA Wireless Node (ESP32-S3)     ");
    println!("  Profile: Dewar #{} Plain (MAX31865)   ", DEWAR3_SLOT);
    println!("  Board: {}", BOARD_NAME);
    println!("  Site: {} | Cycle #{}", SITE_NAME, seq);
    println!("========================================");

    // Sample battery ADC (before Wi-Fi startup so QT Py ADC2 never contends with RF) and MAX31865.
    #[cfg(not(feature = "xiao"))]
    let (pin_mv, rtd_cfg, reading, mut led, _neopix_pwr) = {
        let neopix_pwr = Output::new(peripherals.GPIO38, Level::Low, OutputConfig::default());
        let pin_mv = sample_qtpy_battery_mv(peripherals.ADC2, peripherals.GPIO18);
        println!("Battery ADC (GPIO 18 / A0): calibrated pin_mv = {} mV", pin_mv);

        let sck = Output::new(peripherals.GPIO36, Level::Low, OutputConfig::default());
        let mosi = Output::new(peripherals.GPIO35, Level::Low, OutputConfig::default());
        let miso = Input::new(peripherals.GPIO37, InputConfig::default());
        let cs = Output::new(peripherals.GPIO7, Level::High, OutputConfig::default());
        let (cfg, reading) = read_max31865_sample(sck, mosi, miso, cs, &mut delay);
        (pin_mv, cfg, reading, None::<Output<'static>>, Some(neopix_pwr))
    };

    #[cfg(feature = "xiao")]
    let (pin_mv, rtd_cfg, reading, mut led, _neopix_pwr) = {
        let led = Output::new(peripherals.GPIO21, Level::Low, OutputConfig::default());
        let pin_mv = sample_xiao_battery_mv(peripherals.ADC1, peripherals.GPIO1);
        println!("Battery ADC (GPIO 1 / A0): calibrated pin_mv = {} mV", pin_mv);

        let sck = Output::new(peripherals.GPIO7, Level::Low, OutputConfig::default());
        let mosi = Output::new(peripherals.GPIO9, Level::Low, OutputConfig::default());
        let miso = Input::new(peripherals.GPIO8, InputConfig::default());
        let cs = Output::new(peripherals.GPIO5, Level::High, OutputConfig::default());
        let (cfg, reading) = read_max31865_sample(sck, mosi, miso, cs, &mut delay);
        (pin_mv, cfg, reading, Some(led), None::<Output<'static>>)
    };

    let battery_mv = ((pin_mv as u32 * DEWAR3_BATT_CAL_NUM) / DEWAR3_BATT_CAL_DEN) as u16;
    let (temp_c_x10, fault_code) = eval_rtd_reading(&reading);

    delay.delay_millis(4);
    println!(
        "[MAX31865] cfg=0x{:02X} raw=0x{:04X} R={}.{:02} ohm",
        rtd_cfg,
        reading.raw_adc,
        reading.resistance_x100 / 100,
        reading.resistance_x100 % 100
    );
    delay.delay_millis(4);
    println!(
        "[TELEMETRY] Temp={} dC Fault={} (st=0x{:02X}) Batt={} mV",
        temp_c_x10, fault_code, reading.fault_status, battery_mv
    );

    // Initialize RTOS task scheduler required by esp-radio
    let timg0 = TimerGroup::new(peripherals.TIMG0);
    esp_rtos::start(timg0.timer0, peripherals.FROM_CPU_INTR0);

    // Initialize WiFi and ESP-NOW
    let controller = esp_radio::wifi::WifiController::new(peripherals.WIFI, Default::default()).unwrap();
    let esp_now = controller.esp_now();
    let (_manager, mut sender, receiver) = esp_now.split();

    let mac = efuse::interface_mac_address(InterfaceMacAddress::Station);
    let mac_bytes = mac.as_bytes();
    println!(
        "Node MAC Address: {:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}",
        mac_bytes[0], mac_bytes[1], mac_bytes[2], mac_bytes[3], mac_bytes[4], mac_bytes[5]
    );

    let mut mac_arr = [0u8; 6];
    mac_arr.copy_from_slice(mac_bytes);

    let mut tx_buf = [0u8; 64];
    let telemetry = DeviceTelemetry::Dewar {
        temp_c_x10,
        battery_mv,
        sensor_fault: fault_code,
        access_mode: false,
    };

    let uplink = UplinkPacket::new(DEWAR3_SLOT, mac_arr, seq, telemetry);
    if let Ok(payload) = uplink.serialize(&mut tx_buf) {
        println!("Transmitting ESP-NOW slot {} packet #{}...", DEWAR3_SLOT, seq);
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

    // Listen briefly for downlink commands from bridge before deep sleep
    for _ in 0..20 {
        if let Some(rx_data) = receiver.receive() {
            if let Ok(downlink) = DownlinkPacket::deserialize(rx_data.data()) {
                println!("  <- Downlink Command: {:?}", downlink.command);
            }
        }
        delay.delay_millis(1);
    }

    if let Some(ref mut led_pin) = led {
        led_pin.set_level(Level::High);
    }

    println!("Entering Deep Sleep ({}s)...", REPORT_INTERVAL_SECS);
    let mut lpwr = LowPower::new(peripherals.LPWR);
    let deadline = esp_hal::time::Instant::now() + esp_hal::time::Duration::from_secs(REPORT_INTERVAL_SECS);
    lpwr.set_wakeup_deadline(deadline);
    lpwr.sleep_deep(RtcSleepConfig::deep());
}
