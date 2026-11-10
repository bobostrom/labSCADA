#![no_std]
#![no_main]

extern crate alloc;

mod display;
mod max31855;
mod max31865;
mod touch;

use esp_backtrace as _;
use esp_println::println;
use esp_hal::efuse::{self, InterfaceMacAddress};
use esp_hal::timer::timg::TimerGroup;
use esp_hal::analog::adc::{Adc, AdcConfig, Attenuation, AdcCalCurve};
use esp_hal::peripherals::ADC1;
use esp_radio::esp_now::BROADCAST_ADDRESS;
use wireless_protocol::{DeviceTelemetry, UplinkPacket, PROTOCOL_MAGIC, PROTOCOL_VERSION};

esp_bootloader_esp_idf::esp_app_desc!();

// 10ms loop tick
// 20-second background reporting interval (2000 * 10ms = 20,000ms)
const REPORT_INTERVAL_TICKS: u32 = 2000;
// Screen stays on for 15 seconds after touch (1500 * 10ms = 15,000ms)
const DISPLAY_TIMEOUT_TICKS: u32 = 1500;
// Cryo Hold duration: 30 minutes (180,000 ticks)
const CRYO_HOLD_TICKS: u32 = 180000;

#[esp_hal::main]
fn main() -> ! {
    esp_alloc::heap_allocator!(size: 128 * 1024);

    let peripherals = esp_hal::init(esp_hal::Config::default());
    let delay = esp_hal::delay::Delay::new();

    println!("==================================================");
    println!("  LabSCADA Smart Cryo Dewar Touch Node (ESP32-S3) ");
    println!("  Hardware: 2.8\" IPS Touch Display + MAX31865     ");
    println!("  Mode: Bench Test (-140.0 C Simulated Baseline)  ");
    println!("==================================================");

    // 1. Initialize RTOS timer required by esp-radio
    let timg0 = TimerGroup::new(peripherals.TIMG0);
    esp_rtos::start(timg0.timer0, peripherals.FROM_CPU_INTR0);

    // 2. Initialize WiFi and ESP-NOW
    let controller = esp_radio::wifi::WifiController::new(peripherals.WIFI, Default::default()).unwrap();
    let esp_now = controller.esp_now();
    let (_manager, mut sender, _receiver) = esp_now.split();

    // Read MAC address
    let mac = efuse::interface_mac_address(InterfaceMacAddress::Station);
    let mac_bytes = mac.as_bytes();
    let mut mac_arr = [0u8; 6];
    mac_arr.copy_from_slice(mac_bytes);
    println!("MAC: {:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}",
        mac_arr[0], mac_arr[1], mac_arr[2], mac_arr[3], mac_arr[4], mac_arr[5]);

    // 3. Initialize ILI9341 Display on hardware SPI pins
    // - TFT_SCK:  GPIO 12
    // - TFT_MOSI: GPIO 11
    // - TFT_CS:   GPIO 10
    // - TFT_DC:   GPIO 46
    // - TFT_BL:   GPIO 45 (Backlight)
    let tft_sck = esp_hal::gpio::Output::new(peripherals.GPIO12, esp_hal::gpio::Level::Low, esp_hal::gpio::OutputConfig::default());
    let tft_mosi = esp_hal::gpio::Output::new(peripherals.GPIO11, esp_hal::gpio::Level::Low, esp_hal::gpio::OutputConfig::default());
    let tft_cs = esp_hal::gpio::Output::new(peripherals.GPIO10, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());
    let tft_dc = esp_hal::gpio::Output::new(peripherals.GPIO46, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());
    let tft_bl = esp_hal::gpio::Output::new(peripherals.GPIO45, esp_hal::gpio::Level::Low, esp_hal::gpio::OutputConfig::default());

    let mut screen = display::Ili9341::new(tft_sck, tft_mosi, tft_cs, tft_dc, tft_bl);
    screen.init(&delay);

    // 4. Initialize FT6336G Capacitive Touch
    // - TP_SCL: GPIO 15
    // - TP_SDA: GPIO 16
    // - TP_INT: GPIO 17 (Active Low interrupt)
    // - TP_RST: GPIO 18 (Active Low hardware reset)
    let tp_scl = esp_hal::gpio::Output::new(peripherals.GPIO15, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());
    let tp_sda = esp_hal::gpio::Flex::new(peripherals.GPIO16);
    let tp_int = esp_hal::gpio::Input::new(peripherals.GPIO17, esp_hal::gpio::InputConfig::default().with_pull(esp_hal::gpio::Pull::Up));
    let tp_rst = esp_hal::gpio::Output::new(peripherals.GPIO18, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());

    let mut touch = touch::Ft6336::new(tp_scl, tp_sda, tp_int, tp_rst, &delay);

    // 5. Battery ADC on internal GPIO 9 (BAT_ADC)
    let mut adc1_config = AdcConfig::new();
    let mut batt_pin = adc1_config.enable_pin_with_cal::<_, AdcCalCurve<ADC1>>(
        peripherals.GPIO9,
        Attenuation::_11dB,
    );
    let mut adc1 = Adc::new(peripherals.ADC1, adc1_config);

    // Assumed cryogenic temperature per user request (-140.0 C)
    let assumed_temp_c_x10: i16 = -1400;
    let is_alarm: bool = false; // -140.0 C is safely below the -135.0 C alarm threshold

    // Boot splash for 3 seconds then screen powers down
    screen.backlight_on();
    screen.clear(display::COLOR_BG_APP);
    screen.draw_str(20, 80, "LabSCADA DEWAR NODE", display::COLOR_TEXT_MAIN, display::COLOR_BG_APP, 2);
    screen.draw_str(20, 120, "2.8\" Touch Display", display::COLOR_CRYO_CYAN, display::COLOR_BG_APP, 1);
    screen.draw_str(20, 140, "ESP-NOW Telemetry Ready", display::COLOR_STATUS_GREEN, display::COLOR_BG_APP, 1);
    delay.delay_millis(3000);
    screen.backlight_off();
    println!("[DISPLAY] Boot splash complete -> Backlight OFF (touch glass to wake)");

    let mut tx_buf = [0u8; 64];
    let mut seq: u32 = 1;
    let mut report_counter: u32 = 0;
    let mut screen_timer: u32 = 0;
    let mut hold_timer: u32 = 0;
    let mut latest_batt: u16 = 4100;
    let mut debounce_ticks: u32 = 0;

    loop {
        if debounce_ticks > 0 {
            debounce_ticks -= 1;
        }

        // A. Check Touch
        if touch.is_touch_active() {
            let pt = touch.read_touch(&delay);

            if !screen.is_backlight_on() {
                // Wake screen upon first touch
                println!("[DISPLAY] >>> WAKING BACKLIGHT ON <<<");
                screen.backlight_on();
                screen_timer = DISPLAY_TIMEOUT_TICKS;
                screen.draw_cryo_screen("Dewar 1 (Embryos)", assumed_temp_c_x10, latest_batt, seq, is_alarm, hold_timer > 0);
                debounce_ticks = 25; // 250ms debounce
            } else {
                // Screen is already awake: reset sleep timer and check button
                screen_timer = DISPLAY_TIMEOUT_TICKS;

                // Check tap on "FILL HOLD" button (lower right region)
                if pt.is_touched && debounce_ticks == 0 {
                    println!("[TOUCH] Tap at X={}, Y={}", pt.x, pt.y);
                    // Match the right side of the screen or bottom quadrant
                    if pt.x >= 180 && pt.y >= 160 {
                        debounce_ticks = 35; // 350ms debounce
                        if hold_timer == 0 {
                            hold_timer = CRYO_HOLD_TICKS;
                            println!("[+] Tank Fill Hold ACTIVATED (30 minutes hold)");
                        } else {
                            hold_timer = 0;
                            println!("[-] Tank Fill Hold CANCELLED (Normal monitoring resumed)");
                        }
                        // Instantly re-render screen with updated button and banner color
                        screen.draw_cryo_screen("Dewar 1 (Embryos)", assumed_temp_c_x10, latest_batt, seq, is_alarm, hold_timer > 0);
                    }
                }
            }
        }

        // B. Decrement Hold Timer
        if hold_timer > 0 {
            hold_timer -= 1;
        }

        // C. Decrement Screen Inactivity Timer
        if screen_timer > 0 && !is_alarm {
            screen_timer -= 1;
            if screen_timer == 0 {
                println!("[DISPLAY] 15s timeout reached -> Backlight OFF");
                screen.backlight_off();
            }
        }

        // D. Periodic Measurement and ESP-NOW Transmission (every 20s)
        report_counter += 1;
        if report_counter >= REPORT_INTERVAL_TICKS {
            report_counter = 0;

            // Read Battery ADC (GPIO 9 has 2:1 onboard resistor divider)
            let pin_mv: u16 = adc1.read_blocking(&mut batt_pin);
            latest_batt = pin_mv * 2; // Scaled by 2:1 onboard divider

            println!("TELEMETRY: Temp=-140.0 C (Assumed), Batt={}mV, FillHold={}, INT_low={}",
                latest_batt, hold_timer > 0, touch.is_touch_active());

            // Build Telemetry Packet
            let telemetry = DeviceTelemetry::Dewar {
                temp_c_x10: assumed_temp_c_x10, // -1400 = -140.0 C
                battery_mv: latest_batt,
                sensor_fault: 0, // Clean status
            };

            let packet = UplinkPacket {
                magic: PROTOCOL_MAGIC,
                version: PROTOCOL_VERSION,
                slot_id: 1, // Slot 1 = Dewar 1
                mac_address: mac_arr,
                sequence_number: seq,
                telemetry,
            };

            seq = seq.wrapping_add(1);

            // Send over ESP-NOW
            if let Ok(encoded) = postcard::to_slice(&packet, &mut tx_buf) {
                let _ = sender.send(&BROADCAST_ADDRESS, encoded);
            }

            // Refresh display if awake
            if screen.is_backlight_on() {
                screen.draw_cryo_screen("Dewar 1 (Embryos)", assumed_temp_c_x10, latest_batt, seq, is_alarm, hold_timer > 0);
            }
        }

        // Loop tick: 10ms for snappy touch detection
        delay.delay_millis(10);
    }
}
