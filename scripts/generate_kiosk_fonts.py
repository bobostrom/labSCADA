"""
Generate Exact Kiosk Dashboard Fonts for dewar-display (ESP32-S3):
- FONT_HERO_TEMP: Exact Kiosk .card-val monospace font (Consolas Bold, 48pt) for rock-solid temperature numerals.
- FONT_INTER_18: Exact Kiosk Card Title font (Inter Bold, 18pt) for "Dewar 1 (Embryos)".
- FONT_INTER_14: Exact Kiosk Button & Status Ribbon font (Inter Bold, 14pt) for "VAPOR LIMIT: < -135.0 C [NORMAL]" & "FILL HOLD".
- FONT_INTER_11: Exact Kiosk Metadata font (Inter Medium, 11pt) for "RADIO: ESP-NOW" & "BAT: 3.8V".
"""

import os
from PIL import Image, ImageFont, ImageDraw

CONSOLAS_BOLD = r"C:\Windows\Fonts\consolab.ttf"
INTER_FONT = "Inter.ttf"

def rasterize_font_cells(font_path, font_size, char_list, is_hero=False):
    font = ImageFont.truetype(font_path, font_size)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent

    glyphs = []
    all_bitmap_bytes = []

    for ch in char_list:
        if ch == '^':
            # Custom raised degree symbol circle
            r = max(2, font_size // 7)
            adv = 2 * r + 4
            top_y = max(1, font_size // 8)
            img = Image.new('1', (adv, line_height), 0)
            draw = ImageDraw.Draw(img)
            stroke = 2 if font_size >= 36 else 1
            draw.ellipse([(1, top_y), (1 + 2 * r, top_y + 2 * r)], outline=1, width=stroke)
        else:
            adv = max(1, int(round(font.getlength(ch))))
            img = Image.new('1', (adv, line_height), 0)
            draw = ImageDraw.Draw(img)
            draw.text((0, 0), ch, font=font, fill=1)

        bytes_per_row = (adv + 7) // 8
        glyph_bytes = []
        for row in range(line_height):
            for b in range(bytes_per_row):
                byte_val = 0
                for bit in range(8):
                    col = b * 8 + bit
                    if col < adv and img.getpixel((col, row)):
                        byte_val |= (1 << (7 - bit))
                glyph_bytes.append(byte_val)

        glyphs.append({
            'char': ch,
            'width': adv,
            'bitmap_offset': len(all_bitmap_bytes),
            'byte_count': len(glyph_bytes),
        })
        all_bitmap_bytes.extend(glyph_bytes)

    return {
        'font_size': font_size,
        'line_height': line_height,
        'ascent': ascent,
        'descent': descent,
        'glyphs': glyphs,
        'bitmaps': all_bitmap_bytes,
    }


def main():
    ascii_chars = [chr(c) for c in range(32, 127)]
    hero_chars = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '-', '.', '^', 'C', ' ', '%']

    # 1. Monospace Hero Numbers (Exact Kiosk .card-val Consolas Bold 48pt)
    f_hero = rasterize_font_cells(CONSOLAS_BOLD, 48, hero_chars, is_hero=True)

    # 2. Inter UI Fonts (Exact Kiosk Dashboard Inter 18pt, 14pt, 11pt)
    f18 = rasterize_font_cells(INTER_FONT, 18, ascii_chars)
    f14 = rasterize_font_cells(INTER_FONT, 14, ascii_chars)
    f11 = rasterize_font_cells(INTER_FONT, 11, ascii_chars)

    out_path = r"C:\Projects\labSCADA\wireless\crates\dewar-display\src\kiosk_font.rs"
    with open(out_path, "w", encoding="utf-8") as out:
        out.write("""//! Exact Kiosk Dashboard Typography
//! Generated from 'Inter.ttf' and 'Consolas Bold' (matching kiosk.html .card-val)

#[derive(Clone, Copy)]
pub struct Glyph {
    pub char_code: u8,
    pub width: u8,
    pub bitmap_offset: u16,
}

pub struct FontDef {
    pub height: u8,
    pub first_char: u8,
    pub last_char: u8,
    pub glyphs: &'static [Glyph],
    pub bitmaps: &'static [u8],
}

impl FontDef {
    pub fn get_glyph(&self, ch: char) -> Option<&'static Glyph> {
        let code = ch as u8;
        if code >= self.first_char && code <= self.last_char && self.last_char > 0 {
            let idx = (code - self.first_char) as usize;
            if idx < self.glyphs.len() {
                return Some(&self.glyphs[idx]);
            }
        } else {
            for g in self.glyphs {
                if g.char_code == code {
                    return Some(g);
                }
            }
        }
        None
    }

    pub fn string_width(&self, s: &str) -> u16 {
        let mut w = 0u16;
        for c in s.chars() {
            if let Some(g) = self.get_glyph(c) {
                w += g.width as u16;
            }
        }
        w
    }
}
""")

        write_font_def(out, "FONT_INTER_11", f11, 32, 126)
        write_font_def(out, "FONT_INTER_14", f14, 32, 126)
        write_font_def(out, "FONT_INTER_18", f18, 32, 126)
        write_font_def(out, "FONT_HERO_TEMP", f_hero, 0, 0)

    print(f"Generated {out_path} successfully!")


def write_font_def(out, var_name, font_data, first_char, last_char):
    glyphs = font_data['glyphs']
    bitmaps = font_data['bitmaps']

    out.write(f"\n// ==============================================================================\n")
    out.write(f"// {var_name} (Height: {font_data['line_height']}px, Glyphs: {len(glyphs)})\n")
    out.write(f"// ==============================================================================\n")

    out.write(f"static {var_name}_GLYPHS: [Glyph; {len(glyphs)}] = [\n")
    for g in glyphs:
        out.write(f"    Glyph {{ char_code: {ord(g['char'])}, width: {g['width']}, bitmap_offset: {g['bitmap_offset']} }},\n")
    out.write("];\n\n")

    out.write(f"static {var_name}_BITMAPS: [u8; {len(bitmaps)}] = [\n    ")
    for i, b in enumerate(bitmaps):
        out.write(f"0x{b:02X}, ")
        if (i + 1) % 16 == 0:
            out.write("\n    ")
    out.write("\n];\n\n")

    out.write(f"pub static {var_name}: FontDef = FontDef {{\n")
    out.write(f"    height: {font_data['line_height']},\n")
    out.write(f"    first_char: {first_char},\n")
    out.write(f"    last_char: {last_char},\n")
    out.write(f"    glyphs: &{var_name}_GLYPHS,\n")
    out.write(f"    bitmaps: &{var_name}_BITMAPS,\n")
    out.write("};\n")


if __name__ == "__main__":
    main()

