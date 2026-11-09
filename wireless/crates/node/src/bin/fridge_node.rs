#![no_std]
#![no_main]

extern crate alloc;

use esp_backtrace as _;
use esp_println::println;
use esp_hal::efuse::{self, InterfaceMacAddress};
use esp_hal::timer::timg::TimerGroup;
use esp_radio::esp_now::BROADCAST_ADDRESS;
use wireless_protocol::{DeviceTelemetry, DownlinkPacket, UplinkPacket};
use onecable::{OneWire, ds18b20::DS18B20, search_rom::OneWireRomIter};

esp_bootloader_esp_idf::esp_app_desc!();

const MAX_SENSORS: usize = 3;
const TEMP_SENTINEL_DISCONNECTED: i16 = -9999; // -999.9 °C

#[esp_hal::main]
fn main() -> ! {
    esp_alloc::heap_allocator!(size: 64 * 1024);

    let peripherals = esp_hal::init(esp_hal::Config::default());

    println!("========================================");
    println!("  LabSCADA Wireless Node (ESP32-S3)     ");
    println!("  Profile: Fridge/Freezer/Ambient 1-Wire");
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
    let mut seq: u32 = 1;
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

    let mut sensors: heapless::Vec<DS18B20, MAX_SENSORS> = heapless::Vec::new();

    loop {
        // Ensure pin is released high and verify line is not pulled to ground
        ow_pin.set_high();
        delay.delay_micros(10);
        let bus_high = ow_pin.is_high();

        // 1. Bus Discovery if no sensors currently enumerated
        if !bus_high {
            println!("1-Wire: Line D5 (GPIO 6) is held LOW (shorted or floating). Waiting for pullup/sensor...");
            sensors.clear();
        } else if sensors.is_empty() {
            let mut wire = OneWire::new(&mut ow_pin);
            match wire.initialize_bus(&mut delay) {
                Ok(true) => {
                    println!("1-Wire: Presence pulse detected on Pin D5 (GPIO 6). Scanning ROMs...");
                    for rom in OneWireRomIter::from_wire(&mut wire, &mut delay) {
                        println!("  -> Discovered 1-Wire ROM: {:02X?}", rom.bytes);
                        if let Ok(ds) = DS18B20::try_from(rom) {
                            if sensors.push(ds).is_err() {
                                break;
                            }
                        }
                    }
                    println!("1-Wire: Enumerated {} DS18B20 sensor(s)", sensors.len());
                }
                Ok(false) => {
                    println!("1-Wire: No presence pulse on Pin D5 (GPIO 6) - no sensor responded");
                }
                Err(_) => {
                    println!("1-Wire: Bus error during initialization");
                }
            }
        }

        let mut fridge_temp = TEMP_SENTINEL_DISCONNECTED;
        let mut freezer_temp = TEMP_SENTINEL_DISCONNECTED;
        let mut ambient_temp = TEMP_SENTINEL_DISCONNECTED;
        let mut fault_code: u8 = 0;

        if !sensors.is_empty() {
            let mut wire = OneWire::new(&mut ow_pin);

            // A. Broadcast Simultaneous Temperature Conversion (SKIP ROM 0xCC + CONVERT T 0x44)
            if wire.initialize_bus(&mut delay).unwrap_or(false) {
                let _ = wire.skip_rom(&mut delay);
                let _ = wire.write_byte(0x44, &mut delay);

                // Wait 750ms for 12-bit conversion to finish
                delay.delay_millis(750);

                // B. Read scratchpad for each sensor on the bus
                for (idx, sensor) in sensors.iter().enumerate() {
                    match sensor.target_read_scratchpad(&mut wire, &mut delay) {
                        Ok(scratchpad) => {
                            let raw_bits = scratchpad.temp.to_bits() as i32;
                            let temp_c_x10 = ((raw_bits * 10) / 16) as i16;

                            match idx {
                                0 => {
                                    fridge_temp = temp_c_x10;
                                    println!("  [Probe 1 - Fridge]: {}/10 C", temp_c_x10);
                                }
                                1 => {
                                    freezer_temp = temp_c_x10;
                                    println!("  [Probe 2 - Freezer]: {}/10 C", temp_c_x10);
                                }
                                2 => {
                                    ambient_temp = temp_c_x10;
                                    println!("  [Probe 3 - Ambient]: {}/10 C", temp_c_x10);
                                }
                                _ => {}
                            }
                        }
                        Err(e) => {
                            println!("  [Probe {}]: Read error: {:?}", idx + 1, e);
                            fault_code |= 1 << idx;
                        }
                    }
                }
            } else {
                println!("1-Wire: Lost presence during conversion cycle");
                fault_code = 0xFF;
                sensors.clear(); // Re-trigger discovery next loop
            }
        } else {
            fault_code = 0xFF; // All sensors disconnected
        }

        // 2. Broadcast Telemetry via ESP-NOW
        // Slot 2 = Fridge/Freezer Node
        let telemetry = DeviceTelemetry::FridgeFreezer {
            fridge_temp_c_x10: fridge_temp,
            freezer_temp_c_x10: freezer_temp,
            ambient_temp_c_x10: ambient_temp,
            battery_mv: 3820,
            sensor_fault: fault_code,
        };

        // Activity pulse: LED ON during transmit
        led.set_level(esp_hal::gpio::Level::Low);

        let uplink = UplinkPacket::new(2, mac_arr, seq, telemetry);
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

        delay.delay_millis(3000);
        seq = seq.wrapping_add(1);
    }
}
