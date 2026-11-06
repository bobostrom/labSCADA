#!/usr/bin/env python3
import asyncio
import logging
import subprocess
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("UPS_Modbus")

# 16 holding registers starting at address 0 (40001 to 40016)
block = ModbusSequentialDataBlock(0, [0] * 16)
store = ModbusSlaveContext(hr=block)
context = ModbusServerContext(slaves=store, single=True)

def parse_ups_data():
    try:
        out = subprocess.check_output(["upsc", "apc@localhost"], timeout=3).decode("utf-8")
        data = {}
        for line in out.strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip()
        return data
    except Exception as e:
        logger.error(f"Error reading from upsc: {e}")
        return None

def execute_ups_cmd(cmd_name):
    try:
        logger.info(f"Executing UPS command: {cmd_name}")
        res = subprocess.check_output(["upscmd", "-u", "monuser", "-p", "labmon", "apc", cmd_name], timeout=3).decode("utf-8")
        logger.info(f"Command {cmd_name} result: {res.strip()}")
        return True
    except Exception as e:
        logger.error(f"Failed to execute command {cmd_name}: {e}")
        return False

async def check_command_loop():
    logger.info("Starting command listener on register 40010 (offset 9)...")
    while True:
        try:
            # Register offset 9 (Holding register 40010) is command register
            cmd = context[0].getValues(3, 9, 1)[0]
            if cmd != 0:
                logger.info(f"Received command code: {cmd}")
                if cmd == 1:
                    execute_ups_cmd("beeper.mute")
                elif cmd == 2:
                    execute_ups_cmd("beeper.disable")
                elif cmd == 3:
                    execute_ups_cmd("beeper.enable")
                # Reset command register back to 0
                context[0].setValues(3, 9, [0])
        except Exception as e:
            logger.error(f"Error checking command: {e}")
        await asyncio.sleep(0.2)

async def poll_ups_loop():
    logger.info("Starting UPS polling loop...")
    while True:
        data = parse_ups_data()
        if data:
            status_str = data.get("ups.status", "")
            status_word = 0
            if "OL" in status_str:
                status_word |= (1 << 0)  # Bit 0: Online / Grid OK
            if "OB" in status_str:
                status_word |= (1 << 1)  # Bit 1: On Battery
            if "LB" in status_str:
                status_word |= (1 << 4)  # Bit 4: Low Battery

            try:
                charge = int(float(data.get("battery.charge", 0)))
            except:
                charge = 0

            try:
                runtime_sec = int(float(data.get("battery.runtime", 0)))
                runtime_sec_clamped = min(65535, runtime_sec)
                runtime_min = min(65535, runtime_sec // 60)
            except:
                runtime_sec_clamped = 0
                runtime_min = 0

            try:
                volts_x10 = int(float(data.get("input.voltage", 0)) * 10)
            except:
                volts_x10 = 0

            try:
                load = int(float(data.get("ups.load", 0)))
            except:
                load = 0

            try:
                batt_v_x10 = int(float(data.get("battery.voltage", 0)) * 10)
            except:
                batt_v_x10 = 0

            # Beeper status: 1=enabled, 2=muted, 3=disabled
            beeper_str = data.get("ups.beeper.status", "").lower()
            if "enabled" in beeper_str:
                beeper_status = 1
            elif "muted" in beeper_str:
                beeper_status = 2
            elif "disabled" in beeper_str:
                beeper_status = 3
            else:
                beeper_status = 0

            # Registers 0 to 7:
            # 0: Status Word
            # 1: Battery % (0-100)
            # 2: Runtime (sec)
            # 3: Line Voltage * 10
            # 4: Inverter Load %
            # 5: Battery Voltage * 10
            # 6: Runtime (minutes)
            # 7: Beeper Status (1=enabled, 2=muted, 3=disabled)
            reg_values = [
                status_word,
                charge,
                runtime_sec_clamped,
                volts_x10,
                load,
                batt_v_x10,
                runtime_min,
                beeper_status
            ]
            context[0].setValues(3, 0, reg_values)
        await asyncio.sleep(1.0)

async def main():
    logger.info("Starting Modbus TCP server on port 502 with command handler...")
    asyncio.create_task(poll_ups_loop())
    asyncio.create_task(check_command_loop())
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", 502))

if __name__ == "__main__":
    asyncio.run(main())

