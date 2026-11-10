//! Driver for MAX31855 Cold-Junction Compensated Thermocouple-to-Digital Converter
//! Read-only SPI (SCK, MISO, CS)

use esp_hal::delay::Delay;
use esp_hal::gpio::{Input, Output};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum FaultType {
    None = 0,
    OpenCircuit = 1,
    ShortToGnd = 2,
    ShortToVcc = 3,
    HardwareError = 4,
}

#[derive(Debug, Clone, Copy)]
pub struct Max31855Reading {
    pub raw: u32,
    pub temp_c_x10: i16,
    pub ambient_c_x10: i16,
    pub fault: FaultType,
}

pub struct Max31855<'a> {
    sck: Output<'a>,
    cs: Output<'a>,
    miso: Input<'a>,
}

impl<'a> Max31855<'a> {
    pub fn new(mut sck: Output<'a>, mut cs: Output<'a>, miso: Input<'a>) -> Self {
        cs.set_high();
        sck.set_low();
        Self { sck, cs, miso }
    }

    pub fn read_raw(&mut self, delay: &Delay) -> u32 {
        self.sck.set_low();
        self.cs.set_high();
        delay.delay_millis(1);

        self.cs.set_low();
        delay.delay_micros(10);

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

    pub fn read(&mut self, delay: &Delay) -> Max31855Reading {
        let raw = self.read_raw(delay);

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

        let temp_raw = ((raw >> 18) & 0x3FFF) as u16;
        let temp_c_x10 = if (temp_raw & 0x2000) != 0 {
            let signed_val = (temp_raw as i32) - 16384;
            ((signed_val * 10) / 4) as i16
        } else {
            (((temp_raw as i32) * 10) / 4) as i16
        };

        let ambient_raw = ((raw >> 4) & 0x0FFF) as u16;
        let ambient_c_x10 = if (ambient_raw & 0x0800) != 0 {
            let signed_amb = (ambient_raw as i32) - 4096;
            ((signed_amb * 10) / 16) as i16
        } else {
            (((ambient_raw as i32) * 10) / 16) as i16
        };

        Max31855Reading {
            raw,
            temp_c_x10,
            ambient_c_x10,
            fault,
        }
    }
}
