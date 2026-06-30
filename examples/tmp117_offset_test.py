# SPDX-FileCopyrightText: 2020 Bryan Siepert, written for Adafruit Industries
#
# SPDX-License-Identifier: Unlicense
import time

import board

import adafruit_tmp117

# First try the popular STEMMA_I2C on Feathers and QtPy among others
try:
    i2c = board.STEMMA_I2C()  # Built-in STEMMA QT connector
except Exception:
    i2c = None

# If not available then try the board.I2C
if i2c is None:
    i2c = board.I2C()  # uses board.SCL and board.SDA

tmp117 = adafruit_tmp117.TMP117(i2c)

print(f"Temperature without offset: {tmp117.temperature:.2f} degrees C")
tmp117.temperature_offset = 10.0
time.sleep(0.5)  # Let settle
while True:
    print(f"Temperature w/ offset: {tmp117.temperature:.2f} degrees C")
    time.sleep(1)
