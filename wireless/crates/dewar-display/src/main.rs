#![no_std]
#![no_main]

extern crate alloc;

mod display;
mod kiosk_font;
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
use wireless_protocol::{DeviceTelemetry, DownlinkCommand, DownlinkPacket, UplinkPacket, PROTOCOL_MAGIC, PROTOCOL_VERSION};

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

    // 3. Initialize ILI9341 Display on hardware SPI2 (40 MHz)
    // - TFT_SCK:  GPIO 12
    // - TFT_MOSI: GPIO 11
    // - TFT_CS:   GPIO 10
    // - TFT_DC:   GPIO 46
    // - TFT_BL:   GPIO 45 (Backlight)
    use esp_hal::time::Rate;
    let spi = esp_hal::spi::master::Spi::new(
        peripherals.SPI2,
        esp_hal::spi::master::Config::default().with_frequency(Rate::from_mhz(40)),
    )
    .unwrap()
    .with_sck(peripherals.GPIO12)
    .with_mosi(peripherals.GPIO11);

    let tft_cs = esp_hal::gpio::Output::new(peripherals.GPIO10, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());
    let tft_dc = esp_hal::gpio::Output::new(peripherals.GPIO46, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());
    let tft_bl = esp_hal::gpio::Output::new(peripherals.GPIO45, esp_hal::gpio::Level::Low, esp_hal::gpio::OutputConfig::default());

    let mut screen = display::Ili9341::new(spi, tft_cs, tft_dc, tft_bl);
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

    // 6. Initialize MAX31855 Thermocouple Interface (IO2: SCK, IO14: MISO, IO21: CS)
    let max_sck = esp_hal::gpio::Output::new(peripherals.GPIO2, esp_hal::gpio::Level::Low, esp_hal::gpio::OutputConfig::default());
    let max_cs = esp_hal::gpio::Output::new(peripherals.GPIO21, esp_hal::gpio::Level::High, esp_hal::gpio::OutputConfig::default());
    let max_miso = esp_hal::gpio::Input::new(peripherals.GPIO14, esp_hal::gpio::InputConfig::default());
    let mut max31855 = max31855::Max31855::new(max_sck, max_cs, max_miso);

    let initial_reading = max31855.read(&delay);
    let mut current_temp_c_x10: i16 = if initial_reading.fault == max31855::FaultType::None {
        initial_reading.temp_c_x10
    } else {
        -9999
    };
    let mut sensor_fault_code: u8 = initial_reading.fault as u8;
    let mut is_alarm: bool = current_temp_c_x10 > -1350 && current_temp_c_x10 != -9999;
    let mut prev_alarm: bool = is_alarm;

    // Boot splash screen
    screen.backlight_on();
    screen.clear(display::COLOR_BG_APP);
    screen.draw_kiosk_str(20, 70, "LabSCADA Cryo Node", &kiosk_font::FONT_INTER_18, display::COLOR_TEXT_MAIN, display::COLOR_BG_APP);
    screen.draw_kiosk_str(20, 105, "2.8\" IPS Touch Display", &kiosk_font::FONT_INTER_14, display::COLOR_CRYO_CYAN, display::COLOR_BG_APP);
    screen.draw_kiosk_str(20, 130, "ESP-NOW Telemetry Ready", &kiosk_font::FONT_INTER_14, display::COLOR_STATUS_GREEN, display::COLOR_BG_APP);
    delay.delay_millis(1500);

    // Transition directly to Dewar Monitoring screen
    let pin_mv: u16 = adc1.read_blocking(&mut batt_pin);
    let mut latest_batt: u16 = pin_mv * 2;
    let mut hold_timer: u32 = 0;
    let mut seq: u32 = 1;
    screen.draw_cryo_screen("Dewar 1 (Embryos)", current_temp_c_x10, latest_batt, seq, is_alarm, hold_timer > 0);
    println!("[DISPLAY] Active Dewar monitoring initialized (Initial Temp: {} dC, Batt: {} mV, Fault: {})",
        current_temp_c_x10, latest_batt, sensor_fault_code);

    let mut tx_buf = [0u8; 64];
    let mut report_counter: u32 = 0;
    let mut sensor_read_counter: u32 = 0;
    let mut screen_timer: u32 = DISPLAY_TIMEOUT_TICKS; // Stays on for 15 seconds on battery
    let mut debounce_ticks: u32 = 0;
    let usb_regs = esp_hal::peripherals::USB_DEVICE::regs();
    let mut last_sof: u16 = 0;
    let mut is_usb_connected: bool = false;

    loop {
        if debounce_ticks > 0 {
            debounce_ticks -= 1;
        }

        // A. Periodic Temperature, Battery & USB Measurement (every 500ms / 50 ticks)
        sensor_read_counter += 1;
        if sensor_read_counter >= 50 {
            sensor_read_counter = 0;

            // Check hardware USB Start-Of-Frame (SOF) packet counter
            // USB Host sends 1 frame every 1ms; if counter changes, USB data connection is live!
            let cur_sof = usb_regs.fram_num().read().sof_frame_index().bits();
            let is_usb_data = cur_sof != last_sof;
            last_sof = cur_sof;

            // Read Battery ADC (GPIO 9 has 2:1 onboard resistor divider)
            let pin_mv: u16 = adc1.read_blocking(&mut batt_pin);
            let new_batt = pin_mv * 2;
            let batt_changed = (new_batt / 50) != (latest_batt / 50); // Redraw if shifted by >50mV
            latest_batt = new_batt;

            // Unit is USB-powered if rail >= 4040mV (charge/float rail is ~4.07V-4.2V) or USB SOF active
            is_usb_connected = latest_batt >= 4040 || is_usb_data;

            let reading = max31855.read(&delay);
            let (new_temp, new_fault) = if reading.fault == max31855::FaultType::None {
                (reading.temp_c_x10, 0u8)
            } else {
                (-9999, reading.fault as u8)
            };

            let temp_changed = new_temp != current_temp_c_x10 || new_fault != sensor_fault_code;
            current_temp_c_x10 = new_temp;
            sensor_fault_code = new_fault;

            is_alarm = current_temp_c_x10 > -1350 && hold_timer == 0 && current_temp_c_x10 != -9999;

            // If entering alarm condition for the first time, wake screen immediately
            if is_alarm && !prev_alarm {
                println!("[ALARM] >>> CRYO EXCURSION DETECTED: {} dC <<<", current_temp_c_x10);
                screen.backlight_on();
                screen_timer = DISPLAY_TIMEOUT_TICKS;
            }
            prev_alarm = is_alarm;

            // If screen is on and data changed, redraw screen
            if screen.is_backlight_on() && (temp_changed || batt_changed) {
                screen.draw_cryo_screen("Dewar 1 (Embryos)", current_temp_c_x10, latest_batt, seq, is_alarm, hold_timer > 0);
            }
        }

        // B. Check Touch
        if touch.is_touch_active() {
            let pt = touch.read_touch(&delay);

            if !screen.is_backlight_on() {
                // Wake screen upon touch
                println!("[DISPLAY] >>> WAKING BACKLIGHT ON <<<");
                screen.backlight_on();
                screen_timer = DISPLAY_TIMEOUT_TICKS;
                screen.draw_cryo_screen("Dewar 1 (Embryos)", current_temp_c_x10, latest_batt, seq, is_alarm, hold_timer > 0);
                debounce_ticks = 25; // 250ms debounce
            } else {
                // Screen is already awake: reset sleep timer and check button
                screen_timer = DISPLAY_TIMEOUT_TICKS;

                // Check tap on "ACCESS MODE" button (lower right region)
                if pt.is_touched && debounce_ticks == 0 {
                    debounce_ticks = 25; // 250ms debounce across any tap
                    println!("[TOUCH] Tap at X={}, Y={}", pt.x, pt.y);
                    // Match the right side of the screen or bottom quadrant
                    if pt.x >= 180 && pt.y >= 160 {
                        if hold_timer == 0 {
                            hold_timer = CRYO_HOLD_TICKS;
                            println!("[+] Access Mode ACTIVATED (Alarms paused 30 min)");
                        } else {
                            hold_timer = 0;
                            println!("[-] Access Mode CANCELLED (Normal monitoring resumed)");
                        }
                        is_alarm = current_temp_c_x10 > -1350 && hold_timer == 0 && current_temp_c_x10 != -9999;
                        // Instantly re-render screen with updated button and banner color
                        screen.draw_cryo_screen("Dewar 1 (Embryos)", current_temp_c_x10, latest_batt, seq, is_alarm, hold_timer > 0);
                        // Trigger immediate telemetry uplink so Bridge & PLC see hold state instantly
                        report_counter = REPORT_INTERVAL_TICKS;
                    }
                }
            }
        }

        // C. Decrement Hold Timer
        if hold_timer > 0 {
            hold_timer -= 1;
        }

        // D. Screen Inactivity / USB Power Management
        // If USB is connected (rail >= 4040mV or USB host SOF), screen stays awake permanently.
        // On battery power (< 4040mV), screen times out after 15 seconds to conserve LiPo.
        if is_usb_connected {
            screen_timer = DISPLAY_TIMEOUT_TICKS;
            if !screen.is_backlight_on() {
                screen.backlight_on();
            }
        } else if screen_timer > 0 {
            screen_timer -= 1;
            if screen_timer == 0 {
                println!("[DISPLAY] 15s timeout reached (Battery mode) -> Backlight OFF");
                screen.backlight_off();
            }
        }

        // E. Periodic Measurement and ESP-NOW Transmission (every 20s)
        report_counter += 1;
        if report_counter >= REPORT_INTERVAL_TICKS {
            report_counter = 0;

            // Read Battery ADC (GPIO 9 has 2:1 onboard resistor divider)
            let pin_mv: u16 = adc1.read_blocking(&mut batt_pin);
            latest_batt = pin_mv * 2; // Scaled by 2:1 onboard divider

            println!("TELEMETRY: Temp={}dC, Fault={}, Batt={}mV, AccessMode={}, INT_low={}",
                current_temp_c_x10, sensor_fault_code, latest_batt, hold_timer > 0, touch.is_pin_low());

            // Build Telemetry Packet
            let telemetry = DeviceTelemetry::Dewar {
                temp_c_x10: current_temp_c_x10,
                battery_mv: latest_batt,
                sensor_fault: sensor_fault_code,
                access_mode: hold_timer > 0,
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
                screen.draw_cryo_screen("Dewar 1 (Embryos)", current_temp_c_x10, latest_batt, seq, is_alarm, hold_timer > 0);
            }
        }

        // Loop tick: 10ms for snappy touch detection
        delay.delay_millis(10);
    }
}
