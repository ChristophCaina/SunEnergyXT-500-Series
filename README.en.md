# SunEnergyXT 500 Series
 
[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
 
## Language / Sprache
 
- [Deutsch](README.md)
- [English](README.en.md) (Default)
## Blueprints
 
- [Grid-Beneficial Charging Management (EN)](/blueprints/readme.md)
## Introduction
 
SunEnergyXT 500 Series is a custom integration for Home Assistant. It enables discovery, monitoring and control of AIO devices from the SunEnergyXT 500 Series on the local network.
 
The full reference for the local API, examples for `MD` meter connection strings and `TZ` timezone values can be found in [API.md](API.md).
 
## Features
 
- Automatic device discovery via Zeroconf or manual setup via IP address
- Monitoring of PV input, grid port power, load port power, battery level, firmware versions and other real-time data
- Adjustment of commonly used settings such as `GS`, `IS`, `SI`, `SA`, `SO` and `PT`
- Configuration of local mode, `MM` local self-consumption, `MD` local smart meter connection and the timezone field `TZ`
- **Automatic self-consumption control via any Home Assistant sensor** – no dedicated smart meter at the device required
- Restart the device directly from Home Assistant
## Installation
 
### Installation via HACS (recommended)
 
1. Open HACS in Home Assistant
2. Click the three dots in the top right and select "Custom repositories"
3. Enter the repository URL: https://github.com/SunEnergyXT/SunEnergyXT-500-Series
4. Select "Integration" as the category
5. Click "Add"
6. Search for "SunEnergyXT 500 Series"
7. Click "Download"
8. Restart Home Assistant
### Manual Installation
 
1. Download the latest [release package](https://github.com/SunEnergyXT/SunEnergyXT-500-Series/releases)
2. Extract it to `config/custom_components/`
3. Make sure the target directory is `config/custom_components/sunenergyxt/`
4. Restart Home Assistant
#### Example final directory structure
 
```text
custom_components
    ├── sunenergyxt
        ├── __init__.py
        ├── button.py
        ├── config_flow.py
        ├── const.py
        ├── coordinator.py
        ├── manifest.json
        ├── number.py
        ├── sensor.py
        ├── switch.py
        ├── text.py
        └── translations
            ├── de.json
            ├── en.json
```
 
## Configuration
 
1. Go to "Settings" > "Devices & Services" in Home Assistant
2. Click "Add Integration"
3. Search for `SunEnergyXT 500 Series`
4. Follow the setup dialog
   - If the device is discovered automatically, simply confirm the discovery
   - If the device is not found automatically, enter the IP address manually
5. The integration reads SN and model automatically – no manual entry required
6. **Optional:** Select a Home Assistant sensor as the grid power source (see next section)
Notes:
 
- Home Assistant and the device must be on the same local network
- If using automatic discovery, the network must allow mDNS / Zeroconf
- After changing a control value, the final state should be confirmed via the next update or a re-read
## Automatic Self-Consumption Control via HA Sensor
 
The integration supports optional, vendor-independent self-consumption control via any Home Assistant power sensor.  
<img width="561" height="449" alt="grafik" src="https://github.com/user-attachments/assets/b439c8b6-c5b6-4e99-bd60-da3aaed401fe" />
 
Option with a single sensor (Standard or Inverted)  
<img width="601" height="780" alt="grafik" src="https://github.com/user-attachments/assets/bd69e3c8-774c-4c89-9822-392f9ed90067" />
 
Option with separate sensors for grid feed-in and grid import  
<img width="590" height="420" alt="grafik" src="https://github.com/user-attachments/assets/4388a593-b688-4c89-aae1-4d7140b563d1" />
 
### How does it work?
 
By default, the device's local self-consumption mode (`MM`) only supports certain smart meters directly (Shelly Pro 3EM, EcoTracker, Tasmota/BitShake). Users with a different energy meter – such as **SolarEdge Modbus**, **Tibber Pulse**, **Volkszähler** or another integration – can use a Home Assistant grid power sensor directly.
 
The integration automatically registers a **local HTTP endpoint** in Home Assistant that exposes the sensor data in Shelly-compatible JSON format. The device polls this endpoint directly and uses its **internal PID controller** for regulation – fast, stable and without oscillation. No additional measuring device at the storage system required.
 
```
HA Sensor (e.g. SolarEdge Meter)
        ↓
HA local HTTP proxy
  GET /api/sunenergyxt_proxy/{id}/status
  → {"total_power": <Watts>}
        ↓
Device (MM=1, MD=Proxy-URL)
  internal PID controller
        ↓
Automatic charge/discharge control
```
<img width="639" height="205" alt="grafik" src="https://github.com/user-attachments/assets/b55928cd-479c-4378-bd6a-f6088dd5908a" />
Automatic population of the **Local Meter Data Format** text field  
<img width="244" height="86" alt="grafik" src="https://github.com/user-attachments/assets/973dcc91-9279-45f9-a7ae-3df93e0d947c" />
 
### Setup
 
In the last step of the setup dialog, an optional entity selector appears:
 
> **Grid Power Sensor (optional)**
> Select a Home Assistant sensor that provides the current grid power in Watts.
 
Select the sensor that measures the current grid power at your house connection point. The field can be left empty – in that case the existing behaviour is unchanged.
 
After configuration, the integration automatically writes the `MD` connection string and activates `MM=1` on the device. When the integration is removed, `MM` is automatically disabled.
 
### Sign Convention
 
#### Single Sensor – Standard
| Value | Meaning |
|-------|---------|
| **Positive** | Feed-in to grid (surplus) |
| **Negative** | Import from grid |
 
#### Single Sensor – Inverted*
| Value | Meaning |
|-------|---------|
| **Positive** | Import from grid |
| **Negative** | Feed-in to grid (surplus) |
 
#### Dual Sensors (Import + Export)*
| Sensor | Value | Meaning |
|--------|-------|---------|
| Import sensor | **Positive** | Import from grid – export sensor = 0 W |
| Export sensor | **Positive** | Feed-in to grid – import sensor = 0 W |
 
Example:
- Surplus 500 W: Import = 0 W, Export = 500 W → `500 - 0 = +500 W`
- Grid import 300 W: Import = 300 W, Export = 0 W → `0 - 300 = -300 W`
\* The integration automatically converts the sensor values to the sign convention required by the device.
 
> **Note:** Check the sign of your sensor before configuration.
> Many integrations (e.g. SolarEdge Modbus Multi) already provide the grid power in the standard convention (positive = feed-in).
 
### Examples of compatible sensors
 
| Source | Typical Entity ID |
|--------|------------------|
| SolarEdge Modbus Multi (HACS) | `sensor.solaredge_i1_m1_ac_power` |
| Shelly Pro 3EM | `sensor.shelly_pro3em_total_active_power` |
| Tibber Pulse | `sensor.tibber_power` |
| Volkszähler / SML | depends on integration |
| ESPHome (IR reader head) | depends on configuration |
 
## Entity Description
 
Notes:
 
- The actually visible entities may vary slightly depending on model, firmware version and number of expansion modules
- Energy counters are typically provided by the device as raw `Wh`; the integration displays them as `kWh`
- `TZ` must be provided as a POSIX timezone string, not as a country, city or abbreviation such as `CEST`
### Sensor
 
| Entity ID | Name | Unit | Description |
|-----------|------|------|-------------|
| `WS` | Wi-Fi SSID | - | Diagnostic information about the Wi-Fi connection |
| `WR` | Wi-Fi Signal Strength | dB | Current Wi-Fi signal strength |
| `ST` | System Status | - | Operating status of the device. Common values: `0 = Shutdown`, `1 = Standby`, `2 = Running`, `3 = Upgrading` |
| `IW` | System Total Input Power | W | Current total system input power |
| `OP` | System Total Output Power | W | Current total system output power |
| `PV` | PV Total Input Power | W | Total PV input power across all MPPT channels |
| `PV1` | PV 1 Input Power | W | PV input power from MPPT channel 1 |
| `PV2` | PV 2 Input Power | W | PV input power from MPPT channel 2 |
| `PV3` | PV 3 Input Power | W | PV input power from MPPT channel 3 |
| `PV4` | PV 4 Input Power | W | PV input power from MPPT channel 4 |
| `II1` | PV 1 Input Current | A | Input current from MPPT channel 1 |
| `II2` | PV 2 Input Current | A | Input current from MPPT channel 2 |
| `II3` | PV 3 Input Current | A | Input current from MPPT channel 3 |
| `II4` | PV 4 Input Current | A | Input current from MPPT channel 4 |
| `VP1` | PV 1 Input Voltage | V | Input voltage from MPPT channel 1 |
| `VP2` | PV 2 Input Voltage | V | Input voltage from MPPT channel 2 |
| `VP3` | PV 3 Input Voltage | V | Input voltage from MPPT channel 3 |
| `VP4` | PV 4 Input Voltage | V | Input voltage from MPPT channel 4 |
| `GP` | System Grid Port Power | W | Power at the grid connection point. Positive values typically indicate feed-in, negative values grid import or grid charging |
| `LP` | System Load Port Power | W | Current power at the load port |
| `GD1` | Today's Grid Charge Energy | kWh | Energy charged from the grid into the system today |
| `GD2` | Today's Grid Feed-in Energy | kWh | Energy fed into the grid via the grid port today |
| `LD` | Today's Off-grid Output Energy | kWh | Off-grid output energy delivered today |
| `SC` | System Battery Level | % | Total system SOC |
| `SC0` | Head Storage | % | SOC of the head unit |
| `SC1` | Expansion Storage 1 | % | SOC of expansion module 1 |
| `SC2` | Expansion Storage 2 | % | SOC of expansion module 2 |
| `SC3` | Expansion Storage 3 | % | SOC of expansion module 3 |
| `SC4` | Expansion Storage 4 | % | SOC of expansion module 4 |
| `SC5` | Expansion Storage 5 | % | SOC of expansion module 5 |
| `ON` | System Battery Pack Online Count | - | Number of currently online battery packs |
| `ES` | Firmware Version (Wi-Fi) | - | System Wi-Fi / EMS firmware version |
| `AS` | Firmware Version (AC Unit) | - | AC unit firmware version |
| `DS` | Firmware Version (DC Unit) | - | DC unit firmware version |
| `BS0` | Firmware Version (BMS 0) | - | BMS firmware version of the head unit |
| `BS1` | Firmware Version (BMS 1) | - | BMS firmware version of expansion module 1 |
| `BS2` | Firmware Version (BMS 2) | - | BMS firmware version of expansion module 2 |
| `BS3` | Firmware Version (BMS 3) | - | BMS firmware version of expansion module 3 |
| `BS4` | Firmware Version (BMS 4) | - | BMS firmware version of expansion module 4 |
| `BS5` | Firmware Version (BMS 5) | - | BMS firmware version of expansion module 5 |
| `SN` | System Host SN | - | Device serial number |
| `MS` | Meter Status | - | Connection status of the local smart meter. Common values: `0 = Unbound`, `1 = Online`, `2 = Offline`; some firmware versions also report `3 = IP request in progress` |
 
### Number
 
| Entity ID | Name | Unit | Range | Step | Description |
|-----------|------|------|-------|------|-------------|
| `GS` | System Grid Port Power Setpoint | W | `-2400` to `2400` | `10` | Setpoint for grid port power. When a grid sensor is configured, this value is regulated internally by the device. |
| `IS` | System Max Inverter Power Setpoint | W | `1` to `2400` | `10` | Maximum inverter output power. The upper limit is `800 W` for SunEnergyXT 500 and `2400 W` for SunEnergyXT 500 Pro |
| `SI` | System Min Discharge SOC | % | `1` to `30` | `1` | Minimum SOC for discharging in on-grid operation |
| `SA` | System Max Charge SOC | % | `70` to `100` | `1` | Maximum SOC for charging in on-grid operation |
| `SO` | System Load Port Discharge Limit SOC | % | `1` to `30` | `1` | Minimum SOC for discharging in off-grid / load port operation |
| `PT` | System Auto-Shutdown Time Setting | min | `30` to `1440` | `1` | Time for automatic shutdown |
 
### Switch
 
| Entity ID | Name | Description |
|-----------|------|-------------|
| `LM` | Local Mode | Switch for local mode. When active, the device prioritises local configuration |
| `MM` | Local Zero Feed-in Mode | Switch for local self-consumption mode. Activated automatically when a grid sensor is configured. |
| `PM` | System Parallel Mode | Switch for parallel operation. Only use when the device topology and firmware support this |
 
### Text
 
| Entity ID | Name | Description |
|-----------|------|-------------|
| `MD` | Local Meter Data Format | JSON string for the local smart meter connection. Set automatically when a grid sensor is configured. |
| `TZ` | System Time Zone | POSIX timezone string. For China, e.g. `CST-8`; for Germany with daylight saving time, e.g. `CET-1CEST,M3.5.0,M10.5.0/3`. |
 
### Button
 
| Entity ID | Name | Description |
|-----------|------|-------------|
| `RT` | System Restart | Sends a restart command to the device |
 
## Changes compared to the original SunEnergyXT integration
 
### Reconfiguration
The integration now supports "Reconfigure", allowing changes to the grid sensor configuration without having to remove and re-add the integration.  
<img width="789" height="334" alt="grafik" src="https://github.com/user-attachments/assets/4fb9262d-5fc3-4805-a58b-d39f615b282b" />
 
### Sensor Classification and Home Assistant Standards
1. All units are now derived from Home Assistant constants (`UnitOfPower`, `UnitOfEnergy`, `UnitOfElectricCurrent`, `UnitOfElectricPotential`, `PERCENTAGE`, `SIGNAL_STRENGTH_DECIBELS`).  
This enables internal unit conversion.  
<img width="488" height="475" alt="grafik" src="https://github.com/user-attachments/assets/3395ed70-614d-4934-bc4c-62504a388949" />
2. `SensorDeviceClass` has been added for relevant sensors
3. All energy sensors have been equipped with their `state_class`.  
These are: `TOTAL_INCREASING` and `MEASUREMENT`, which enables integration into the Energy Dashboard and long-term statistics in Home Assistant.  
<img width="566" height="468" alt="grafik" src="https://github.com/user-attachments/assets/f572daa3-337e-4f36-8d99-246ed9168313" />
### Sensor Reorganisation
In the original integration, almost all sensors were grouped under `Diagnostic`.  
The integration now distinguishes between "Controls", "Sensors", "Configuration" and "Diagnostic" – and hides less relevant sensors by default.  
<img width="296" height="732" alt="grafik" src="https://github.com/user-attachments/assets/e8668918-6963-4e03-99a7-2ddea40c972c" />
<img width="290" height="632" alt="grafik" src="https://github.com/user-attachments/assets/32386ac5-832e-40cb-a7b3-dac19ea0b25b" />
<img width="291" height="545" alt="grafik" src="https://github.com/user-attachments/assets/12e64b20-6c8a-4dd4-8905-94bf2b54eaba" />
<img width="293" height="251" alt="grafik" src="https://github.com/user-attachments/assets/ebd54eed-e1c3-45a8-aa59-cfa42383fccf" />
 
## Troubleshooting
 
### Device not found
 
- Make sure the device is powered on and connected to the local network
- Make sure Home Assistant and the device are on the same network segment
- If automatic discovery fails, enter the IP address manually
- If the network blocks mDNS / Zeroconf, automatic discovery may not work
### Data update issues
 
- Check that the device's network connection is stable
- Check that `http://device-ip/read` is directly reachable
- After a change, always confirm the final state via a re-read
### Self-consumption control not working (MS = Unbound)
 
- Check that the configured sensor provides a valid numeric value in Watts
- Check that Home Assistant is reachable from the device: `curl http://ha-ip:8123/api/sunenergyxt_proxy/{entry_id}/status`
- Make sure `LM` (Local Mode) is enabled
- Check the HA logs for error messages (`Logger: custom_components.sunenergyxt`)
### Local self-consumption not working (without HA sensor)
 
- Make sure `MD` exactly matches the meter example in [API.md](API.md)
- Make sure `MM` is enabled
- Check whether `MS` reports an online meter and whether real meter data is being updated
- Do not rely on `MD` as a guaranteed echo after writing
### Timezone is set incorrectly
 
- `TZ` must be set as a POSIX timezone string
- Do not use `Europe/Berlin`, `UTC+1`, `CET` or `CEST` as the final `TZ` value
- For Germany, a POSIX string with a daylight saving rule should be used, e.g. `CET-1CEST,M3.5.0,M10.5.0/3`
- After writing, confirm the resulting timezone effect rather than expecting an exact echo of the written `TZ` value
## Contributing
 
Contributions are welcome. Please submit issues or pull requests on [GitHub](https://github.com/SunEnergyXT/SunEnergyXT-500-Series).
 
## License
 
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
 
[releases-shield]: https://img.shields.io/github/release/SunEnergyXT/SunEnergyXT-500-Series.svg
[releases]: https://github.com/SunEnergyXT/SunEnergyXT-500-Series/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/SunEnergyXT/SunEnergyXT-500-Series.svg
[commits]: https://github.com/SunEnergyXT/SunEnergyXT-500-Series/commits/main
[license-shield]: https://img.shields.io/github/license/SunEnergyXT/SunEnergyXT-500-Series.svg
