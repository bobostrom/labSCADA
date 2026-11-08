//! Driver for MAX31855 Cold-Junction Compensated Thermocouple-to-Digital Converter
//!
//! Pin assignments for Seeed Studio XIAO ESP32-S3:
//! - SCK:  D8 (GPIO 7)
//! - MISO: D9 (GPIO 8)
//! - CS:   D1 (GPIO 2)

use esp_hal::delay::Delay;
use esp_hal::gpio::{Input, Output};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum FaultType {
    None = 0,
    OpenCircuit = 1,     // Bit 0: D0 OC (Thermocouple disconnected)
    ShortToGnd = 2,      // Bit 1: D1 SCG (Thermocouple shorted to GND)
    ShortToVcc = 3,      // Bit 2: D2 SCV (Thermocouple shorted to VCC)
    HardwareError = 4,   // Bit 16: General fault or communication bus unresponsive
}

#[derive(Debug, Clone, Copy)]
pub struct Max31855Reading {
    /// Raw 32-bit SPI word
    pub raw: u32,
    /// Thermocouple temperature in tenths of a °C (-1954 = -195.4 °C, -9999 = Sentinel)
    pub temp_c_x10: i16,
    /// Cold-junction (ambient cleanroom board) temperature in tenths of a °C (245 = 24.5 °C)
    pub ambient_c_x10: i16,
    /// Detailed fault code
    pub fault: FaultType,
}

pub struct Max31855<'a> {
    sck: Output<'a>,
    cs: Output<'a>,
    miso: Input<'a>,
}

impl<'a> Max31855<'a> {
    pub fn new(sck: Output<'a>, cs: Output<'a>, miso: Input<'a>) -> Self {
        let mut dev = Self { sck, cs, miso };
        dev.cs.set_high();
        dev.sck.set_low();
        dev
    }

    /// Read raw 32-bit register from MAX31855 over bit-banged SPI with bit-level timing
    pub fn read_raw(&mut self, delay: &Delay) -> u32 {
        self.sck.set_low();
        self.cs.set_high();
        delay.delay_millis(1);

        self.cs.set_low();
        delay.delay_micros(10); // tCSS: CS setup time

        let mut raw = 0u32;
        for _ in 0..32 {
            self.sck.set_high();
            delay.delay_micros(5);
            let bit = if self.miso.is_high() { 1 } else { 0 };
            raw = (raw << 1) | bit;
            self.sck.set_low();
            delay.delay_micros(5);
        }

        self.cs.set_high();
        delay.delay_micros(10);
        raw
    }

    /// Read and decode temperature and fault diagnostics
    pub fn read(&mut self, delay: &Delay) -> Max31855Reading {
        let raw = self.read_raw(delay);

        // If bus is unpowered or floating completely:
        if raw == 0 || raw == 0xFFFF_FFFF {
            return Max31855Reading {
                raw,
                temp_c_x10: -9999,
                ambient_c_x10: -9999,
                fault: FaultType::OpenCircuit,
            };
        }

        let fault_bit = (raw & 0x0001_0000) != 0;
        let oc_bit = (raw & 0x0000_0001) != 0;
        let scg_bit = (raw & 0x0000_0002) != 0;
        let scv_bit = (raw & 0x0000_0004) != 0;

        let fault = if oc_bit {
            FaultType::OpenCircuit
        } else if scg_bit {
            FaultType::ShortToGnd
        } else if scv_bit {
            FaultType::ShortToVcc
        } else if fault_bit {
            FaultType::HardwareError
        } else {
            FaultType::None
        };

        // Cold junction (ambient) temperature in bits 15..4 (12-bit signed, 0.0625 °C/LSB)
        let raw_cj = ((raw << 16) as i32) >> 20;
        let ambient_c_x10 = (raw_cj * 5 / 8) as i16;

        // Thermocouple temperature in bits 31..18 (14-bit signed, 0.25 °C/LSB)
        let raw_tc = (raw as i32) >> 18;
        let temp_c_x10 = if fault != FaultType::None {
            -9999 // Sentinel for invalid / faulted reading
        } else {
            (raw_tc * 25 / 10) as i16
        };

        Max31855Reading {
            raw,
            temp_c_x10,
            ambient_c_x10,
            fault,
        }
    }
}

