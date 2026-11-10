//! High-Performance Cleanroom SCADA Dashboard Display Driver
//! Matches Web Dashboard: Alaskan Deep Navy (#03141f), Marine Blue Card (#041b2b),
//! Glacier Blue (#00e5ff), Brand Blue (#0284c7), Brand Gold (#cda349), Emerald Green (#10b981)
//! Typography: Clean Modern Sans-Serif (Inter / Helvetica style)

use esp_hal::delay::Delay;
use esp_hal::gpio::Output;
use esp_hal::spi::master::Spi;
use esp_hal::Blocking;
use crate::kiosk_font::{FontDef, FONT_INTER_11, FONT_INTER_14, FONT_INTER_18, FONT_HERO_TEMP};

pub const LCD_WIDTH: u16 = 320;
pub const LCD_HEIGHT: u16 = 240;

// ==============================================================================
// Dashboard Exact Web Palette (RGB565)
// ==============================================================================
pub const COLOR_BG_APP: u16        = 0x00A3; // #03141f - Deep Alaskan Navy
pub const COLOR_BG_CARD: u16       = 0x0106; // #041b2b - Marine Blue Card
pub const COLOR_BG_CARD_SUB: u16   = 0x0084; // #02121e - Sub-panel Dark
pub const COLOR_BORDER_SUBTLE: u16 = 0x11F1; // #133D56 - Subtle Glacier Border
pub const COLOR_BORDER_ACTIVE: u16 = 0x03F4; // #037EAB - Brand Glacier Accent
pub const COLOR_CRYO_CYAN: u16     = 0x071F; // #00E5FF - Cryo Cyan / Glacier Hero
pub const COLOR_TEXT_MAIN: u16     = 0xFFFF; // #F0F8FF - Alice Ice White
pub const COLOR_TEXT_MUTED: u16    = 0x8D16; // #8BA2B5 - Slate Steel Muted Text
pub const COLOR_STATUS_GREEN: u16  = 0x15D0; // #10B981 - Emerald Green Normal
pub const COLOR_STATUS_AMBER: u16  = 0xF4E1; // #CDA349 / #F59E0B - Brand Gold / Hold Active
pub const COLOR_STATUS_RED: u16    = 0xEA28; // #EF4444 - Excursion Emergency Red
pub const COLOR_BTN_BLUE: u16      = 0x0438; // #0284C7 - Kiosk Action Button Sky Blue

pub struct Ili9341<'d> {
    spi: Spi<'d, Blocking>,
    cs: Output<'d>,
    dc: Output<'d>,
    backlight: Output<'d>,
    is_on: bool,
}

impl<'d> Ili9341<'d> {
    pub fn new(
        spi: Spi<'d, Blocking>,
        mut cs: Output<'d>,
        mut dc: Output<'d>,
        mut backlight: Output<'d>,
    ) -> Self {
        cs.set_high();
        dc.set_high();
        backlight.set_low();

        Self {
            spi,
            cs,
            dc,
            backlight,
            is_on: false,
        }
    }

    #[inline(always)]
    fn write_cmd(&mut self, cmd: u8) {
        self.dc.set_low();
        self.cs.set_low();
        let _ = self.spi.write(&[cmd]);
        self.cs.set_high();
    }

    #[inline(always)]
    fn write_data(&mut self, data: u8) {
        self.dc.set_high();
        self.cs.set_low();
        let _ = self.spi.write(&[data]);
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

    /// Hardware initialization for ES3C28P IPS Display
    pub fn init(&mut self, delay: &Delay) {
        self.write_cmd(0x01); // Software Reset
        delay.delay_millis(120);

        self.write_cmd(0x11); // Sleep Out
        delay.delay_millis(120);

        // Memory Access Control: Landscape (MY=1, MX=1, MV=1, BGR=1 -> 0xE8)
        // Eliminates mirror imaging!
        self.write_cmd(0x36);
        self.write_data(0xE8);

        // CRITICAL FOR IPS PANELS: Display Inversion ON (INVON = 0x21)
        // Fixes inverted negative colors on IPS screens!
        self.write_cmd(0x21);

        // Pixel Format: 16-bit RGB565
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

        // VCOM Control 1: tuned for deep blacks and rich contrast on IPS panels
        self.write_cmd(0xC5);
        self.write_data(0x3E); // VCOMH = 4.25V
        self.write_data(0x28); // VCOML = -1.5V

        // Select Gamma Curve 1
        self.write_cmd(0x26);
        self.write_data(0x01);

        // Positive Gamma Correction (0xE0) - Calibrated IPS Curve
        self.write_cmd(0xE0);
        for &val in &[
            0x0F, 0x31, 0x2B, 0x0C, 0x0E, 0x08, 0x4E, 0xF1,
            0x37, 0x07, 0x10, 0x03, 0x0E, 0x09, 0x00,
        ] {
            self.write_data(val);
        }

        // Negative Gamma Correction (0xE1) - Calibrated IPS Curve
        self.write_cmd(0xE1);
        for &val in &[
            0x00, 0x0E, 0x14, 0x03, 0x11, 0x07, 0x31, 0xC1,
            0x48, 0x08, 0x0F, 0x0C, 0x31, 0x36, 0x0F,
        ] {
            self.write_data(val);
        }

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

        let mut count = (x1 - x + 1) as usize * (y1 - y + 1) as usize;
        self.dc.set_high();
        self.cs.set_low();

        let hi = (color >> 8) as u8;
        let lo = (color & 0xFF) as u8;

        // Fast burst buffer of 64 pixels (128 bytes)
        let mut buf = [0u8; 128];
        for i in 0..64 {
            buf[i * 2] = hi;
            buf[i * 2 + 1] = lo;
        }

        while count > 0 {
            let chunk_pixels = count.min(64);
            let _ = self.spi.write(&buf[..chunk_pixels * 2]);
            count -= chunk_pixels;
        }
        self.cs.set_high();
    }

    pub fn clear(&mut self, color: u16) {
        self.fill_rect(0, 0, LCD_WIDTH, LCD_HEIGHT, color);
    }

    // ==============================================================================
    // Clean Modern Sans-Serif Hero Numbers (Inter / Helvetica style)
    // 32px wide, 52px tall, smooth solid strokes, zero jaggies.
    // ==============================================================================
    pub fn draw_sans_hero_digit(&mut self, x: u16, y: u16, c: char, fg: u16, bg: u16) {
        // Clear digit bounding box
        self.fill_rect(x, y, 32, 52, bg);
        let t = 6u16; // Stroke thickness

        match c {
            '0' => {
                self.fill_rect(x + 4, y, 24, t, fg);         // Top
                self.fill_rect(x + 4, y + 46, 24, t, fg);    // Bottom
                self.fill_rect(x, y + 4, t, 44, fg);         // Left
                self.fill_rect(x + 26, y + 4, t, 44, fg);    // Right
            }
            '1' => {
                self.fill_rect(x + 14, y, 7, 52, fg);
                self.fill_rect(x + 6, y + 2, 8, 6, fg);
                self.fill_rect(x + 6, y + 46, 22, 6, fg);
            }
            '2' => {
                self.fill_rect(x + 4, y, 24, t, fg);         // Top
                self.fill_rect(x + 26, y + 4, t, 20, fg);     // Top Right
                self.fill_rect(x + 4, y + 23, 24, t, fg);    // Middle
                self.fill_rect(x, y + 26, t, 20, fg);        // Bottom Left
                self.fill_rect(x, y + 46, 32, t, fg);        // Bottom
            }
            '3' => {
                self.fill_rect(x + 4, y, 24, t, fg);         // Top
                self.fill_rect(x + 26, y + 4, t, 44, fg);     // Right
                self.fill_rect(x + 8, y + 23, 20, t, fg);    // Middle
                self.fill_rect(x + 4, y + 46, 24, t, fg);    // Bottom
            }
            '4' => {
                self.fill_rect(x + 20, y, 7, 52, fg);
                self.fill_rect(x + 2, y + 2, 7, 30, fg);
                self.fill_rect(x + 2, y + 26, 28, 7, fg);
            }
            '5' => {
                self.fill_rect(x, y, 32, t, fg);             // Top
                self.fill_rect(x, y + 4, t, 20, fg);         // Top Left
                self.fill_rect(x, y + 23, 28, t, fg);        // Middle
                self.fill_rect(x + 26, y + 26, t, 20, fg);    // Bottom Right
                self.fill_rect(x + 4, y + 46, 24, t, fg);    // Bottom
            }
            '6' => {
                self.fill_rect(x + 4, y, 24, t, fg);         // Top
                self.fill_rect(x, y + 4, t, 44, fg);         // Left
                self.fill_rect(x + 4, y + 23, 24, t, fg);    // Middle
                self.fill_rect(x + 26, y + 26, t, 20, fg);    // Bottom Right
                self.fill_rect(x + 4, y + 46, 24, t, fg);    // Bottom
            }
            '7' => {
                self.fill_rect(x, y, 32, t, fg);             // Top
                self.fill_rect(x + 24, y + 4, 8, 48, fg);    // Right
            }
            '8' => {
                self.fill_rect(x + 4, y, 24, t, fg);         // Top
                self.fill_rect(x + 4, y + 23, 24, t, fg);    // Middle
                self.fill_rect(x + 4, y + 46, 24, t, fg);    // Bottom
                self.fill_rect(x, y + 4, t, 44, fg);         // Left
                self.fill_rect(x + 26, y + 4, t, 44, fg);    // Right
            }
            '9' => {
                self.fill_rect(x + 4, y, 24, t, fg);         // Top
                self.fill_rect(x, y + 4, t, 22, fg);         // Top Left
                self.fill_rect(x + 4, y + 23, 24, t, fg);    // Middle
                self.fill_rect(x + 26, y + 4, t, 44, fg);    // Right
                self.fill_rect(x + 4, y + 46, 24, t, fg);    // Bottom
            }
            '-' => {
                self.fill_rect(x + 4, y + 23, 24, 7, fg);
            }
            _ => {
                self.fill_rect(x + 6, y + 6, 20, 40, fg);
            }
        }
    }

    /// Decimal point for hero numbers
    pub fn draw_sans_dp(&mut self, x: u16, y: u16, fg: u16, bg: u16) {
        self.fill_rect(x, y, 12, 52, bg);
        self.fill_rect(x + 2, y + 44, 8, 8, fg);
    }

    // ==============================================================================
    // Clean Inter Monospace Font for Labels and Badges
    // ==============================================================================
    pub fn draw_char(&mut self, x: u16, y: u16, c: char, fg: u16, bg: u16, scale: u8) {
        let glyph = get_glyph_6x10(c);
        let s = scale.max(1) as u16;

        if s == 1 {
            self.set_window(x, y, x + 5, y + 9);
            self.dc.set_high();
            self.cs.set_low();
            let mut char_buf = [0u8; 120];
            let mut idx = 0;
            for row in 0..10usize {
                let bits = glyph[row];
                for col in 0..6u16 {
                    let pixel_on = (bits >> (5 - col)) & 0x01 != 0;
                    let color = if pixel_on { fg } else { bg };
                    char_buf[idx] = (color >> 8) as u8;
                    char_buf[idx + 1] = (color & 0xFF) as u8;
                    idx += 2;
                }
            }
            let _ = self.spi.write(&char_buf);
            self.cs.set_high();
        } else {
            for row in 0..10u16 {
                let bits = glyph[row as usize];
                for col in 0..6u16 {
                    let pixel_on = (bits >> (5 - col)) & 0x01 != 0;
                    let color = if pixel_on { fg } else { bg };
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

    pub fn draw_kiosk_char(
        &mut self,
        x: u16,
        y: u16,
        c: char,
        font: &FontDef,
        fg: u16,
        bg: u16,
    ) -> u16 {
        let glyph = match font.get_glyph(c) {
            Some(g) => g,
            None => return 0,
        };
        let w = glyph.width as u16;
        let h = font.height as u16;
        if w == 0 || x + w > LCD_WIDTH || y + h > LCD_HEIGHT {
            return w;
        }

        self.set_window(x, y, x + w - 1, y + h - 1);
        self.dc.set_high();
        self.cs.set_low();

        let bytes_per_row = ((w + 7) / 8) as usize;
        let hi_fg = (fg >> 8) as u8;
        let lo_fg = (fg & 0xFF) as u8;
        let hi_bg = (bg >> 8) as u8;
        let lo_bg = (bg & 0xFF) as u8;

        let mut burst_buf = [0u8; 128];
        let mut burst_idx = 0;

        for row in 0..h as usize {
            let row_offset = glyph.bitmap_offset as usize + row * bytes_per_row;
            for col in 0..w as usize {
                let byte_idx = row_offset + (col / 8);
                let bit_mask = 1 << (7 - (col % 8));
                let is_on = (font.bitmaps[byte_idx] & bit_mask) != 0;

                if is_on {
                    burst_buf[burst_idx] = hi_fg;
                    burst_buf[burst_idx + 1] = lo_fg;
                } else {
                    burst_buf[burst_idx] = hi_bg;
                    burst_buf[burst_idx + 1] = lo_bg;
                }
                burst_idx += 2;

                if burst_idx == 128 {
                    let _ = self.spi.write(&burst_buf);
                    burst_idx = 0;
                }
            }
        }
        if burst_idx > 0 {
            let _ = self.spi.write(&burst_buf[..burst_idx]);
        }
        self.cs.set_high();

        w
    }

    pub fn draw_kiosk_str(
        &mut self,
        mut x: u16,
        y: u16,
        s: &str,
        font: &FontDef,
        fg: u16,
        bg: u16,
    ) -> u16 {
        for c in s.chars() {
            let adv = self.draw_kiosk_char(x, y, c, font, fg, bg);
            x += adv;
        }
        x
    }

    // ==============================================================================
    // Dashboard Kiosk Card Screen (Exact Kiosk Inter & Consolas Bold Monospace)
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
        let card_border = if is_alarm {
            COLOR_STATUS_RED
        } else if hold_active {
            COLOR_STATUS_AMBER
        } else {
            COLOR_CRYO_CYAN
        };

        // Outer App background (#03141f)
        self.fill_rect(0, 0, LCD_WIDTH, 4, COLOR_BG_APP);
        self.fill_rect(0, 0, 4, LCD_HEIGHT, COLOR_BG_APP);
        self.fill_rect(LCD_WIDTH - 4, 0, 4, LCD_HEIGHT, COLOR_BG_APP);
        self.fill_rect(0, LCD_HEIGHT - 4, LCD_WIDTH, 4, COLOR_BG_APP);

        // 1. Kiosk Card Top Accent Bar (3px Cryo Cyan / Amber / Red)
        self.fill_rect(4, 4, LCD_WIDTH - 8, 3, card_border);

        // 2. Card Header (#041b2b)
        self.fill_rect(4, 7, LCD_WIDTH - 8, 34, COLOR_BG_CARD);

        // Tank Label: "Dewar 1 (Embryos)" - in Inter 18pt
        self.draw_kiosk_str(14, 15, tank_name, &FONT_INTER_18, COLOR_TEXT_MAIN, COLOR_BG_CARD);

        // Battery Pill in Header - in Inter 11pt
        let batt_pct = if batt_mv >= 4200 { 100 } else if batt_mv <= 3500 { 0 } else { ((batt_mv - 3500) * 100) / 700 };
        let mut b_buf = [0u8; 24];
        let b_str = format_buf(
            &mut b_buf,
            "BAT: ",
            (batt_mv / 1000) as u32,
            ".",
            ((batt_mv % 1000) / 100) as u32,
            "V",
            0,
            "",
        );
        let b_w = FONT_INTER_11.string_width(b_str);
        let pill_w = b_w + 16;
        let pill_x = LCD_WIDTH - 8 - pill_w - 4;
        self.fill_rect(pill_x, 13, pill_w, 22, COLOR_BG_CARD_SUB);
        self.fill_rect(pill_x, 13, pill_w, 1, COLOR_BORDER_SUBTLE);
        self.draw_kiosk_str(pill_x + 8, 17, b_str, &FONT_INTER_11, COLOR_STATUS_GREEN, COLOR_BG_CARD_SUB);

        // 3. Main Hero Panel (#02121e with Subtle Glacier Border)
        self.fill_rect(4, 41, LCD_WIDTH - 8, 102, COLOR_BG_CARD_SUB);
        self.fill_rect(4, 41, LCD_WIDTH - 8, 1, COLOR_BORDER_SUBTLE);

        // Hero Temperature digits in Kiosk .card-val Consolas Bold 48pt Monospace ("-140.0 ^C")
        let hero_color = if is_alarm { COLOR_STATUS_RED } else { COLOR_CRYO_CYAN };
        let hero_bg = COLOR_BG_CARD_SUB;
        let mut hero_buf = [0u8; 16];
        let hero_str = format_temp(&mut hero_buf, temp_c_x10);
        let hero_w = FONT_HERO_TEMP.string_width(hero_str);
        let hero_x = (LCD_WIDTH.saturating_sub(hero_w)) / 2;
        let hero_y = 41 + (102 - FONT_HERO_TEMP.height as u16) / 2;
        self.draw_kiosk_str(hero_x, hero_y, hero_str, &FONT_HERO_TEMP, hero_color, hero_bg);

        // 4. Clinical Status Ribbon
        let ribbon_color = if is_alarm {
            COLOR_STATUS_RED
        } else if hold_active {
            COLOR_STATUS_AMBER
        } else {
            COLOR_STATUS_GREEN
        };

        self.fill_rect(4, 143, LCD_WIDTH - 8, 28, ribbon_color);
        let ribbon_text = if is_alarm {
            "CRYO EXCURSION! LIMIT EXCEEDED"
        } else if hold_active {
            "LN2 FILL MODE (HOLD 30M ACTIVE)"
        } else {
            "VAPOR LIMIT: < -135.0 ^C [NORMAL]"
        };
        let ribbon_w = FONT_INTER_14.string_width(ribbon_text);
        let ribbon_x = (LCD_WIDTH.saturating_sub(ribbon_w)) / 2;
        let ribbon_y = 143 + (28 - FONT_INTER_14.height as u16) / 2;
        self.draw_kiosk_str(ribbon_x, ribbon_y, ribbon_text, &FONT_INTER_14, 0x0000, ribbon_color);

        // 5. Action Bar & Footer (#041b2b)
        self.fill_rect(4, 171, LCD_WIDTH - 8, 65, COLOR_BG_CARD);

        let mut rf_buf = [0u8; 32];
        let rf_str = format_buf(&mut rf_buf, "RADIO: ESP-NOW #", tx_seq, " [OK]", 0, "", 0, "");
        self.draw_kiosk_str(14, 181, rf_str, &FONT_INTER_11, COLOR_TEXT_MUTED, COLOR_BG_CARD);

        let mut sub_buf = [0u8; 32];
        let sub_str = format_buf(&mut sub_buf, "SLOT 1 | BATT: ", batt_pct as u32, "% | USP 1079", 0, "", 0, "");
        self.draw_kiosk_str(14, 203, sub_str, &FONT_INTER_11, COLOR_TEXT_MUTED, COLOR_BG_CARD);

        // Interactive Kiosk Touch Button (Lower Right)
        let (btn_bg, btn_txt) = if hold_active {
            (COLOR_STATUS_AMBER, "HOLD ACTIVE")
        } else {
            (COLOR_BTN_BLUE, "FILL HOLD")
        };
        self.fill_rect(196, 179, 114, 47, btn_bg);
        let btn_w = FONT_INTER_14.string_width(btn_txt);
        let btn_x = 196 + (114u16.saturating_sub(btn_w)) / 2;
        let btn_y = 179 + (47 - FONT_INTER_14.height as u16) / 2;
        self.draw_kiosk_str(btn_x, btn_y, btn_txt, &FONT_INTER_14, COLOR_TEXT_MAIN, btn_bg);
    }
}

fn format_temp<'a>(buf: &'a mut [u8], temp_c_x10: i16) -> &'a str {
    let mut idx = 0;
    let is_neg = temp_c_x10 < 0;
    let val = if is_neg { (-temp_c_x10) as u32 } else { temp_c_x10 as u32 };
    let whole = val / 10;
    let frac = val % 10;

    if is_neg && idx < buf.len() {
        buf[idx] = b'-';
        idx += 1;
    }

    let mut num_buf = [0u8; 8];
    let mut num_idx = 0;
    let mut n = whole;
    if n == 0 {
        num_buf[0] = b'0';
        num_idx = 1;
    } else {
        while n > 0 && num_idx < num_buf.len() {
            num_buf[num_idx] = b'0' + (n % 10) as u8;
            num_idx += 1;
            n /= 10;
        }
    }
    for i in (0..num_idx).rev() {
        if idx < buf.len() {
            buf[idx] = num_buf[i];
            idx += 1;
        }
    }
    if idx < buf.len() {
        buf[idx] = b'.';
        idx += 1;
    }
    if idx < buf.len() {
        buf[idx] = b'0' + frac as u8;
        idx += 1;
    }
    if idx < buf.len() {
        buf[idx] = b' ';
        idx += 1;
    }
    if idx < buf.len() {
        buf[idx] = b'^'; // Raised degree symbol in FONT_HANDEL
        idx += 1;
    }
    if idx < buf.len() {
        buf[idx] = b'C';
        idx += 1;
    }
    core::str::from_utf8(&buf[..idx]).unwrap_or("")
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

/// Clean 6x10 Monospace Cleanroom Font
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
        '°' => [0x00, 0x18, 0x24, 0x24, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00],
        'a' => [0x00, 0x00, 0x1E, 0x01, 0x1F, 0x21, 0x21, 0x1F, 0x00, 0x00],
        'b' => [0x20, 0x20, 0x3E, 0x21, 0x21, 0x21, 0x21, 0x3E, 0x00, 0x00],
        'c' => [0x00, 0x00, 0x1E, 0x21, 0x20, 0x20, 0x21, 0x1E, 0x00, 0x00],
        'd' => [0x01, 0x01, 0x1F, 0x21, 0x21, 0x21, 0x21, 0x1F, 0x00, 0x00],
        'e' => [0x00, 0x00, 0x1E, 0x21, 0x3F, 0x20, 0x21, 0x1E, 0x00, 0x00],
        'f' => [0x0E, 0x11, 0x10, 0x3C, 0x10, 0x10, 0x10, 0x10, 0x00, 0x00],
        'g' => [0x00, 0x00, 0x1F, 0x21, 0x21, 0x1F, 0x01, 0x1E, 0x00, 0x00],
        'h' => [0x20, 0x20, 0x3E, 0x21, 0x21, 0x21, 0x21, 0x21, 0x00, 0x00],
        'i' => [0x08, 0x00, 0x18, 0x08, 0x08, 0x08, 0x08, 0x1C, 0x00, 0x00],
        'j' => [0x02, 0x00, 0x06, 0x02, 0x02, 0x02, 0x22, 0x1C, 0x00, 0x00],
        'k' => [0x20, 0x20, 0x22, 0x24, 0x38, 0x24, 0x22, 0x21, 0x00, 0x00],
        'l' => [0x18, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x1C, 0x00, 0x00],
        'm' => [0x00, 0x00, 0x36, 0x2B, 0x29, 0x29, 0x29, 0x29, 0x00, 0x00],
        'n' => [0x00, 0x00, 0x3E, 0x21, 0x21, 0x21, 0x21, 0x21, 0x00, 0x00],
        'o' => [0x00, 0x00, 0x1E, 0x21, 0x21, 0x21, 0x21, 0x1E, 0x00, 0x00],
        'p' => [0x00, 0x00, 0x3E, 0x21, 0x21, 0x3E, 0x20, 0x20, 0x00, 0x00],
        'q' => [0x00, 0x00, 0x1F, 0x21, 0x21, 0x1F, 0x01, 0x01, 0x00, 0x00],
        'r' => [0x00, 0x00, 0x2E, 0x31, 0x20, 0x20, 0x20, 0x20, 0x00, 0x00],
        's' => [0x00, 0x00, 0x1E, 0x20, 0x1E, 0x01, 0x21, 0x1E, 0x00, 0x00],
        't' => [0x10, 0x10, 0x3C, 0x10, 0x10, 0x10, 0x11, 0x0E, 0x00, 0x00],
        'u' => [0x00, 0x00, 0x21, 0x21, 0x21, 0x21, 0x23, 0x1D, 0x00, 0x00],
        'v' => [0x00, 0x00, 0x21, 0x21, 0x21, 0x12, 0x12, 0x0C, 0x00, 0x00],
        'w' => [0x00, 0x00, 0x21, 0x21, 0x25, 0x25, 0x2D, 0x12, 0x00, 0x00],
        'x' => [0x00, 0x00, 0x21, 0x12, 0x0C, 0x0C, 0x12, 0x21, 0x00, 0x00],
        'y' => [0x00, 0x00, 0x21, 0x21, 0x21, 0x1F, 0x01, 0x1E, 0x00, 0x00],
        'z' => [0x00, 0x00, 0x3F, 0x02, 0x04, 0x08, 0x10, 0x3F, 0x00, 0x00],
        _   => [0x00; 10], // Default to space/blank instead of an ugly box!
    }
}
