#![no_std]
#![no_main]

extern crate alloc;

use esp_backtrace as _;
use esp_println::println;
use esp_hal::efuse::{self, InterfaceMacAddress};
use esp_hal::timer::timg::TimerGroup;
use esp_hal::rtc_cntl::sleep::{LowPower, RtcSleepConfig};
use esp_hal::analog::adc::{Adc, AdcConfig, Attenuation, AdcCalCurve};
use esp_hal::peripherals::ADC1;
use esp_radio::esp_now::BROADCAST_ADDRESS;
use wireless_protocol::{DeviceTelemetry, DownlinkPacket, UplinkPacket};
use onecable::{OneWire, ds18b20::DS18B20, search_rom::OneWireRomIter, rom_code::RomCode};

esp_bootloader_esp_idf::esp_app_desc!();

// Node configuration auto-generated from equipment manifest by build.rs
include!(concat!(env!("OUT_DIR"), "/node_config.rs"));

const MAX_SENSORS: usize = 3;
const TEMP_SENTINEL_DISCONNECTED: i16 = -9999; // -999.9 °C
const DS18B20_FAMILY_CODE: u8 = 0x28;
const DS18B20_POR_RAW_BITS: i32 = 0x0550; // +85.0 °C power-on-reset sentinel
const REPORT_INTERVAL_SECS: u64 = FRIDGE_REPORT_INTERVAL_SECS;
const CACHED_ROMS_MAGIC: u32 = 0x4652_4933; // "FRI3"
const BUS_SETTLE_MS: u32 = 5;
const CONV_WAIT_MS: u32 = 850;
const SLOT_LABELS: [&str; MAX_SENSORS] = ["Fridge", "Freezer", "Ambient"];

#[esp_hal::ram(unstable(rtc_fast, persistent))]
static mut BOOT_SEQ: u32 = 1;

// Preserve validated 3-probe ROM slot assignments across deep-sleep wakeups so
// a single probe failing to respond never shifts Ambient into Freezer.
#[esp_hal::ram(unstable(rtc_fast, persistent))]
static mut CACHED_ROMS: [[u8; 8]; MAX_SENSORS] = [[0; 8]; MAX_SENSORS];

#[esp_hal::ram(unstable(rtc_fast, persistent))]
static mut CACHED_ROMS_STATE: u32 = 0;

fn log_slot_rom(slot_idx: usize, label: &str, pinned: bool, bytes: &[u8; 8]) {
    let tag = if pinned { "Slot" } else { "Unpinned" };
    println!(
        "  -> {} {} ({}) ROM: {:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}",
        tag, slot_idx + 1, label,
        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7]
    );
}

fn settle_bus_high(ow_pin: &mut esp_hal::gpio::Flex<'_>, delay: &mut esp_hal::delay::Delay) -> bool {
    ow_pin.set_high();
    delay.delay_millis(BUS_SETTLE_MS);
    ow_pin.is_high()
}

fn scan_roms_with_retries(
    ow_pin: &mut esp_hal::gpio::Flex<'_>,
    delay: &mut esp_hal::delay::Delay,
) -> heapless::Vec<RomCode, MAX_SENSORS> {
    let mut best: heapless::Vec<RomCode, MAX_SENSORS> = heapless::Vec::new();

    for attempt in 1..=3 {
        if !settle_bus_high(ow_pin, delay) {
            println!("1-Wire: Bus held LOW before scan attempt {}", attempt);
            continue;
        }
        let mut wire = OneWire::new(ow_pin);
        if !wire.initialize_bus(delay).unwrap_or(false) {
            println!("1-Wire: No presence pulse on scan attempt {}", attempt);
            delay.delay_millis(15);
            continue;
        }

        let mut found: heapless::Vec<RomCode, MAX_SENSORS> = heapless::Vec::new();
        for rom in OneWireRomIter::from_wire(&mut wire, delay) {
            if rom.family_code() == DS18B20_FAMILY_CODE
                && rom.validate_crc()
                && !found.iter().any(|r| r.bytes == rom.bytes)
            {
                if found.push(rom).is_err() {
                    break;
                }
            }
        }
        if found.len() >= best.len() {
            best = found;
        }
        if best.len() == MAX_SENSORS {
            break;
        }
        println!(
            "1-Wire: Scan attempt {} found {}/{} valid DS18B20 ROM(s); retrying...",
            attempt, best.len(), MAX_SENSORS
        );
        delay.delay_millis(20);
    }

    best.sort_by(|a, b| a.bytes.cmp(&b.bytes));
    best
}

fn resolve_slot_sensors(
    ow_pin: &mut esp_hal::gpio::Flex<'_>,
    delay: &mut esp_hal::delay::Delay,
) -> [Option<DS18B20>; MAX_SENSORS] {
    let mut slots: [Option<DS18B20>; MAX_SENSORS] = [None, None, None];

    if let Some(pinned) = FRIDGE_PROBE_ROMS {
        println!("1-Wire: Using manifest-pinned ROM slots (3 probes)");
        for idx in 0..MAX_SENSORS {
            let rom = RomCode { bytes: pinned[idx] };
            slots[idx] = DS18B20::try_from(rom).ok();
        }
        return slots;
    }

    let (cached_state, cached_roms) = unsafe { (CACHED_ROMS_STATE, CACHED_ROMS) };
    let cached_valid = cached_state == CACHED_ROMS_MAGIC
        && cached_roms.iter().all(|b| {
            let r = RomCode { bytes: *b };
            r.family_code() == DS18B20_FAMILY_CODE && r.validate_crc()
        });

    if cached_valid {
        for (idx, bytes) in cached_roms.iter().enumerate() {
            slots[idx] = DS18B20::try_from(RomCode { bytes: *bytes }).ok();
        }
        return slots;
    }

    let roms = scan_roms_with_retries(ow_pin, delay);
    if roms.len() == MAX_SENSORS {
        for (idx, rom) in roms.iter().enumerate() {
            log_slot_rom(idx, SLOT_LABELS[idx], true, &rom.bytes);
            unsafe {
                CACHED_ROMS[idx] = rom.bytes;
            }
            slots[idx] = DS18B20::try_from(*rom).ok();
        }
        unsafe {
            CACHED_ROMS_STATE = CACHED_ROMS_MAGIC;
        }
        println!("1-Wire: Pinned all 3 DS18B20 ROMs in RTC cache");
    } else {
        println!(
            "1-Wire: Only {}/{} probes responded cleanly; leaving RTC cache unlocked",
            roms.len(), MAX_SENSORS
        );
        for (idx, rom) in roms.iter().enumerate() {
            log_slot_rom(idx, SLOT_LABELS[idx], false, &rom.bytes);
            slots[idx] = DS18B20::try_from(*rom).ok();
        }
    }

    slots
}

fn start_conversion(ow_pin: &mut esp_hal::gpio::Flex<'_>, delay: &mut esp_hal::delay::Delay) -> bool {
    for attempt in 1..=2 {
        if !settle_bus_high(ow_pin, delay) {
            continue;
        }
        let mut wire = OneWire::new(ow_pin);
        if wire.skip_rom(delay).is_ok() && wire.write_byte(0x44, delay).is_ok() {
            return true;
        }
        println!("1-Wire: Convert-T attempt {} failed", attempt);
        delay.delay_millis(5);
    }
    false
}

fn read_probe_with_retries(
    ds: &DS18B20,
    ow_pin: &mut esp_hal::gpio::Flex<'_>,
    delay: &mut esp_hal::delay::Delay,
) -> Option<i16> {
    for attempt in 1..=3 {
        if !settle_bus_high(ow_pin, delay) {
            println!("    Read attempt {}: bus held LOW", attempt);
            continue;
        }
        let mut wire = OneWire::new(ow_pin);
        match ds.target_read_scratchpad(&mut wire, delay) {
            Ok(scratchpad) => {
                let raw_bits = scratchpad.temp.to_bits() as i32;
                let temp_c_x10 = ((raw_bits * 10) / 16) as i16;
                if raw_bits == DS18B20_POR_RAW_BITS || temp_c_x10 <= -550 || temp_c_x10 >= 850 {
                    println!("    Read attempt {}: rejected suspicious raw_bits=0x{:04X} ({}/10 C)",
                        attempt, raw_bits, temp_c_x10);
                    return None;
                }
                return Some(temp_c_x10);
            }
            Err(e) => {
                println!("    Read attempt {} failed: {:?}", attempt, e);
                delay.delay_millis(5);
            }
        }
    }
    None
}

#[esp_hal::main]
fn main() -> ! {
    esp_alloc::heap_allocator!(size: 64 * 1024);

    let peripherals = esp_hal::init(esp_hal::Config::default());
    let mut lpwr = LowPower::new(peripherals.LPWR);

    println!("========================================");
    println!("  LabSCADA Wireless Node (ESP32-S3)     ");
    println!("  Profile: Fridge/Freezer/Ambient 1-Wire");
    println!("  Site: {} (Slot {})", SITE_NAME, FRIDGE_SLOT);
    println!("  Batt Cal: {}/{} | Sleep: {}s", FRIDGE_BATT_CAL_NUM, FRIDGE_BATT_CAL_DEN, FRIDGE_REPORT_INTERVAL_SECS);
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

    let mut delay = esp_hal::delay::Delay::new();
    let seq = unsafe {
        let s = BOOT_SEQ;
        BOOT_SEQ = BOOT_SEQ.wrapping_add(1);
        if s == 0 || s > 500_000_000 { 1 } else { s }
    };
    let mut tx_buf = [0u8; 64];

    // Hardware pin mapping for Seeed Studio XIAO ESP32-S3:
    // One-Wire bus is on D5 = GPIO 6 (Open-Drain with internal Pull::Up backup)
    // User LED = GPIO 21 (Active-Low: Low = ON, High = OFF)
    let mut ow_pin = esp_hal::gpio::Flex::new(peripherals.GPIO6);
    ow_pin.apply_output_config(
        &esp_hal::gpio::OutputConfig::default()
            .with_drive_mode(esp_hal::gpio::DriveMode::OpenDrain)
            .with_pull(esp_hal::gpio::Pull::Up),
    );
    ow_pin.apply_input_config(
        &esp_hal::gpio::InputConfig::default()
            .with_pull(esp_hal::gpio::Pull::Up),
    );
    ow_pin.set_input_enable(true);
    ow_pin.set_output_enable(true);
    ow_pin.set_high();

    let mut led = esp_hal::gpio::Output::new(peripherals.GPIO21, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());

    // Initialize ADC1 on GPIO 1 (A0) with factory curve calibration
    let mut adc1_config = AdcConfig::new();
    let mut batt_pin = adc1_config.enable_pin_with_cal::<_, AdcCalCurve<ADC1>>(
        peripherals.GPIO1,
        Attenuation::_11dB,
    );
    let mut adc1 = Adc::new(peripherals.ADC1, adc1_config);

    loop {
        let mut temps = [TEMP_SENTINEL_DISCONNECTED; MAX_SENSORS];
        let mut fault_code: u8 = 0;
        let slots = resolve_slot_sensors(&mut ow_pin, &mut delay);

        if slots.iter().any(|s| s.is_some()) {
            if start_conversion(&mut ow_pin, &mut delay) {
                delay.delay_millis(CONV_WAIT_MS);
                for (idx, maybe_ds) in slots.iter().enumerate() {
                    if let Some(ds) = maybe_ds {
                        if let Some(temp_c_x10) = read_probe_with_retries(ds, &mut ow_pin, &mut delay) {
                            temps[idx] = temp_c_x10;
                            println!("  [Probe {} - {}]: {}/10 C", idx + 1, SLOT_LABELS[idx], temp_c_x10);
                        } else {
                            fault_code |= 1 << idx;
                        }
                    } else {
                        fault_code |= 1 << idx;
                    }
                }
            } else {
                println!("1-Wire: Lost presence during conversion cycle");
                fault_code = 0xFF;
            }
        } else {
            fault_code = 0xFF; // All sensors disconnected
        }

        let (fridge_temp, freezer_temp, ambient_temp) = (temps[0], temps[1], temps[2]);

        // 2. Read Battery Voltage via ADC1 on GPIO 1 (A0)
        let pin_mv: u16 = adc1.read_blocking(&mut batt_pin);
        println!("Battery ADC (GPIO 1): calibrated pin_mv = {} mV", pin_mv);

        // Calibrated against manifest parameters (FRIDGE_BATT_CAL_NUM / FRIDGE_BATT_CAL_DEN)
        let battery_mv = ((pin_mv as u32 * FRIDGE_BATT_CAL_NUM) / FRIDGE_BATT_CAL_DEN) as u16;

        // 3. Broadcast Telemetry via ESP-NOW
        let telemetry = DeviceTelemetry::FridgeFreezer {
            fridge_temp_c_x10: fridge_temp,
            freezer_temp_c_x10: freezer_temp,
            ambient_temp_c_x10: ambient_temp,
            battery_mv,
            sensor_fault: fault_code,
        };

        // Activity pulse: LED ON during transmit
        led.set_level(esp_hal::gpio::Level::Low);

        let uplink = UplinkPacket::new(FRIDGE_SLOT, mac_arr, seq, telemetry);
        if let Ok(payload) = uplink.serialize(&mut tx_buf) {
            println!("Transmitting ESP-NOW packet #{} (Fridge: {}/10 C, Freezer: {}/10 C, Ambient: {}/10 C)...",
                seq, fridge_temp, freezer_temp, ambient_temp);
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

        // 40ms pulse duration, then turn LED OFF
        delay.delay_millis(40);
        led.set_level(esp_hal::gpio::Level::High);

        // 3. Check for Downlink Response from Bridge for 20ms
        for _ in 0..20 {
            if let Some(rx_data) = receiver.receive() {
                if let Ok(downlink) = DownlinkPacket::deserialize(rx_data.data()) {
                    println!("  <- Received Downlink Command from Bridge: {:?}", downlink.command);
                }
            }
            delay.delay_millis(1);
        }

        // 4. Enter Ultra-Low-Power Deep Sleep for reporting interval (configured in equipment.json)
        println!("Entering Ultra-Low-Power Deep Sleep ({}s)...", REPORT_INTERVAL_SECS);
        let deadline = esp_hal::time::Instant::now() + esp_hal::time::Duration::from_secs(REPORT_INTERVAL_SECS);
        lpwr.set_wakeup_deadline(deadline);
        lpwr.sleep_deep(RtcSleepConfig::deep());
    }
}
