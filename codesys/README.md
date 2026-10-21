# CODESYS PLC Integration (Raspberry Pi 4 & WAGO PFC200)

This directory stores the CODESYS project, exported IEC 61131-3 Structured Text logic, and integration guides for the IVF Laboratory SCADA telemetry system.

---

## 1. Directory Structure

```
codesys/
├── README.md               # Architecture, setup instructions, and troubleshooting
├── projects/               # CODESYS binary project archives (*.project, *.projectarchive)
└── src/                    # Exported Structured Text (*.st) source files for Git version control
    └── PLC_PRG.st          # Main program (LED heartbeat + IVF telemetry simulation)
```

---

## 2. Setting Up the Blinker in CODESYS (Structured Text)

The program in [`src/PLC_PRG.st`](file:///home/bobostrom/Projects/labSCADA/codesys/src/PLC_PRG.st) uses standard IEC 61131-3 `TON` timers to toggle `bLedOutput` every 500ms (1 Hz blink frequency).

### Step-by-Step in CODESYS Development System:

1. **Add the POU to MainTask:**
   - In the CODESYS project tree, expand **Task Configuration** -> **MainTask**.
   - Ensure `PLC_PRG` is added to the list of called POUs.
   - Set the task cycle time (e.g., `t#20ms` or `t#50ms`).

2. **Connecting to the Hardware (Raspberry Pi 4 vs External LED):**
   > [!IMPORTANT]
   > **Raspberry Pi 4 Onboard ACT LED Note:**
   > On Raspberry Pi 4, the green ACT LED is connected through a power-management expander chip (`rpi-exp-gpio`), and the Linux kernel defaults its trigger to SD card activity (`mmc0`). 
   > 
   > For hardware I/O verification, the standard CODESYS method is using the **40-pin GPIO header** (e.g. GPIO 17 / Pin 11, or GPIO 22 / Pin 15):
   >
   > 1. In CODESYS Device tree, right-click **Device** -> **Add Device...** -> select **GPIOs (Raspberry Pi)**.
   > 2. Double-click **GPIOs** -> go to **GPIOs Parameters**:
   >    - Set your target pin (e.g., `GPIO17`) mode to **Output**.
   > 3. Go to **GPIOs I/O Mapping**:
   >    - Expand the output channels and map the pin to `PLC_PRG.bLedOutput` (or double-click the variable column and select it).
   > 4. **CRITICAL SETTING:** At the bottom right of the I/O Mapping tab, change:
   >    - **"Always update variables"** from *Disabled* to **Enabled 2 (always in bus cycle task)** or **Enabled 1**.
   >    *(If left on Disabled, CODESYS optimizes out the I/O writes during runtime).*

3. **Login and Start:**
   - Select **Online** -> **Login** (or `Alt + F8`).
   - Choose **Download** or **Online Change**.
   - If the controller is in **STOP** mode (orange indicator), press **F5** or click the **Start / Run** button (green arrow in the toolbar).

---

## 3. Alternative: Blinking the Physical Onboard ACT LED via Linux Trigger

If you want the green onboard LED on `codesyspi02.local` to blink directly without wiring to the header pins:
1. SSH into the Pi or run via bash:
   ```bash
   # Release kernel MMC trigger
   echo none | sudo tee /sys/class/leds/ACT/trigger
   # Turn ON
   echo 1 | sudo tee /sys/class/leds/ACT/brightness
   # Turn OFF
   echo 0 | sudo tee /sys/class/leds/ACT/brightness
   ```
2. In CODESYS, you can add the library **SysProcess** and call `SysProcessExecuteCommand2` to write `1` or `0` to `/sys/class/leds/ACT/brightness` upon `bLedOutput` transitions.

---

## 4. Git Version Control Best Practices for CODESYS

Because CODESYS `.project` files are proprietary binary databases, Git cannot generate clean diffs on them.
To maintain version history:
1. Save your master project file in `codesys/projects/` (e.g., `codesys/projects/IVF_Lab_Telemetry.project`).
2. When saving major revisions, export your POUs and GVLs as Structured Text (`.st` / `.txt`) into `codesys/src/` (Right-click POU -> *Export...*).
3. This ensures all logic changes can be reviewed in git diffs and pull requests.

---

## 5. Upcoming Transition Roadmap

1. **OPC UA Server Setup in CODESYS:**
   - Add **Symbol Configuration** under the Application.
   - Check the variables:
     * `PLC_PRG.rLabAmbientTemp` (~25°C)
     * `PLC_PRG.rMedFridgeTemp` (~3°C)
     * `PLC_PRG.rMedFreezerTemp` (~ -20°C)
     * `PLC_PRG.rCryoTankTemp` (~ -150°C)
     * `PLC_PRG.bDoor01_MainDoor` (BOOL)
     * `PLC_PRG.bDoor02_CryoLabDoor` (BOOL)
     * `PLC_PRG.bIncubator01_Alarm` (BOOL)
     * `PLC_PRG.bIncubator02_Alarm` (BOOL)
     * `PLC_PRG.bLedOutput` (Heartbeat BOOL)
   - The embedded OPC UA server publishes these nodes on port `4840`.
2. **Rapid SCADA Integration:**
   - Configure Rapid SCADA's `DrvOpcUa` to connect to `opc.tcp://codesyspi02.local:4840`.
   - Map OPC UA tags directly to Rapid SCADA channels.
3. **WAGO 750-8212 (PFC200) Migration:**
   - When the WAGO hardware arrives, right-click **Device** in CODESYS and select **Update Device...** -> select **WAGO 750-8212**.
   - The application logic (`PLC_PRG.st`), OPC UA symbol configuration, and telemetry data structures will carry over directly with zero changes.
4. **Grafana Dashboard:**
   - Create a dedicated dashboard JSON in this repository pointing to the new device data without altering the existing dashboard.
5. **Pushover Notification Daemon:**
   - Configure Pushover REST API triggers for critical alarm channels.
