# SPDX-FileCopyrightText: 2026 Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Hardware test: one-shot (take_single_measurement) regression guard.

Guards the Data_Ready poll-hang fix (issue #10). In one-shot the part returns to SHUTDOWN
the instant its single conversion completes, so polling the clear-on-read Data_Ready bit
could lose the flag on the completion edge and spin forever. The fix waits the
deterministic conversion time instead of polling.

The guard runs many one-shots across averaging settings and asserts each returns an
in-range value within a time bound. If the poll hang is ever reintroduced,
take_single_measurement() blocks, this file never reaches the ``~~END~~`` line, and the
harness times out -- a clean failure signal.

Set DEMONSTRATE_ORIGINAL_BUG = True to also reproduce the pre-fix behavior (bounded so it
can't hang the run). Stalls printed there are the bug reproducing and are informational --
they are NOT counted as test failures.
"""

import time

import board
import busio

import adafruit_tmp117
from adafruit_tmp117 import AverageCount

passed = 0
failed = 0


def test(name, condition):
    global passed, failed
    if condition:
        print(f"PASS: {name}")
        passed += 1
    else:
        print(f"FAIL: {name}")
        failed += 1


# Set True to also demonstrate the pre-fix poll-hang (slower; intermittent stalls).
DEMONSTRATE_ORIGINAL_BUG = False

# MOD=11 one-shot trigger (matches adafruit_tmp117._ONE_SHOT_MODE; defined locally so the
# test doesn't import a private module constant).
_ONE_SHOT_MODE = 0b11

# ~15.5 ms typ / 17.5 ms max active conversion per averaged sample (datasheet ref 5/7).
_SINGLE_CONVERSION_MAX_S = 0.0175

# Regression guard: (averaging code, iterations) -- fewer iters for slower settings.
GUARD_ITERATIONS = (
    (AverageCount.AVERAGE_1X, 100),
    (AverageCount.AVERAGE_8X, 30),
    (AverageCount.AVERAGE_32X, 10),
)

DEMO_AVG = AverageCount.AVERAGE_8X  # higher averaging => stalls reproduce faster
DEMO_ITERS = 60

TEMP_MIN_C = -55.0
TEMP_MAX_C = 150.0


def expected_one_shot_seconds(avg_code):
    """Deterministic worst-case time for one one-shot at the given averaging code."""
    return AverageCount.string[avg_code] * _SINGLE_CONVERSION_MAX_S + 0.002


def original_one_shot(sensor, timeout_s):
    """Recreate the PRE-FIX one-shot path: trigger, then poll clear-on-read Data_Ready.

    Returns the temperature, or None if it stalled (issue #10). The timeout exists ONLY so
    this demonstration detects the hang instead of hanging. Reaches into driver internals
    on purpose to recreate the old code path.
    """
    sensor._mode = _ONE_SHOT_MODE
    deadline = time.monotonic() + timeout_s
    while not sensor._read_status()[2]:
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.001)
    return sensor._read_temperature()


try:
    i2c = board.STEMMA_I2C()  # built-in STEMMA QT / Qwiic (most QtPy + Feather boards)
except Exception:
    i2c = None

try:
    if i2c is None:
        i2c = busio.I2C(board.SCL, board.SDA)  # fall back to the board's SCL/SDA pins
    sensor = adafruit_tmp117.TMP117(i2c)
    test("Sensor found", True)

    print("\n=== TMP117 One-Shot Regression Test ===\n")

    if DEMONSTRATE_ORIGINAL_BUG:
        print("--- Demonstration: original (pre-fix) polling behavior ---")
        sensor.averaged_measurements = DEMO_AVG
        timeout_s = expected_one_shot_seconds(DEMO_AVG) * 6 + 0.3
        stalls = 0
        for i in range(DEMO_ITERS):
            if original_one_shot(sensor, timeout_s) is None:
                stalls += 1
                print(f"  [{i + 1}] STALLED: Data_Ready never observed <- issue #10")
        print(f"  (informational) original path stalled {stalls}/{DEMO_ITERS} times\n")

    print("--- Regression guard: fixed take_single_measurement() ---")
    print("  (if the poll hang returns, this blocks and ~~END~~ never prints)")
    for avg_code, iters in GUARD_ITERATIONS:
        sensor.averaged_measurements = avg_code
        samples = AverageCount.string[avg_code]
        bound_s = expected_one_shot_seconds(avg_code) * 1.5 + 0.05
        worst_s = 0.0
        out_of_range = 0
        for _ in range(iters):
            start = time.monotonic()
            temp = sensor.take_single_measurement()
            elapsed = time.monotonic() - start
            worst_s = max(worst_s, elapsed)
            if not TEMP_MIN_C <= temp <= TEMP_MAX_C:
                out_of_range += 1
        test(f"x{samples}: {iters} one-shots all in range", out_of_range == 0)
        test(
            f"x{samples}: worst call {worst_s:.3f}s within bound {bound_s:.3f}s",
            worst_s <= bound_s,
        )

    print()
    print(f"=== Summary: {passed} passed, {failed} failed ===")
    print("ALL TESTS PASSED" if passed > 0 and failed == 0 else "SOME TESTS FAILED")

except Exception as e:
    print(f"FAIL: Unhandled exception: {e}")
    failed += 1

print("~~END~~")
