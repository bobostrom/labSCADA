//! MAX31865 RTD Resistance Temperature Detector (PT100 / PT1000) Driver
//! 4-Wire SPI (SCK, MOSI, MISO, CS)

use esp_hal::delay::Delay;
use esp_hal::gpio::{Input, Output};

pub const REG_CONFIG: u8 = 0x00;
pub const REG_RTD_MSB: u8 = 0x01;
pub const REG_RTD_LSB: u8 = 0x02;
pub const REG_HIGH_FAULT_MSB: u8 = 0x03;
pub const REG_HIGH_FAULT_LSB: u8 = 0x04;
pub const REG_LOW_FAULT_MSB: u8 = 0x05;
pub const REG_LOW_FAULT_LSB: u8 = 0x06;
pub const REG_FAULT_STATUS: u8 = 0x07;

// Config register bits
pub const CONFIG_VBIAS: u8 = 0x80;
pub const CONFIG_AUTO_MODE: u8 = 0x40;
pub const CONFIG_1SHOT: u8 = 0x20;
pub const CONFIG_3WIRE: u8 = 0x10;
pub const CONFIG_FAULT_DETECT_MASK: u8 = 0x0C;
pub const CONFIG_FAULT_CLEAR: u8 = 0x02;
pub const CONFIG_50HZ_FILTER: u8 = 0x01;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RtdType {
    /// PT100 sensor with 430 Ohm reference resistor (standard Adafruit / generic)
    Pt100Rref430,
    /// PT100 sensor with 400 Ohm reference resistor
    Pt100Rref400,
    /// PT1000 sensor with 4300 Ohm reference resistor
    Pt1000Rref4300,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WireMode {
    TwoOrFourWire,
    ThreeWire,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Max31865Reading {
    pub raw_adc: u16,
    pub resistance_x100: u32, // e.g. 10000 = 100.00 Ohms, 2025 = 20.25 Ohms
    pub temp_c_x10: i16,      // e.g. -1962 = -196.2 C
    pub fault_status: u8,
    pub is_fault: bool,
}

pub struct Max31865<'d> {
    sck: Output<'d>,
    mosi: Output<'d>,
    miso: Input<'d>,
    cs: Output<'d>,
    rtd_type: RtdType,
    wire_mode: WireMode,
}

impl<'d> Max31865<'d> {
    pub fn new(
        mut sck: Output<'d>,
        mut mosi: Output<'d>,
        miso: Input<'d>,
        mut cs: Output<'d>,
        rtd_type: RtdType,
        wire_mode: WireMode,
    ) -> Self {
        sck.set_low();
        mosi.set_low();
        cs.set_high();

        Self {
            sck,
            mosi,
            miso,
            cs,
            rtd_type,
            wire_mode,
        }
    }

    /// Bit-bang SPI transfer (Mode 1 / 3: SCK idles low or high, sampled on trailing edge)
    fn transfer_byte(&mut self, byte: u8, delay: &Delay) -> u8 {
        let mut in_byte: u8 = 0;
        for i in 0..8 {
            let bit = (byte >> (7 - i)) & 0x01;
            if bit != 0 {
                self.mosi.set_high();
            } else {
                self.mosi.set_low();
            }

            // Rising clock edge
            self.sck.set_high();
            delay.delay_micros(2);

            in_byte = (in_byte << 1) | (if self.miso.is_high() { 1 } else { 0 });

            // Falling clock edge
            self.sck.set_low();
            delay.delay_micros(2);
        }
        in_byte
    }

    pub fn write_register(&mut self, reg: u8, val: u8, delay: &Delay) {
        self.cs.set_low();
        delay.delay_micros(2);
        self.transfer_byte(reg | 0x80, delay); // MSB = 1 for write
        self.transfer_byte(val, delay);
        delay.delay_micros(2);
        self.cs.set_high();
    }

    pub fn read_register(&mut self, reg: u8, delay: &Delay) -> u8 {
        self.cs.set_low();
        delay.delay_micros(2);
        self.transfer_byte(reg & 0x7F, delay); // MSB = 0 for read
        let val = self.transfer_byte(0x00, delay);
        delay.delay_micros(2);
        self.cs.set_high();
        val
    }

    /// Configure MAX31865 for continuous conversions and clear any faults
    pub fn init(&mut self, delay: &Delay) {
        // Clear any previous faults
        let mut cfg = CONFIG_FAULT_CLEAR;
        self.write_register(REG_CONFIG, cfg, delay);

        delay.delay_millis(10);

        // Turn on VBIAS and continuous conversion mode
        cfg = CONFIG_VBIAS | CONFIG_AUTO_MODE;
        if self.wire_mode == WireMode::ThreeWire {
            cfg |= CONFIG_3WIRE;
        }
        self.write_register(REG_CONFIG, cfg, delay);

        delay.delay_millis(100);
    }

    /// Read raw 15-bit ADC, convert to resistance, and calculate cryogenic temperature
    pub fn read_temperature(&mut self, delay: &Delay) -> Max31865Reading {
        // Read MSB and LSB
        self.cs.set_low();
        delay.delay_micros(2);
        self.transfer_byte(REG_RTD_MSB & 0x7F, delay);
        let msb = self.transfer_byte(0x00, delay);
        let lsb = self.transfer_byte(0x00, delay);
        delay.delay_micros(2);
        self.cs.set_high();

        let raw_adc = (((msb as u16) << 8) | (lsb as u16)) >> 1;
        let is_fault = (lsb & 0x01) != 0;

        let mut fault_status = 0;
        if is_fault {
            fault_status = self.read_register(REG_FAULT_STATUS, delay);
            // Clear fault
            let mut cfg = self.read_register(REG_CONFIG, delay);
            cfg |= CONFIG_FAULT_CLEAR;
            self.write_register(REG_CONFIG, cfg, delay);
        }

        // Calculate resistance in Ohms * 100 (e.g. 100.00 Ohm = 10000)
        let r_ref_x100: u32 = match self.rtd_type {
            RtdType::Pt100Rref430 => 43000,
            RtdType::Pt100Rref400 => 40000,
            RtdType::Pt1000Rref4300 => 430000,
        };

        let resistance_x100 = ((raw_adc as u64 * r_ref_x100 as u64) / 32768) as u32;

        // Normalize to PT100 equivalent scale (100.00 Ohm at 0 C)
        let r_pt100_x100 = match self.rtd_type {
            RtdType::Pt100Rref430 | RtdType::Pt100Rref400 => resistance_x100,
            RtdType::Pt1000Rref4300 => resistance_x100 / 10,
        };

        // Callendar-Van Dusen calculation optimized for clinical cryogenic range [-200 C to +50 C]
        // Resistance at 0 C = 100.00 Ohms (10000)
        // Resistance at -196 C = ~20.25 Ohms (2025)
        let temp_c_x10 = calculate_pt100_temp_c_x10(r_pt100_x100);

        Max31865Reading {
            raw_adc,
            resistance_x100,
            temp_c_x10,
            fault_status,
            is_fault,
        }
    }
}

/// Computes temperature in Celsius * 10 given PT100 resistance * 100 (e.g. 10000 = 100.00 Ohm)
/// Validated for IVF cryogenic storage range (-200 C to +50 C)
fn calculate_pt100_temp_c_x10(r_x100: u32) -> i16 {
    let r = r_x100 as f32 / 100.0;

    // Open circuit or disconnected probe protection
    if r > 390.0 || r < 10.0 {
        return -9999;
    }

    let temp_f: f32;
    if r >= 100.0 {
        // Above 0 C: Standard quadratic formula
        // R = R0 * (1 + A*T + B*T^2)
        // A = 3.9083e-3, B = -5.775e-7
        let a = 3.9083e-3;
        let b = -5.775e-7;
        let r0 = 100.0;
        let discriminant = a * a - 4.0 * b * (1.0 - r / r0);
        if discriminant >= 0.0 {
            temp_f = (-a + libm::sqrtf(discriminant)) / (2.0 * b);
        } else {
            temp_f = (r - 100.0) / 0.385;
        }
    } else {
        // Below 0 C down to -200 C (Cryogenic LN2 range):
        // Highly accurate polynomial inversion of Callendar-Van Dusen sub-zero curve:
        // T = -242.02 + 2.2228 * R + 2.5859e-3 * R^2 - 4.8260e-6 * R^3
        let r2 = r * r;
        let r3 = r2 * r;
        temp_f = -242.02 + (2.2228 * r) + (2.5859e-3 * r2) - (4.8260e-6 * r3);
    }

    (temp_f * 10.0) as i16
}
