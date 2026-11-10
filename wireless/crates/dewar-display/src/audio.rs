//! Imperial Legion Fanfare Startup Audio Driver using ESP32-S3 LEDC PWM
//! Drives onboard speaker / piezo buzzer on GPIO 4

use esp_hal::delay::Delay;
use esp_hal::ledc::{
    channel::{self, ChannelIFace},
    timer::{self, TimerIFace},
    LSGlobalClkSource, Ledc, LowSpeed,
};
use esp_hal::time::Rate;
use esp_hal::peripherals::{GPIO4, LEDC};

pub struct Note {
    pub freq_hz: u32,
    pub duration_ms: u32,
    pub pause_ms: u32,
    pub fade_out: bool,
}

// Concert Bb Roman Cornu / Tuba Fanfare
pub const ROMAN_FANFARE: &[Note] = &[
    Note { freq_hz: 233, duration_ms: 140, pause_ms: 20, fade_out: false }, // Bb3
    Note { freq_hz: 349, duration_ms: 140, pause_ms: 20, fade_out: false }, // F4
    Note { freq_hz: 466, duration_ms: 260, pause_ms: 40, fade_out: false }, // Bb4
    Note { freq_hz: 466, duration_ms: 110, pause_ms: 15, fade_out: false }, // Bb4
    Note { freq_hz: 587, duration_ms: 140, pause_ms: 20, fade_out: false }, // D5
    Note { freq_hz: 698, duration_ms: 600, pause_ms: 0,  fade_out: true  }, // F5 (breath decay)
];

pub fn play_startup_fanfare(ledc_peri: LEDC, gpio4: GPIO4, delay: &Delay) {
    let mut ledc = Ledc::new(ledc_peri);
    ledc.set_global_slow_clock(LSGlobalClkSource::APBClk);

    let mut lstimer0 = ledc.timer::<LowSpeed>(timer::Number::Timer0);
    let timer_ptr: *mut timer::Timer<'_, LowSpeed> = &mut lstimer0 as *mut _;
    let timer_ref: &timer::Timer<'_, LowSpeed> = unsafe { &*timer_ptr };

    let mut channel0 = ledc.channel(channel::Number::Channel0, gpio4);
    let _ = channel0.configure(channel::config::Config {
        timer: timer_ref,
        duty_pct: 0,
        drive_mode: esp_hal::gpio::DriveMode::PushPull,
    });

    for note in ROMAN_FANFARE {
        // Reconfigure timer frequency for each note
        unsafe {
            let _ = (*timer_ptr).configure(timer::config::Config {
                duty: timer::config::Duty::Duty10Bit,
                clock_source: timer::LSClockSource::APBClk,
                frequency: Rate::from_hz(note.freq_hz),
            });
        }

        let _ = channel0.set_duty(50);

        if note.fade_out {
            let step_ms = note.duration_ms / 20;
            for step in 0..20 {
                let duty = 50 - (step * 2);
                let _ = channel0.set_duty(duty as u8);
                delay.delay_millis(step_ms);
            }
        } else {
            delay.delay_millis(note.duration_ms);
        }

        // Mute between notes
        let _ = channel0.set_duty(0);
        if note.pause_ms > 0 {
            delay.delay_millis(note.pause_ms);
        }
    }
}
