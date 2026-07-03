"""
Constants for SunEnergyXT 500 Series integration.

This module defines constant values used throughout the SunEnergyXT integration.

Constants:
- DOMAIN: The integration domain name
- HOST_PREFIX: Prefix for SunEnergyXT device hostnames
- HOST_SUFFIX: Suffix for SunEnergyXT device hostnames
"""

DOMAIN = "sunenergyxt"
HOST_PREFIX = "SunEnergyXT_AIO_"
HOST_SUFFIX = ".local"

CONF_GRID_SENSOR = "grid_sensor_entity_id"

# Multi-phase meter configuration (see proxy.py). CONF_GRID_SENSOR is kept
# as the legacy single-sensor / "total" input for backward compatibility —
# existing single-phase configs keep working unchanged.
CONF_PHASE_A_SENSOR = "phase_a_sensor_entity_id"
CONF_PHASE_B_SENSOR = "phase_b_sensor_entity_id"
CONF_PHASE_C_SENSOR = "phase_c_sensor_entity_id"

# Which Shelly-schema field this Kopfspeicher instance's MD should point
# at. "total" is the default and matches pre-multi-phase behaviour.
CONF_METER_PHASE = "meter_phase"
METER_PHASE_TOTAL = "total"
METER_PHASE_A = "a"
METER_PHASE_B = "b"
METER_PHASE_C = "c"
METER_PHASE_OPTIONS = [
    METER_PHASE_TOTAL,
    METER_PHASE_A,
    METER_PHASE_B,
    METER_PHASE_C,
]

# Maps a meter_phase value to the corresponding field in the proxy's
# Shelly EM.GetStatus-compatible JSON output.
METER_PHASE_FIELD_MAP = {
    METER_PHASE_TOTAL: "total_act_power",
    METER_PHASE_A: "a_act_power",
    METER_PHASE_B: "b_act_power",
    METER_PHASE_C: "c_act_power",
}
