//! High-Performance Cleanroom SCADA Dashboard Display Driver
//! Theme: Alaskan Deep Navy & Cryo Glacier (#03141f / #00e5ff)
//! Typography: Precision Vector 7-Segment Cryo LED + Clean Status Badges

use esp_hal::delay::Delay;
use esp_hal::gpio::Output;

pub const LCD_WIDTH: u16 = 320;
pub const LCD_HEIGHT: u16 = 240;

// ==============================================================================
// Dashboard Exact Color Palette (RGB565)
// ==============================================================================
pub const COLOR_BG_APP: u16       = 0x00A3; // #03141f - Deep Alaskan Navy
pub const COLOR_BG_CARD: u16      = 0x0106; // #041b2b - Marine Blue Card
pub const COLOR_BG_CARD_SUB: u16  = 0x0084; // #02121e - Sub-panel dark
pub const COLOR_BORDER_SUBTLE: u16 = 0x11F1; // #133D56 - Subtle glacier border
pub const COLOR_BORDER_ACTIVE: u16 = 0x03F4; // #037EAB - Brand Glacier border
pub const COLOR_CRYO_CYAN: u16    = 0x071F; // #00E5FF - Cryo Cyan / Glacier Hero
pub const COLOR_SEG_DIM: u16      = 0x0906; // #082234 - Faint unlit segment ghost
pub const COLOR_TEXT_MAIN: u16    = 0xFFFF; // #F0F8FF - Alice Ice White
pub const COLOR_TEXT_MUTED: u16   = 0x8D16; // #8BA2B5 - Slate Steel
pub const COLOR_STATUS_GREEN: u16 = 0x15D0; // #10B981 - Emerald Green Normal
pub const COLOR_STATUS_AMBER: u16 = 0xF4E1; // #F59E0B - Gold/Amber Warning & Hold
pub const COLOR_STATUS_RED: u16   = 0xEA28; // #EF4444 - Cryo Excursion Emergency
pub const COLOR_BTN_BLUE: u16     = 0x0438; // #0284C7 - Kiosk Action Button Sky Blue

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
        backlight.set_low();

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

    /// Hardware initialization for ILI9341V
    pub fn init(&mut self, delay: &Delay) {
        self.write_cmd(0x01); // Software Reset
        delay.delay_millis(120);

        self.write_cmd(0x11); // Sleep Out
        delay.delay_millis(120);

        // Memory Access Control (Landscape orientation, BGR order)
        self.write_cmd(0x36);
        self.write_data(0x28 | 0x80);

        // Pixel Format: 16-bit / pixel (RGB565)
        self.write_cmd(0x3A);
        self.write_data(0x55);

        // Frame Rate Control: 70Hz
        self.write_cmd(0xB1);
        self.write_data(0x00);
        self.write_data(0x1B);

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

        self.clear(COLOR_BG_APP);
    }

    pub fn set_window(&mut self, x0: u16, y0: u16, x1: u16, y1: u16) {
        self.write_cmd(0x2A);
        self.write_data((x0 >> 8) as u8);
        self.write_data((x0 & 0xFF) as u8);
        self.write_data((x1 >> 8) as u8);
        self.write_data((x1 & 0xFF) as u8);

        self.write_cmd(0x2B);
        self.write_data((y0 >> 8) as u8);
        self.write_data((y0 & 0xFF) as u8);
        self.write_data((y1 >> 8) as u8);
        self.write_data((y1 & 0xFF) as u8);

        self.write_cmd(0x2C);
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

    // ==============================================================================
    // Geometric 7-Segment Digital Cryo Controller Font Engine
    // Digit size: 36px wide, 68px tall. Zero pixelation.
    // ==============================================================================
    pub fn draw_7seg_digit(&mut self, x: u16, y: u16, digit: char, on_color: u16, off_color: u16) {
        // Segment bitmask: [A, B, C, D, E, F, G]
        let mask: u8 = match digit {
            '0' => 0b0011_1111,
            '1' => 0b0000_0110,
            '2' => 0b0101_1011,
            '3' => 0b0100_1111,
            '4' => 0b0110_0110,
            '5' => 0b0110_1101,
            '6' => 0b0111_1101,
            '7' => 0b0000_0111,
            '8' => 0b0111_1111,
            '9' => 0b0110_1111,
            '-' => 0b0100_0000,
            _   => 0b0000_0000,
        };

        let col_a = if (mask & 0x01) != 0 { on_color } else { off_color };
        let col_b = if (mask & 0x02) != 0 { on_color } else { off_color };
        let col_c = if (mask & 0x04) != 0 { on_color } else { off_color };
        let col_d = if (mask & 0x08) != 0 { on_color } else { off_color };
        let col_e = if (mask & 0x10) != 0 { on_color } else { off_color };
        let col_f = if (mask & 0x20) != 0 { on_color } else { off_color };
        let col_g = if (mask & 0x40) != 0 { on_color } else { off_color };

        let t: u16 = 6;  // Thickness
        let l: u16 = 24; // Horizontal segment length
        let h: u16 = 25; // Vertical segment height

        // Segment A: Top horizontal
        self.fill_rect(x + t, y, l, t, col_a);
        // Segment B: Top-right vertical
        self.fill_rect(x + t + l, y + t, t, h, col_b);
        // Segment C: Bottom-right vertical
        self.fill_rect(x + t + l, y + (2 * t) + h, t, h, col_c);
        // Segment D: Bottom horizontal
        self.fill_rect(x + t, y + (2 * t) + (2 * h), l, t, col_d);
        // Segment E: Bottom-left vertical
        self.fill_rect(x, y + (2 * t) + h, t, h, col_e);
        // Segment F: Top-left vertical
        self.fill_rect(x, y + t, t, h, col_f);
        // Segment G: Middle horizontal
        self.fill_rect(x + t, y + t + h, l, t, col_g);
    }

    /// Decimal point for 7-segment display
    pub fn draw_7seg_dp(&mut self, x: u16, y: u16, on_color: u16) {
        self.fill_rect(x, y + 58, 8, 8, on_color);
    }

    // ==============================================================================
    // Clean Monospace Typography Engine (Inter / Cleanroom Terminal style)
    // 6x10 font scaled cleanly 1x or 2x
    // ==============================================================================
    pub fn draw_char(&mut self, x: u16, y: u16, c: char, fg: u16, bg: u16, scale: u8) {
        let glyph = get_glyph_6x10(c);
        let s = scale.max(1) as u16;

        for row in 0..10u16 {
            let bits = glyph[row as usize];
            for col in 0..6u16 {
                let pixel_on = (bits >> (5 - col)) & 0x01 != 0;
                let color = if pixel_on { fg } else { bg };
                if s == 1 {
                    self.set_window(x + col, y + row, x + col, y + row);
                    self.dc.set_high();
                    self.cs.set_low();
                    self.send_byte((color >> 8) as u8);
                    self.send_byte((color & 0xFF) as u8);
                    self.cs.set_high();
                } else {
                    self.fill_rect(x + col * s, y + row * s, s, s, color);
                }
            }
        }
    }

    pub fn draw_str(&mut self, mut x: u16, y: u16, s: &str, fg: u16, bg: u16, scale: u8) {
        let char_w = 6 * scale.max(1) as u16 + 1;
        for c in s.chars() {
            if x + char_w > LCD_WIDTH {
                break;
            }
            self.draw_char(x, y, c, fg, bg, scale);
            x += char_w;
        }
    }

    // ==============================================================================
    // Full Dashboard Kiosk Screen Renderer
    // ==============================================================================
    pub fn draw_cryo_screen(
        &mut self,
        tank_name: &str,
        temp_c_x10: i16,
        batt_mv: u16,
        tx_seq: u32,
        is_alarm: bool,
        hold_active: bool,
    ) {
        // App Canvas Background
        let card_border = if is_alarm {
            COLOR_STATUS_RED
        } else if hold_active {
            COLOR_STATUS_AMBER
        } else {
            COLOR_CRYO_CYAN
        };

        // 1. Kiosk Card Wrapper (Border & Card Header)
        // Outer background
        self.fill_rect(0, 0, LCD_WIDTH, 6, COLOR_BG_APP);
        self.fill_rect(0, 0, 6, LCD_HEIGHT, COLOR_BG_APP);
        self.fill_rect(LCD_WIDTH - 6, 0, 6, LCD_HEIGHT, COLOR_BG_APP);
        self.fill_rect(0, LCD_HEIGHT - 6, LCD_WIDTH, 6, COLOR_BG_APP);

        // Top Accent Strip (3px Cryo Cyan / Amber / Red matching Kiosk)
        self.fill_rect(6, 6, LCD_WIDTH - 12, 3, card_border);

        // Header Background (#041b2b)
        self.fill_rect(6, 9, LCD_WIDTH - 12, 32, COLOR_BG_CARD);

        // Tank Label ("DEWAR 1 (EMBRYOS)")
        self.draw_str(16, 17, tank_name, COLOR_TEXT_MAIN, COLOR_BG_CARD, 2);

        // Battery Pill Badge in Header (e.g. "[4.12V]")
        let batt_pct = if batt_mv >= 4200 { 100 } else if batt_mv <= 3500 { 0 } else { ((batt_mv - 3500) * 100) / 700 };
        let mut b_buf = [0u8; 24];
        let b_str = format_buf(
            &mut b_buf,
            "BAT:",
            (batt_mv / 1000) as u32,
            ".",
            ((batt_mv % 1000) / 100) as u32,
            "V",
            0,
            "",
        );
        self.fill_rect(238, 14, 70, 20, COLOR_BG_CARD_SUB);
        self.fill_rect(238, 14, 70, 1, COLOR_BORDER_SUBTLE);
        self.draw_str(244, 19, b_str, COLOR_STATUS_GREEN, COLOR_BG_CARD_SUB, 1);

        // 2. Main Hero Panel (#02121e with Subtle Glacier Border)
        self.fill_rect(6, 41, LCD_WIDTH - 12, 104, COLOR_BG_CARD_SUB);
        self.fill_rect(6, 41, LCD_WIDTH - 12, 1, COLOR_BORDER_SUBTLE);

        // Hero Temperature via Precision 7-Segment Display
        let (d_sign, d_h, d_t, d_o, d_f) = split_temp_digits(temp_c_x10);
        let hero_color = if is_alarm { COLOR_STATUS_RED } else { COLOR_CRYO_CYAN };
        let seg_bg = COLOR_SEG_DIM;

        let start_x: u16 = 22;
        let hero_y: u16 = 56;
        let d_w: u16 = 38; // 36px digit + 2px space

        // Digit 1: Minus Sign
        if d_sign {
            self.draw_7seg_digit(start_x, hero_y, '-', hero_color, seg_bg);
        } else {
            self.draw_7seg_digit(start_x, hero_y, ' ', hero_color, seg_bg);
        }

        // Digit 2: Hundreds ('1')
        self.draw_7seg_digit(start_x + d_w, hero_y, d_h, hero_color, seg_bg);

        // Digit 3: Tens ('4')
        self.draw_7seg_digit(start_x + (2 * d_w), hero_y, d_t, hero_color, seg_bg);

        // Digit 4: Ones ('0')
        self.draw_7seg_digit(start_x + (3 * d_w), hero_y, d_o, hero_color, seg_bg);

        // Decimal Point '.'
        self.draw_7seg_dp(start_x + (4 * d_w) - 2, hero_y, hero_color);

        // Digit 5: Tenths ('0')
        self.draw_7seg_digit(start_x + (4 * d_w) + 8, hero_y, d_f, hero_color, seg_bg);

        // Unit '°C'
        self.draw_str(start_x + (5 * d_w) + 16, hero_y + 14, "o", hero_color, COLOR_BG_CARD_SUB, 1);
        self.draw_str(start_x + (5 * d_w) + 24, hero_y + 20, "C", hero_color, COLOR_BG_CARD_SUB, 3);

        // 3. Clinical Limit & Status Ribbon (#10B981 / #F59E0B / #EF4444)
        let ribbon_color = if is_alarm {
            COLOR_STATUS_RED
        } else if hold_active {
            COLOR_STATUS_AMBER
        } else {
            COLOR_STATUS_GREEN
        };

        self.fill_rect(6, 145, LCD_WIDTH - 12, 28, ribbon_color);
        let ribbon_text = if is_alarm {
            "CRYO EXCURSION! LIMIT EXCEEDED"
        } else if hold_active {
            "LN2 FILL MODE (HOLD 30M ACTIVE)"
        } else {
            "VAPOR LIMIT: < -135.0 C [NORMAL]"
        };
        self.draw_str(18, 153, ribbon_text, 0x0000, ribbon_color, 2);

        // 4. Kiosk Action Bar & Footer (#041b2b)
        self.fill_rect(6, 173, LCD_WIDTH - 12, 61, COLOR_BG_CARD);

        // Radio RF Status
        let mut rf_buf = [0u8; 32];
        let rf_str = format_buf(&mut rf_buf, "RADIO: ESP-NOW #", tx_seq, " [OK]", 0, "", 0, "");
        self.draw_str(16, 185, rf_str, COLOR_TEXT_MUTED, COLOR_BG_CARD, 1);

        let mut sub_buf = [0u8; 32];
        let sub_str = format_buf(&mut sub_buf, "SLOT 1 | BATT: ", batt_pct as u32, "% | USP 1079", 0, "", 0, "");
        self.draw_str(16, 203, sub_str, COLOR_TEXT_MUTED, COLOR_BG_CARD, 1);

        // Interactive Kiosk Touch Button (Lower Right)
        let (btn_bg, btn_txt) = if hold_active {
            (COLOR_STATUS_AMBER, "HOLD ACTIVE")
        } else {
            (COLOR_BTN_BLUE, "FILL HOLD")
        };
        self.fill_rect(198, 181, 110, 45, btn_bg);
        self.draw_str(206, 196, btn_txt, COLOR_TEXT_MAIN, btn_bg, 2);
    }
}

/// Splits a cryogenic tenth-degree value (-1400) into 7-segment digit characters
fn split_temp_digits(temp_c_x10: i16) -> (bool, char, char, char, char) {
    let is_neg = temp_c_x10 < 0;
    let abs_val = temp_c_x10.abs();
    let whole = abs_val / 10;
    let frac = abs_val % 10;

    let hundreds = ((whole / 100) % 10) as u8;
    let tens = ((whole / 10) % 10) as u8;
    let ones = (whole % 10) as u8;

    let c_h = if hundreds > 0 { (b'0' + hundreds) as char } else { ' ' };
    let c_t = (b'0' + tens) as char;
    let c_o = (b'0' + ones) as char;
    let c_f = (b'0' + (frac as u8)) as char;

    (is_neg, c_h, c_t, c_o, c_f)
}

fn format_buf<'a>(
    buf: &'a mut [u8],
    p1: &str,
    v1: u32,
    p2: &str,
    v2: u32,
    p3: &str,
    _v3: u32,
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
    copy_str(buf, &mut idx, p4);

    core::str::from_utf8(&buf[..idx]).unwrap_or("")
}

/// Pixel-perfect 6x10 Monospace Cleanroom Font
fn get_glyph_6x10(c: char) -> [u8; 10] {
    match c {
        '0' => [0x1E, 0x21, 0x23, 0x25, 0x29, 0x31, 0x21, 0x1E, 0x00, 0x00],
        '1' => [0x08, 0x18, 0x28, 0x08, 0x08, 0x08, 0x08, 0x3E, 0x00, 0x00],
        '2' => [0x1E, 0x21, 0x01, 0x02, 0x0C, 0x10, 0x20, 0x3F, 0x00, 0x00],
        '3' => [0x1E, 0x21, 0x01, 0x0E, 0x01, 0x01, 0x21, 0x1E, 0x00, 0x00],
        '4' => [0x02, 0x06, 0x0A, 0x12, 0x22, 0x3F, 0x02, 0x02, 0x00, 0x00],
        '5' => [0x3F, 0x20, 0x20, 0x3E, 0x01, 0x01, 0x21, 0x1E, 0x00, 0x00],
        '6' => [0x0E, 0x10, 0x20, 0x3E, 0x21, 0x21, 0x21, 0x1E, 0x00, 0x00],
        '7' => [0x3F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10, 0x10, 0x00, 0x00],
        '8' => [0x1E, 0x21, 0x21, 0x1E, 0x21, 0x21, 0x21, 0x1E, 0x00, 0x00],
        '9' => [0x1E, 0x21, 0x21, 0x21, 0x1F, 0x01, 0x02, 0x1C, 0x00, 0x00],
        '-' => [0x00, 0x00, 0x00, 0x00, 0x3F, 0x00, 0x00, 0x00, 0x00, 0x00],
        '.' => [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C, 0x00],
        ':' => [0x00, 0x0C, 0x0C, 0x00, 0x00, 0x0C, 0x0C, 0x00, 0x00, 0x00],
        '[' => [0x1E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x1E, 0x00, 0x00],
        ']' => [0x3C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x3C, 0x00, 0x00],
        '(' => [0x06, 0x0C, 0x18, 0x18, 0x18, 0x18, 0x0C, 0x06, 0x00, 0x00],
        ')' => [0x30, 0x18, 0x0C, 0x0C, 0x0C, 0x0C, 0x18, 0x30, 0x00, 0x00],
        '<' => [0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02, 0x00, 0x00, 0x00],
        '>' => [0x20, 0x10, 0x08, 0x04, 0x08, 0x10, 0x20, 0x00, 0x00, 0x00],
        '|' => [0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x00, 0x00],
        '%' => [0x23, 0x13, 0x08, 0x04, 0x32, 0x31, 0x00, 0x00, 0x00, 0x00],
        '#' => [0x12, 0x12, 0x3F, 0x12, 0x3F, 0x12, 0x12, 0x00, 0x00, 0x00],
        ' ' => [0x00; 10],
        'A' => [0x0C, 0x12, 0x21, 0x21, 0x3F, 0x21, 0x21, 0x21, 0x00, 0x00],
        'B' => [0x3E, 0x21, 0x21, 0x3E, 0x21, 0x21, 0x21, 0x3E, 0x00, 0x00],
        'C' => [0x1E, 0x21, 0x20, 0x20, 0x20, 0x20, 0x21, 0x1E, 0x00, 0x00],
        'D' => [0x3C, 0x22, 0x21, 0x21, 0x21, 0x21, 0x22, 0x3C, 0x00, 0x00],
        'E' => [0x3F, 0x20, 0x20, 0x3E, 0x20, 0x20, 0x20, 0x3F, 0x00, 0x00],
        'F' => [0x3F, 0x20, 0x20, 0x3E, 0x20, 0x20, 0x20, 0x20, 0x00, 0x00],
        'G' => [0x1E, 0x21, 0x20, 0x27, 0x21, 0x21, 0x21, 0x1E, 0x00, 0x00],
        'H' => [0x21, 0x21, 0x21, 0x3F, 0x21, 0x21, 0x21, 0x21, 0x00, 0x00],
        'I' => [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F, 0x00, 0x00],
        'J' => [0x07, 0x02, 0x02, 0x02, 0x02, 0x22, 0x22, 0x1C, 0x00, 0x00],
        'K' => [0x21, 0x22, 0x24, 0x38, 0x24, 0x22, 0x21, 0x21, 0x00, 0x00],
        'L' => [0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20, 0x3F, 0x00, 0x00],
        'M' => [0x21, 0x33, 0x3B, 0x2D, 0x21, 0x21, 0x21, 0x21, 0x00, 0x00],
        'N' => [0x21, 0x31, 0x29, 0x25, 0x23, 0x21, 0x21, 0x21, 0x00, 0x00],
        'O' => [0x1E, 0x21, 0x21, 0x21, 0x21, 0x21, 0x21, 0x1E, 0x00, 0x00],
        'P' => [0x3E, 0x21, 0x21, 0x3E, 0x20, 0x20, 0x20, 0x20, 0x00, 0x00],
        'Q' => [0x1E, 0x21, 0x21, 0x21, 0x21, 0x25, 0x22, 0x1D, 0x00, 0x00],
        'R' => [0x3E, 0x21, 0x21, 0x3E, 0x28, 0x24, 0x22, 0x21, 0x00, 0x00],
        'S' => [0x1E, 0x21, 0x20, 0x1E, 0x01, 0x01, 0x21, 0x1E, 0x00, 0x00],
        'T' => [0x3F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x00],
        'U' => [0x21, 0x21, 0x21, 0x21, 0x21, 0x21, 0x21, 0x1E, 0x00, 0x00],
        'V' => [0x21, 0x21, 0x21, 0x21, 0x12, 0x12, 0x0C, 0x0C, 0x00, 0x00],
        'W' => [0x21, 0x21, 0x21, 0x21, 0x2D, 0x2D, 0x33, 0x21, 0x00, 0x00],
        'X' => [0x21, 0x12, 0x0C, 0x0C, 0x12, 0x21, 0x21, 0x21, 0x00, 0x00],
        'Y' => [0x21, 0x21, 0x12, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x00, 0x00],
        'Z' => [0x3F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x3F, 0x00, 0x00],
        'o' => [0x00, 0x18, 0x24, 0x24, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00], // Degree circle
        _   => [0x00, 0x3F, 0x21, 0x21, 0x21, 0x3F, 0x00, 0x00, 0x00, 0x00], // Box fallback
    }
}
