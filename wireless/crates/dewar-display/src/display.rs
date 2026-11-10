//! High-Performance ILI9341 SPI Display Driver for 2.8" TFT (240x320)
//! Native RGB565 rendering with large clinical cryogenic font

use esp_hal::delay::Delay;
use esp_hal::gpio::Output;

pub const LCD_WIDTH: u16 = 320;
pub const LCD_HEIGHT: u16 = 240;

// RGB565 Color Palette
pub const COLOR_BLACK: u16 = 0x0000;
pub const COLOR_WHITE: u16 = 0xFFFF;
pub const COLOR_RED: u16 = 0xF800;
pub const COLOR_GREEN: u16 = 0x07E0;
pub const COLOR_CYAN: u16 = 0x07FF;
pub const COLOR_BLUE: u16 = 0x001F;
pub const COLOR_NAVY: u16 = 0x000F;
pub const COLOR_DARK_GRAY: u16 = 0x2104;
pub const COLOR_LIGHT_GRAY: u16 = 0xBDD7;
pub const COLOR_AMBER: u16 = 0xFD20;
pub const COLOR_ALARM_BG: u16 = 0x8000; // Deep dark red

pub struct Ili9341<'d> {
    sck: Output<'d>,
    mosi: Output<'d>,
    cs: Output<'d>,
    dc: Output<'d>,
    backlight: Output<'d>,
    is_on: bool,
}

impl<'d> Ili9341<'d> {
    pub fn new(
        mut sck: Output<'d>,
        mut mosi: Output<'d>,
        mut cs: Output<'d>,
        mut dc: Output<'d>,
        mut backlight: Output<'d>,
    ) -> Self {
        sck.set_low();
        mosi.set_low();
        cs.set_high();
        dc.set_high();
        backlight.set_low(); // Screen OFF by default for power saving

        Self {
            sck,
            mosi,
            cs,
            dc,
            backlight,
            is_on: false,
        }
    }

    #[inline(always)]
    fn send_byte(&mut self, byte: u8) {
        for i in 0..8 {
            if (byte >> (7 - i)) & 0x01 != 0 {
                self.mosi.set_high();
            } else {
                self.mosi.set_low();
            }
            self.sck.set_high();
            self.sck.set_low();
        }
    }

    fn write_cmd(&mut self, cmd: u8) {
        self.dc.set_low();
        self.cs.set_low();
        self.send_byte(cmd);
        self.cs.set_high();
    }

    fn write_data(&mut self, data: u8) {
        self.dc.set_high();
        self.cs.set_low();
        self.send_byte(data);
        self.cs.set_high();
    }

    fn write_data16(&mut self, val: u16) {
        self.dc.set_high();
        self.cs.set_low();
        self.send_byte((val >> 8) as u8);
        self.send_byte((val & 0xFF) as u8);
        self.cs.set_high();
    }

    pub fn backlight_on(&mut self) {
        self.backlight.set_high();
        self.is_on = true;
    }

    pub fn backlight_off(&mut self) {
        self.backlight.set_low();
        self.is_on = false;
    }

    pub fn is_backlight_on(&self) -> bool {
        self.is_on
    }

    /// Hardware initialization sequence for ILI9341V
    pub fn init(&mut self, delay: &Delay) {
        self.write_cmd(0x01); // Software Reset
        delay.delay_millis(120);

        self.write_cmd(0x11); // Sleep Out
        delay.delay_millis(120);

        // Memory Access Control (Landscape orientation, BGR order)
        self.write_cmd(0x36);
        self.write_data(0x28 | 0x80); // Landscape: MV=1, MX=1

        // Pixel Format: 16-bit / pixel (RGB565)
        self.write_cmd(0x3A);
        self.write_data(0x55);

        // Frame Rate Control: 70Hz
        self.write_cmd(0xB1);
        self.write_data(0x00);
        self.write_data(0x1B);

        // Display Function Control
        self.write_cmd(0xB6);
        self.write_data(0x0A);
        self.write_data(0xA2);

        // Power Control 1
        self.write_cmd(0xC0);
        self.write_data(0x21);

        // Power Control 2
        self.write_cmd(0xC1);
        self.write_data(0x10);

        // VCOM Control 1
        self.write_cmd(0xC5);
        self.write_data(0x31);
        self.write_data(0x3C);

        // Display ON
        self.write_cmd(0x29);
        delay.delay_millis(50);

        // Clear display to solid black
        self.clear(COLOR_BLACK);
    }

    pub fn set_window(&mut self, x0: u16, y0: u16, x1: u16, y1: u16) {
        self.write_cmd(0x2A); // Column addr
        self.write_data((x0 >> 8) as u8);
        self.write_data((x0 & 0xFF) as u8);
        self.write_data((x1 >> 8) as u8);
        self.write_data((x1 & 0xFF) as u8);

        self.write_cmd(0x2B); // Row addr
        self.write_data((y0 >> 8) as u8);
        self.write_data((y0 & 0xFF) as u8);
        self.write_data((y1 >> 8) as u8);
        self.write_data((y1 & 0xFF) as u8);

        self.write_cmd(0x2C); // Memory write
    }

    pub fn fill_rect(&mut self, x: u16, y: u16, w: u16, h: u16, color: u16) {
        if x >= LCD_WIDTH || y >= LCD_HEIGHT {
            return;
        }
        let x1 = (x + w - 1).min(LCD_WIDTH - 1);
        let y1 = (y + h - 1).min(LCD_HEIGHT - 1);
        self.set_window(x, y, x1, y1);

        let count = (x1 - x + 1) as u32 * (y1 - y + 1) as u32;
        self.dc.set_high();
        self.cs.set_low();
        let hi = (color >> 8) as u8;
        let lo = (color & 0xFF) as u8;
        for _ in 0..count {
            self.send_byte(hi);
            self.send_byte(lo);
        }
        self.cs.set_high();
    }

    pub fn clear(&mut self, color: u16) {
        self.fill_rect(0, 0, LCD_WIDTH, LCD_HEIGHT, color);
    }

    /// Renders standard 8x16 ASCII character scaled by `scale` factor
    pub fn draw_char(&mut self, x: u16, y: u16, c: char, fg: u16, bg: u16, scale: u8) {
        let glyph = get_glyph_8x16(c);
        let scale = scale.max(1) as u16;

        for row in 0..16u16 {
            let bits = glyph[row as usize];
            for col in 0..8u16 {
                let pixel_on = (bits >> (7 - col)) & 0x01 != 0;
                let color = if pixel_on { fg } else { bg };
                if scale == 1 {
                    self.set_window(x + col, y + row, x + col, y + row);
                    self.write_data16(color);
                } else {
                    self.fill_rect(x + col * scale, y + row * scale, scale, scale, color);
                }
            }
        }
    }

    /// Draw a null-terminated / string slice
    pub fn draw_str(&mut self, mut x: u16, y: u16, s: &str, fg: u16, bg: u16, scale: u8) {
        let char_w = 8 * scale.max(1) as u16;
        for c in s.chars() {
            if x + char_w > LCD_WIDTH {
                break;
            }
            self.draw_char(x, y, c, fg, bg, scale);
            x += char_w;
        }
    }

    /// High-level clinical glance screen for liquid nitrogen storage
    pub fn draw_cryo_screen(
        &mut self,
        tank_name: &str,
        temp_c_x10: i16,
        batt_mv: u16,
        tx_seq: u32,
        is_alarm: bool,
        hold_active: bool,
    ) {
        let bg_color = if is_alarm { COLOR_ALARM_BG } else { COLOR_BLACK };
        let card_color = if is_alarm { COLOR_RED } else { COLOR_NAVY };

        // 1. Header Banner
        self.fill_rect(0, 0, LCD_WIDTH, 36, card_color);
        self.draw_str(10, 8, tank_name, COLOR_WHITE, card_color, 2);

        // 2. Main Cryo Temperature Hero Display
        let (temp_str, temp_color) = format_temp_str(temp_c_x10);
        let display_color = if is_alarm { COLOR_WHITE } else { temp_color };

        // Background behind temperature
        self.fill_rect(0, 36, LCD_WIDTH, 120, bg_color);
        self.draw_str(18, 54, &temp_str, display_color, bg_color, 4);

        // Unit label
        self.draw_str(250, 72, " C", display_color, bg_color, 3);
        // Degree symbol
        self.fill_rect(242, 68, 6, 6, display_color);

        // 3. Clinical Limit & Status Bar
        let status_color = if is_alarm {
            COLOR_RED
        } else if hold_active {
            COLOR_AMBER
        } else {
            COLOR_GREEN
        };

        self.fill_rect(10, 154, LCD_WIDTH - 20, 26, status_color);
        let status_text = if is_alarm {
            "CRYO EXCURSION! > -135 C"
        } else if hold_active {
            "LN2 FILL MODE (HOLD 30M)"
        } else {
            "USP <1079> LIMIT: < -135.0 C"
        };
        self.draw_str(20, 160, status_text, COLOR_BLACK, status_color, 1);

        // 4. Footer Information (Battery, RF Sequence, Touch Button)
        self.fill_rect(0, 186, LCD_WIDTH, 54, COLOR_DARK_GRAY);

        // Battery percentage calculation (LiPo: 3.5V = 0%, 4.2V = 100%)
        let batt_pct = if batt_mv >= 4200 {
            100
        } else if batt_mv <= 3500 {
            0
        } else {
            ((batt_mv - 3500) * 100) / 700
        };

        let mut batt_buf = [0u8; 32];
        let batt_str = format_buf(
            &mut batt_buf,
            "Batt: ",
            (batt_mv / 1000) as u32,
            ".",
            ((batt_mv % 1000) / 100) as u32,
            "V (",
            batt_pct as u32,
            "%)",
        );
        self.draw_str(12, 196, batt_str, COLOR_LIGHT_GRAY, COLOR_DARK_GRAY, 1);

        let mut rf_buf = [0u8; 32];
        let rf_str = format_buf(&mut rf_buf, "ESP-NOW: TX #", tx_seq, " [OK]", 0, "", 0, "");
        self.draw_str(12, 214, rf_str, COLOR_LIGHT_GRAY, COLOR_DARK_GRAY, 1);

        // Interactive Touch Button on right side of footer
        let btn_color = if hold_active { COLOR_AMBER } else { COLOR_BLUE };
        self.fill_rect(205, 192, 105, 42, btn_color);
        self.draw_str(212, 204, "FILL HOLD", COLOR_WHITE, btn_color, 1);
    }
}

/// Helper to format temperature string and clinical color
fn format_temp_str(temp_c_x10: i16) -> (heapless::String<16>, u16) {
    let mut s = heapless::String::<16>::new();

    if temp_c_x10 <= -9000 {
        let _ = s.push_str("FAULT");
        return (s, COLOR_AMBER);
    }

    let is_neg = temp_c_x10 < 0;
    let abs_val = temp_c_x10.abs();
    let whole = abs_val / 10;
    let frac = abs_val % 10;

    let mut buf = [0u8; 16];
    let mut idx = 0;

    if is_neg {
        buf[idx] = b'-';
        idx += 1;
    }

    // Number to string
    let mut digits = [0u8; 6];
    let mut d_idx = 0;
    let mut n = whole;
    if n == 0 {
        digits[0] = b'0';
        d_idx = 1;
    } else {
        while n > 0 {
            digits[d_idx] = b'0' + (n % 10) as u8;
            n /= 10;
            d_idx += 1;
        }
    }

    for i in (0..d_idx).rev() {
        buf[idx] = digits[i];
        idx += 1;
    }

    buf[idx] = b'.';
    idx += 1;
    buf[idx] = b'0' + frac as u8;
    idx += 1;

    let str_slice = core::str::from_utf8(&buf[..idx]).unwrap_or("-196.0");
    let _ = s.push_str(str_slice);

    let color = if temp_c_x10 > -1350 {
        COLOR_RED
    } else {
        COLOR_CYAN
    };

    (s, color)
}

fn format_buf<'a>(
    buf: &'a mut [u8],
    p1: &str,
    v1: u32,
    p2: &str,
    v2: u32,
    p3: &str,
    v3: u32,
    p4: &str,
) -> &'a str {
    let mut idx = 0;

    let copy_str = |b: &mut [u8], i: &mut usize, s: &str| {
        for byte in s.bytes() {
            if *i < b.len() {
                b[*i] = byte;
                *i += 1;
            }
        }
    };

    let copy_num = |b: &mut [u8], i: &mut usize, mut num: u32| {
        if num == 0 {
            if *i < b.len() {
                b[*i] = b'0';
                *i += 1;
            }
            return;
        }
        let mut d = [0u8; 10];
        let mut count = 0;
        while num > 0 {
            d[count] = b'0' + (num % 10) as u8;
            num /= 10;
            count += 1;
        }
        for k in (0..count).rev() {
            if *i < b.len() {
                b[*i] = d[k];
                *i += 1;
            }
        }
    };

    copy_str(buf, &mut idx, p1);
    copy_num(buf, &mut idx, v1);
    copy_str(buf, &mut idx, p2);
    copy_num(buf, &mut idx, v2);
    copy_str(buf, &mut idx, p3);
    copy_num(buf, &mut idx, v3);
    copy_str(buf, &mut idx, p4);

    core::str::from_utf8(&buf[..idx]).unwrap_or("")
}

/// Basic 8x16 ASCII Font table for digits, punctuation, and uppercase
fn get_glyph_8x16(c: char) -> [u8; 16] {
    match c {
        '0' => [0x3C,0x66,0xC3,0xC3,0xC7,0xCF,0xDF,0xDB,0xFB,0xF3,0xE3,0xC3,0xC3,0x66,0x3C,0x00],
        '1' => [0x18,0x38,0x78,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x7E,0x00],
        '2' => [0x3C,0x66,0xC3,0x03,0x06,0x0C,0x18,0x30,0x60,0xC0,0xC0,0xC0,0xC3,0x66,0xFF,0x00],
        '3' => [0x3C,0x66,0xC3,0x03,0x06,0x1C,0x06,0x03,0x03,0x03,0x03,0xC3,0xC3,0x66,0x3C,0x00],
        '4' => [0x06,0x0E,0x1E,0x36,0x66,0xC6,0xC6,0xC6,0xFF,0x06,0x06,0x06,0x06,0x06,0x0F,0x00],
        '5' => [0x7F,0x60,0x60,0x60,0x7C,0x66,0x03,0x03,0x03,0x03,0x03,0xC3,0xC3,0x66,0x3C,0x00],
        '6' => [0x1C,0x30,0x60,0x60,0x7C,0x66,0xC3,0xC3,0xC3,0xC3,0xC3,0xC3,0x66,0x3C,0x18,0x00],
        '7' => [0xFF,0xC3,0x03,0x06,0x0C,0x18,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x00],
        '8' => [0x3C,0x66,0xC3,0xC3,0x66,0x3C,0x66,0xC3,0xC3,0xC3,0xC3,0xC3,0x66,0x3C,0x18,0x00],
        '9' => [0x3C,0x66,0xC3,0xC3,0xC3,0xC3,0xC3,0x67,0x3F,0x03,0x06,0x0C,0x18,0x30,0x60,0x00],
        '-' => [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x7E,0x7E,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        '.' => [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x18,0x18,0x00,0x00],
        ':' => [0x00,0x00,0x00,0x18,0x18,0x00,0x00,0x00,0x00,0x00,0x18,0x18,0x00,0x00,0x00,0x00],
        '[' => [0x3C,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x30,0x3C,0x00],
        ']' => [0x3C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x0C,0x3C,0x00],
        '(' => [0x0E,0x1C,0x38,0x38,0x38,0x70,0x70,0x70,0x70,0x70,0x38,0x38,0x38,0x1C,0x0E,0x00],
        ')' => [0x70,0x38,0x1C,0x1C,0x1C,0x0E,0x0E,0x0E,0x0E,0x0E,0x1C,0x1C,0x1C,0x38,0x70,0x00],
        '<' => [0x00,0x06,0x0C,0x18,0x30,0x60,0xC0,0x60,0x30,0x18,0x0C,0x06,0x00,0x00,0x00,0x00],
        '>' => [0x00,0x60,0x30,0x18,0x0C,0x06,0x03,0x06,0x0C,0x18,0x30,0x60,0x00,0x00,0x00,0x00],
        '%' => [0x00,0x63,0x66,0x0C,0x18,0x30,0x60,0xC6,0x86,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        '#' => [0x24,0x24,0xFF,0x24,0x24,0x24,0xFF,0x24,0x24,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        ' ' => [0x00; 16],
        'A' => [0x18,0x3C,0x66,0xC3,0xC3,0xC3,0xFF,0xC3,0xC3,0xC3,0xC3,0xC3,0xC3,0x00,0x00,0x00],
        'B' => [0xFC,0x66,0x66,0x66,0x7C,0x66,0x66,0x66,0x66,0x66,0xFC,0x00,0x00,0x00,0x00,0x00],
        'C' => [0x3C,0x66,0xC3,0xC0,0xC0,0xC0,0xC0,0xC0,0xC0,0xC3,0x66,0x3C,0x00,0x00,0x00,0x00],
        'D' => [0xF8,0x6C,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x6C,0xF8,0x00,0x00,0x00,0x00,0x00],
        'E' => [0xFE,0x62,0x60,0x64,0x7C,0x64,0x60,0x60,0x62,0xFE,0x00,0x00,0x00,0x00,0x00,0x00],
        'F' => [0xFE,0x62,0x60,0x64,0x7C,0x64,0x60,0x60,0x60,0xF0,0x00,0x00,0x00,0x00,0x00,0x00],
        'H' => [0xC3,0xC3,0xC3,0xC3,0xFF,0xC3,0xC3,0xC3,0xC3,0xC3,0x00,0x00,0x00,0x00,0x00,0x00],
        'I' => [0x7E,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x7E,0x00,0x00,0x00,0x00,0x00,0x00],
        'K' => [0xC3,0xC6,0xCC,0xD8,0xF0,0xD8,0xCC,0xC6,0xC3,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'L' => [0xF0,0x60,0x60,0x60,0x60,0x60,0x60,0x62,0x66,0xFE,0x00,0x00,0x00,0x00,0x00,0x00],
        'M' => [0xC3,0xE7,0xFF,0xDB,0xC3,0xC3,0xC3,0xC3,0xC3,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'N' => [0xC3,0xE3,0xF3,0xDB,0xCF,0xC7,0xC3,0xC3,0xC3,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'O' => [0x3C,0x66,0xC3,0xC3,0xC3,0xC3,0xC3,0x66,0x3C,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'P' => [0xFC,0x66,0x66,0x66,0x7C,0x60,0x60,0x60,0xF0,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'R' => [0xFC,0x66,0x66,0x66,0x7C,0x6C,0x66,0x63,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'S' => [0x3C,0x66,0xC0,0xC0,0x78,0x0E,0x03,0xC3,0x66,0x3C,0x00,0x00,0x00,0x00,0x00,0x00],
        'T' => [0x7E,0x5A,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'U' => [0xC3,0xC3,0xC3,0xC3,0xC3,0xC3,0xC3,0x66,0x3C,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'V' => [0xC3,0xC3,0xC3,0xC3,0x66,0x66,0x3C,0x18,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'W' => [0xC3,0xC3,0xC3,0xC3,0xDB,0xFF,0xE7,0xC3,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        'X' => [0xC3,0x66,0x3C,0x18,0x3C,0x66,0xC3,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
        _ => [0x00,0x00,0x7E,0x42,0x42,0x42,0x7E,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00], // Box fallback
    }
}
