# SunEnergyXT 500 Series

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

## Language / Sprache / 语言

- [English](README.md) (default)
- [中文](README.zh.md)
- [Deutsch](README.de.md)

## Introduction

SunEnergyXT 500 Series is a custom integration for Home Assistant that allows you to monitor and control SunEnergyXT 500 series inverters.

## Features

- Monitor real-time status and data of the inverter
- Control various modes and settings of the inverter
- Adjust parameters of the inverter
- Support automatic device discovery via Zeroconf

## Installation

### Install via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner and select "Custom repositories"
3. Enter the repository address: https://github.com/GLORYFeonix/SunEnergyXT_500_Series
4. Select "Integration" as the category
5. Click "Add"
6. Search for "SunEnergyXT 500 Series"
7. Click "Download"
8. Restart Home Assistant

### Manual Installation

1. Download the latest [release package](https://github.com/SunEnergyXT/SunEnergyXT-500-Series/releases)
2. Extract to `config/custom_components/` directory
3. Ensure the directory structure is `config/custom_components/sunenergyxt/`
4. Restart Home Assistant

#### Final Directory Structure Example

```
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
            └── zh-Hans.json
```

## Configuration

1. In Home Assistant, go to "Configuration" > "Devices & Services"
2. Click "+ Add Integration"
3. Search for "SunEnergyXT 500 Series"
4. Follow the prompts to complete the configuration process
   - Enter the IP address of the inverter
   - Enter the serial number of the inverter

## Entity Description

### Sensor

| Entity ID | Name | Unit | Description |
|-----------|------|------|-------------|
| WS | Work Status | - | Work status of the inverter |
| WR | Work Mode | - | Work mode of the inverter |
| ST | System Time | - | System time of the inverter |
| IW | Input Power | W | Input power of the inverter |
| OP | Output Power | W | Output power of the inverter |
| PV | PV Total Power | W | Total photovoltaic power |
| PV1 | PV String 1 Power | W | Power of photovoltaic string 1 |
| PV2 | PV String 2 Power | W | Power of photovoltaic string 2 |
| PV3 | PV String 3 Power | W | Power of photovoltaic string 3 |
| PV4 | PV String 4 Power | W | Power of photovoltaic string 4 |
| II1 | Input Current 1 | A | Input current 1 |
| II2 | Input Current 2 | A | Input current 2 |
| II3 | Input Current 3 | A | Input current 3 |
| II4 | Input Current 4 | A | Input current 4 |
| VP1 | Input Voltage 1 | V | Input voltage 1 |
| VP2 | Input Voltage 2 | V | Input voltage 2 |
| VP3 | Input Voltage 3 | V | Input voltage 3 |
| VP4 | Input Voltage 4 | V | Input voltage 4 |
| GP | Grid Power | W | Grid power |
| LP | Load Power | W | Load power |
| GD1 | Grid Generation Total | kwh | Total grid generation |
| GD2 | Grid Generation Total 2 | kwh | Total grid generation 2 |
| LD | Load Consumption Total | kwh | Total load consumption |
| SC | System Status | % | System status |
| SC0 | System Status 0 | % | System status 0 |
| SC1 | System Status 1 | % | System status 1 |
| SC2 | System Status 2 | % | System status 2 |
| SC3 | System Status 3 | % | System status 3 |
| SC4 | System Status 4 | % | System status 4 |
| SC5 | System Status 5 | % | System status 5 |
| ON | Online Status | - | Online status of the inverter |
| ES | Error Status | - | Error status of the inverter |
| BS0 | Battery Status 0 | - | Battery status 0 |
| BS1 | Battery Status 1 | - | Battery status 1 |
| BS2 | Battery Status 2 | - | Battery status 2 |
| BS3 | Battery Status 3 | - | Battery status 3 |
| BS4 | Battery Status 4 | - | Battery status 4 |
| BS5 | Battery Status 5 | - | Battery status 5 |
| AS | Alarm Status | - | Alarm status of the inverter |
| DS | Device Status | - | Device status |
| SN | Serial Number | - | Serial number of the inverter |
| MS | Manufacturer | - | Manufacturer of the inverter |

### Number

| Entity ID | Name | Unit | Range | Step | Description |
|-----------|------|------|-------|------|-------------|
| GS | Grid Power Setting | W | -2400 to 2400 | 10 | Grid power setting |
| IS | Input Power Setting | W | 1 to 2400 | 10 | Input power setting |
| SI | Start Charging Current | % | 1 to 30 | 1 | Start charging current |
| SA | Charging Termination Voltage | % | 70 to 100 | 1 | Charging termination voltage |
| SO | Discharging Termination Voltage | % | 1 to 30 | 1 | Discharging termination voltage |
| PT | Protection Time | min | 30 to 1440 | 1 | Protection time |

### Button

| Entity ID | Name | Description |
|-----------|------|-------------|
| RT | Restart | Restart the inverter |

### Switch

| Entity ID | Name | Description |
|-----------|------|-------------|
| LM | Light Mode | Light mode switch |
| MM | Mute Mode | Mute mode switch |
| PM | Power Mode | Power mode switch |

### Text

| Entity ID | Name | Description |
|-----------|------|-------------|
| MD | Model | Model of the inverter |
| TZ | Time Zone | Time zone setting of the inverter |

## Troubleshooting

### Device Not Found

- Ensure the inverter is powered on and connected to the network
- Ensure Home Assistant and the inverter are on the same network segment
- Try manually entering the inverter's IP address

### Data Update Issues

- Check if the network connection is stable
- Check if the inverter is working normally
- Try restarting the inverter and Home Assistant

## Contribution

Contributions are welcome! Please submit issues or pull requests on [GitHub](https://github.com/GLORYFeonix/SunEnergyXT_500_Series).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

[releases-shield]: https://img.shields.io/github/release/GLORYFeonix/SunEnergyXT_500_Series.svg
[releases]: https://github.com/GLORYFeonix/SunEnergyXT_500_Series/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/GLORYFeonix/SunEnergyXT_500_Series.svg
[commits]: https://github.com/GLORYFeonix/SunEnergyXT_500_Series/commits/main
[license-shield]: https://img.shields.io/github/license/GLORYFeonix/SunEnergyXT_500_Series.svg
