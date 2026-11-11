//! FT6336G Capacitive Touch Controller Driver
//! I2C on GPIO 15 (SCL) & GPIO 16 (SDA via Flex), Touch Interrupt on GPIO 17 (Active LOW),
//! Hardware Reset on GPIO 18 (Active LOW)

use esp_hal::delay::Delay;
use esp_hal::gpio::{Flex, Input, Output};
use esp_println::println;

pub const FT6336_I2C_ADDR: u8 = 0x38;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TouchPoint {
    pub x: u16,
    pub y: u16,
    pub is_touched: bool,
}

pub struct Ft6336<'d> {
    scl: Output<'d>,
    sda: Flex<'d>,
    int_pin: Input<'d>,
    rst: Output<'d>,
}

impl<'d> Ft6336<'d> {
    pub fn new(
        mut scl: Output<'d>,
        mut sda: Flex<'d>,
        mut int_pin: Input<'d>,
        mut rst: Output<'d>,
        delay: &Delay,
    ) -> Self {
        scl.set_high();
        sda.set_input_enable(true);
        sda.set_output_enable(false); // Float high (pullup)

        // 1. Hardware Reset sequence for FT6336 (GPIO 18)
        rst.set_low();
        delay.delay_millis(15);
        rst.set_high();
        delay.delay_millis(100); // Wait for FT6336 internal boot

        int_pin.listen(esp_hal::gpio::Event::FallingEdge);

        let mut dev = Self {
            scl,
            sda,
            int_pin,
            rst,
        };

        // 2. Query Vendor / Chip ID
        let chip_id = dev.read_register(0xA6, delay);
        let vendor_id = dev.read_register(0xA8, delay);
        let default_th = dev.read_register(0x80, delay);
        println!("[+] FT6336 online: ChipID=0x{:02X}, VendorID=0x{:02X}, Factory TH_GROUP={}", chip_id, vendor_id, default_th);

        // 3. Tune Sensitivity Threshold (Register 0x80 - TH_GROUP)
        // Lower value = HIGHER sensitivity (requires lighter touch)
        // Factory default is usually 34-55 (stiff/hard press).
        // Setting to 14 provides light fingertip tap detection.
        dev.write_register(0x80, 14, delay);
        let tuned_th = dev.read_register(0x80, delay);
        println!("[+] Adjusted Touch Sensitivity: TH_GROUP (0x80) set to {}", tuned_th);

        // 4. Set Active Scan Period (Register 0x86) to 10ms for fast detection
        dev.write_register(0x86, 10, delay);

        // 5. Configure Interrupt Mode (Register 0xA4 - G_MODE)
        // 0x01 = Trigger / Edge pulse mode (clean single interrupt per touch event)
        dev.write_register(0xA4, 0x01, delay);

        // 6. Clear any startup interrupt
        let _ = dev.read_touch(delay);

        dev
    }

    /// Fast check if the user is touching the screen glass (hardware falling-edge interrupt latch)
    #[inline(always)]
    pub fn is_touch_active(&mut self) -> bool {
        if self.int_pin.is_interrupt_set() {
            self.int_pin.clear_interrupt();
            true
        } else {
            false
        }
    }

    #[inline(always)]
    pub fn is_pin_low(&self) -> bool {
        self.int_pin.is_low()
    }

    #[inline(always)]
    fn sda_high(&mut self) {
        self.sda.set_output_enable(false);
    }

    #[inline(always)]
    fn sda_low(&mut self) {
        self.sda.set_low();
        self.sda.set_output_enable(true);
    }

    // Bit-bang I2C helpers
    fn i2c_start(&mut self, delay: &Delay) {
        self.sda_high();
        self.scl.set_high();
        delay.delay_micros(2);
        self.sda_low();
        delay.delay_micros(2);
        self.scl.set_low();
        delay.delay_micros(2);
    }

    fn i2c_stop(&mut self, delay: &Delay) {
        self.sda_low();
        delay.delay_micros(2);
        self.scl.set_high();
        delay.delay_micros(2);
        self.sda_high();
        delay.delay_micros(2);
    }

    fn i2c_write_byte(&mut self, byte: u8, delay: &Delay) -> bool {
        for i in 0..8 {
            let bit = (byte >> (7 - i)) & 0x01 != 0;
            if bit {
                self.sda_high();
            } else {
                self.sda_low();
            }
            delay.delay_micros(2);
            self.scl.set_high();
            delay.delay_micros(2);
            self.scl.set_low();
            delay.delay_micros(2);
        }

        // ACK bit: release SDA and read
        self.sda_high();
        delay.delay_micros(2);
        self.scl.set_high();
        delay.delay_micros(2);
        let ack = self.sda.is_low();
        self.scl.set_low();
        delay.delay_micros(2);
        ack
    }

    fn i2c_read_byte(&mut self, ack: bool, delay: &Delay) -> u8 {
        self.sda_high();
        let mut byte = 0u8;
        for _ in 0..8 {
            self.scl.set_high();
            delay.delay_micros(2);
            byte = (byte << 1) | (if self.sda.is_high() { 1 } else { 0 });
            self.scl.set_low();
            delay.delay_micros(2);
        }

        if ack {
            self.sda_low();
        } else {
            self.sda_high();
        }
        delay.delay_micros(2);
        self.scl.set_high();
        delay.delay_micros(2);
        self.scl.set_low();
        self.sda_high();
        delay.delay_micros(2);
        byte
    }

    pub fn write_register(&mut self, reg: u8, val: u8, delay: &Delay) {
        self.write_device_reg(FT6336_I2C_ADDR, reg, val, delay);
    }

    pub fn read_register(&mut self, reg: u8, delay: &Delay) -> u8 {
        self.read_device_reg(FT6336_I2C_ADDR, reg, delay)
    }

    pub fn write_device_reg(&mut self, addr: u8, reg: u8, val: u8, delay: &Delay) -> bool {
        self.i2c_start(delay);
        if !self.i2c_write_byte(addr << 1, delay) {
            self.i2c_stop(delay);
            return false;
        }
        self.i2c_write_byte(reg, delay);
        self.i2c_write_byte(val, delay);
        self.i2c_stop(delay);
        true
    }

    pub fn read_device_reg(&mut self, addr: u8, reg: u8, delay: &Delay) -> u8 {
        self.i2c_start(delay);
        if !self.i2c_write_byte(addr << 1, delay) {
            self.i2c_stop(delay);
            return 0xFF;
        }
        self.i2c_write_byte(reg, delay);

        self.i2c_start(delay);
        if !self.i2c_write_byte((addr << 1) | 0x01, delay) {
            self.i2c_stop(delay);
            return 0xFF;
        }
        let val = self.i2c_read_byte(false, delay);
        self.i2c_stop(delay);
        val
    }

    /// Read touch coordinates and clear interrupt on FT6336
    pub fn read_touch(&mut self, delay: &Delay) -> TouchPoint {
        self.i2c_start(delay);
        if !self.i2c_write_byte(FT6336_I2C_ADDR << 1, delay) {
            self.i2c_stop(delay);
            return TouchPoint { x: 0, y: 0, is_touched: false };
        }
        self.i2c_write_byte(0x02, delay); // Start at TD_STATUS register

        // Repeated start
        self.i2c_start(delay);
        if !self.i2c_write_byte((FT6336_I2C_ADDR << 1) | 0x01, delay) {
            self.i2c_stop(delay);
            return TouchPoint { x: 0, y: 0, is_touched: false };
        }

        let touch_count = self.i2c_read_byte(true, delay) & 0x0F;
        let x_h = self.i2c_read_byte(true, delay);
        let x_l = self.i2c_read_byte(true, delay);
        let y_h = self.i2c_read_byte(true, delay);
        let y_l = self.i2c_read_byte(false, delay);
        self.i2c_stop(delay);

        if touch_count > 0 {
            let raw_x = (((x_h as u16) & 0x0F) << 8) | (x_l as u16);
            let raw_y = (((y_h as u16) & 0x0F) << 8) | (y_l as u16);

            // Map coordinate space to 180-degree landscape (320 x 240)
            // Display is rotated 0x28 (Landscape 180°).
            // Matches enclosure orientation so touch aligns with rendered buttons.
            let x = raw_y.min(320);
            let y = 240u16.saturating_sub(raw_x);

            TouchPoint {
                x,
                y,
                is_touched: true,
            }
        } else {
            TouchPoint {
                x: 0,
                y: 0,
                is_touched: false,
            }
        }
    }
}
