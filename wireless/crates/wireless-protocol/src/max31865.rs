//! MAX31865 RTD Resistance Temperature Detector (PT100 / PT1000) Driver
//! 4-Wire bit-banged SPI (SCK, MOSI, MISO, CS) over `embedded-hal` 1.0 traits.

use embedded_hal::delay::DelayNs;
use embedded_hal::digital::{InputPin, OutputPin};

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

/// Bit-banged SPI driver for the MAX31865 RTD-to-digital converter.
pub struct Max31865<SCK, MOSI, MISO, CS> {
    sck: SCK,
    mosi: MOSI,
    miso: MISO,
    cs: CS,
    rtd_type: RtdType,
    wire_mode: WireMode,
}

impl<SCK, MOSI, MISO, CS> Max31865<SCK, MOSI, MISO, CS>
where
    SCK: OutputPin,
    MOSI: OutputPin,
    MISO: InputPin,
    CS: OutputPin,
{
    pub fn new(
        mut sck: SCK,
        mut mosi: MOSI,
        miso: MISO,
        mut cs: CS,
        rtd_type: RtdType,
        wire_mode: WireMode,
    ) -> Self {
        let _ = sck.set_low();
        let _ = mosi.set_low();
        let _ = cs.set_high();

        Self {
            sck,
            mosi,
            miso,
            cs,
            rtd_type,
            wire_mode,
        }
    }

    /// Bit-bang SPI transfer (Mode 1/3: SCK idles low, data sampled on falling edge)
    fn transfer_byte(&mut self, byte: u8, delay: &mut impl DelayNs) -> u8 {
        let mut in_byte: u8 = 0;
        for i in 0..8 {
            let bit = (byte >> (7 - i)) & 0x01;
            if bit != 0 {
                let _ = self.mosi.set_high();
            } else {
                let _ = self.mosi.set_low();
            }

            // Rising clock edge
            let _ = self.sck.set_high();
            delay.delay_us(2);

            let sample = if self.miso.is_high().unwrap_or(false) { 1 } else { 0 };
            in_byte = (in_byte << 1) | sample;

            // Falling clock edge
            let _ = self.sck.set_low();
            delay.delay_us(2);
        }
        in_byte
    }

    pub fn write_register(&mut self, reg: u8, val: u8, delay: &mut impl DelayNs) {
        let _ = self.cs.set_low();
        delay.delay_us(2);
        self.transfer_byte(reg | 0x80, delay); // MSB = 1 for write
        self.transfer_byte(val, delay);
        delay.delay_us(2);
        let _ = self.cs.set_high();
    }

    pub fn read_register(&mut self, reg: u8, delay: &mut impl DelayNs) -> u8 {
        let _ = self.cs.set_low();
        delay.delay_us(2);
        self.transfer_byte(reg & 0x7F, delay); // MSB = 0 for read
        let val = self.transfer_byte(0x00, delay);
        delay.delay_us(2);
        let _ = self.cs.set_high();
        val
    }

    /// Configure MAX31865 for continuous conversions and clear any faults.
    /// Pre-charges VBIAS briefly before starting continuous conversion so the first
    /// reading after power-up or sleep is settled.
    pub fn init(&mut self, delay: &mut impl DelayNs) {
        let wire_bit = if self.wire_mode == WireMode::ThreeWire {
            CONFIG_3WIRE
        } else {
            0
        };

        self.write_register(REG_CONFIG, CONFIG_FAULT_CLEAR | wire_bit, delay);
        delay.delay_ms(10);

        // Charge VBIAS capacitor before starting conversion
        self.write_register(REG_CONFIG, CONFIG_VBIAS | wire_bit, delay);
        delay.delay_ms(15);

        // Enable continuous conversion mode and wait for first conversion (~65ms max)
        self.write_register(REG_CONFIG, CONFIG_VBIAS | CONFIG_AUTO_MODE | wire_bit, delay);
        delay.delay_ms(85);
    }

    /// Disable VBIAS and continuous conversion to cut quiescent draw (~2 uA) before deep sleep.
    pub fn shutdown(&mut self, delay: &mut impl DelayNs) {
        let wire_bit = if self.wire_mode == WireMode::ThreeWire {
            CONFIG_3WIRE
        } else {
            0
        };
        self.write_register(REG_CONFIG, wire_bit, delay);
    }

    /// Read raw 15-bit ADC, convert to resistance, and calculate cryogenic temperature
    pub fn read_temperature(&mut self, delay: &mut impl DelayNs) -> Max31865Reading {
        let _ = self.cs.set_low();
        delay.delay_us(2);
        self.transfer_byte(REG_RTD_MSB & 0x7F, delay);
        let msb = self.transfer_byte(0x00, delay);
        let lsb = self.transfer_byte(0x00, delay);
        delay.delay_us(2);
        let _ = self.cs.set_high();

        let raw_adc = (((msb as u16) << 8) | (lsb as u16)) >> 1;
        let is_fault = (lsb & 0x01) != 0;

        let mut fault_status = 0;
        if is_fault {
            fault_status = self.read_register(REG_FAULT_STATUS, delay);
            let mut cfg = self.read_register(REG_CONFIG, delay);
            cfg |= CONFIG_FAULT_CLEAR;
            self.write_register(REG_CONFIG, cfg, delay);
        }

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

/// Convert a MAX31865 RTD reading to `(temp_c_x10, sensor_fault_code)`.
/// Fault codes match `crate::DeviceTelemetry::Dewar`:
/// 0 = OK, 1 = Probe Disconnected / Out of Range, 2 = Short, 3 = Hardware Fault.
pub fn eval_rtd_reading(reading: &Max31865Reading) -> (i16, u8) {
    if !reading.is_fault && reading.temp_c_x10 != -9999 {
        return (reading.temp_c_x10, 0);
    }

    let fault_code = if (reading.fault_status & 0x80) != 0 {
        1 // RTD High Threshold / Open Circuit
    } else if (reading.fault_status & 0x40) != 0 {
        2 // RTD Low Threshold / Short
    } else if reading.is_fault || reading.raw_adc == 0 {
        3 // Hardware / VBIAS / REFIN / SPI Bus Fault
    } else {
        1 // Out-of-range resistance (-9999 sentinel)
    };
    (-9999, fault_code)
}

/// Computes temperature in Celsius * 10 given PT100 resistance * 100 (e.g. 10000 = 100.00 Ohm)
/// Validated for IVF cryogenic storage range (-200 C to +50 C)
pub fn calculate_pt100_temp_c_x10(r_x100: u32) -> i16 {
    let r = r_x100 as f32 / 100.0;

    // Open circuit or disconnected probe protection
    if r > 390.0 || r < 10.0 {
        return -9999;
    }

    let temp_f: f32;
    if r >= 100.0 {
        // Above 0 C: Standard quadratic formula
        // R = R0 * (1 + A*T + B*T^2)
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
        let r2 = r * r;
        let r3 = r2 * r;
        temp_f = -242.02 + (2.2228 * r) + (2.5859e-3 * r2) - (4.8260e-6 * r3);
    }

    (temp_f * 10.0) as i16
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pt100_cryogenic_and_ambient_points() {
        assert_eq!(calculate_pt100_temp_c_x10(10000), 0); // 100.00 Ohm -> 0.0 C
        let cryogen = calculate_pt100_temp_c_x10(2025); // 20.25 Ohm (~LN2 -196 C)
        assert!((-1970..=-1950).contains(&cryogen), "Expected ~-196.0 C, got {}", cryogen);
        let room = calculate_pt100_temp_c_x10(10973); // 109.73 Ohm (+25.0 C)
        assert!((248..=252).contains(&room), "Expected ~+25.0 C, got {}", room);
        assert_eq!(calculate_pt100_temp_c_x10(900), -9999);
        assert_eq!(calculate_pt100_temp_c_x10(40000), -9999);
    }

    #[test]
    fn test_eval_rtd_reading_fault_mapping() {
        let ok = Max31865Reading {
            raw_adc: 1500,
            resistance_x100: 2025,
            temp_c_x10: -1960,
            fault_status: 0,
            is_fault: false,
        };
        assert_eq!(eval_rtd_reading(&ok), (-1960, 0));

        let open = Max31865Reading {
            raw_adc: 32767,
            resistance_x100: 42999,
            temp_c_x10: -9999,
            fault_status: 0x80,
            is_fault: true,
        };
        assert_eq!(eval_rtd_reading(&open), (-9999, 1));

        let short = Max31865Reading {
            raw_adc: 0,
            resistance_x100: 0,
            temp_c_x10: -9999,
            fault_status: 0x40,
            is_fault: true,
        };
        assert_eq!(eval_rtd_reading(&short), (-9999, 2));

        let spi_disconnected = Max31865Reading {
            raw_adc: 0,
            resistance_x100: 0,
            temp_c_x10: -9999,
            fault_status: 0x00,
            is_fault: false,
        };
        assert_eq!(eval_rtd_reading(&spi_disconnected), (-9999, 3));
    }
}

