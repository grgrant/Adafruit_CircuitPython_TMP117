# SPDX-FileCopyrightText: 2020 Bryan Siepert, written for Adafruit Industries
#
# SPDX-License-Identifier: Unlicense
import time

import board

import adafruit_tmp117

# First try the popular STEMMA_I2C on Feathers and QtPy among others
try:
    i2c = board.STEMMA_I2C()  # Built-in STEMMA QT connector
except Exception:  # noqa: BLE001 - board may not expose STEMMA_I2C
    i2c = None
# If not available then try the board.I2C
if i2c is None:
    i2c = board.I2C()  # uses board.SCL and board.SDA

tmp117 = adafruit_tmp117.TMP117(i2c)


def _c_to_f(tempc):
    return tempc * 9 / 5 + 32


while True:
    tempc = tmp117.temperature
    print(f"Temperature: {tempc:.2f} degrees C {_c_to_f(tempc):.2f} degrees F")
    time.sleep(1)
