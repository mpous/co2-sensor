import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Mapping, Optional

import adafruit_scd30  # type: ignore
from adafruit_dps310.advanced import DPS310  # type: ignore
from adafruit_extended_bus import ExtendedI2C as I2C  # type: ignore

import paho.mqtt.client as mqtt


DEVICE_UUID = os.getenv("BALENA_DEVICE_UUID")
RESIN_DEVICE_TYPE = os.getenv("RESIN_DEVICE_TYPE")
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "1"))

LOGGER = logging.getLogger(__name__)


DEFAULT_I2C_BUS_ID = 11
I2C_BUS_ID_MAP: Mapping[Optional[str], int] = {"beaglebone-green-gateway": 2}

def get_i2c_bus_id() -> int:
    override = os.getenv("I2C_BUS_ID")
    if override is not None:
        logging.info("Using I2C bus override: %s", override)
        return int(override)

    retval = I2C_BUS_ID_MAP.get(RESIN_DEVICE_TYPE, DEFAULT_I2C_BUS_ID)
    logging.info("I2C bus for device type %s: %s", RESIN_DEVICE_TYPE, retval)
    return retval


def main() -> None:  # pylint: disable=missing-function-docstring
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO
    )

    client = mqtt.Client()
    try:
        logging.info("Trying to connect the MQTT client to mqtt:1883")
        client.connect("mqtt", 1883, 60)
    except Exception as e:
        logging.error("Error connecting to MQTT. ({0})".format(str(e)))
    else:
        client.loop_start()

    #i2c_bus_id = get_i2c_bus_id()
    #i2c = I2C(i2c_bus_id)
    i2c= I2C(DEFAULT_I2C_BUS_ID)
    
    scd = adafruit_scd30.SCD30(i2c)
    time.sleep(1)
    scd.ambient_pressure = 1007
    dps310 = DPS310(i2c)

    # Enable self calibration mode
    scd.temperature_offset = 4.0
    scd.altitude = 0
    scd.self_calibration_enabled = True

    while True:
        # Sleep at the top of the loop allows calling `continue` anywhere to skip this
        # cycle, without entering a busy loop
        time.sleep(POLL_INTERVAL_SECONDS)

        # since the measurement interval is long (2+ seconds) we check for new data
        # before reading the values, to ensure current readings.
        if not scd.data_available:
            continue

        # Set SCD Pressure from Barometer
        #
        # See Section 1.4.1 in SCD30 Interface Guide
        # https://www.sensirion.com/fileadmin/user_upload/customers/sensirion/Dokumente/9.5_CO2/Sensirion_CO2_Sensors_SCD30_Interface_Description.pdf
        #
        # The Reference pressure must be greater than 0.
        if dps310.pressure > 0:
            scd.ambient_pressure = dps310.pressure


        # Publish to Local MQTT Broker
        data = {}
        data["CO2"] = scd.CO2
        data["Temperature"] = scd.temperature
        data["Relative_Humidity"] = scd.relative_humidity
        data["scd_temp_offset"] = scd.temperature_offset
        data["baro_temp"] = dps310.temperature
        data["baro_pressure_hpa"] = dps310.pressure
        data["scd30_pressure_mbar"] = scd.ambient_pressure
        data["scd30_alt_m"] = scd.altitude

        logging.info(json.dumps(data))

        try:
            client.publish("sensors/" + DEVICE_UUID, json.dumps(data))
            logging.info("MQTT message published by "+ DEVICE_UUID)
        except Exception as e:
            logging.error("Error publishing to MQTT. ({0})".format(str(e)))
            


if __name__ == "__main__":
    main()
