# SPDX-FileCopyrightText: 2020 Bryan Siepert, written for Adafruit Industries
# SPDX-FileCopyrightText: 2024 one-shot regression guard additions
#
# SPDX-License-Identifier: Unlicense
"""
TMP117 one-shot regression test / demonstration.

Background
----------
``take_single_measurement()`` triggers a one-shot conversion. The pre-fix code then
polled the **clear-on-read** Data_Ready bit (config register) to detect completion. In
one-shot mode the part returns to SHUTDOWN the instant its single conversion finishes, so
a Data_Ready that gets cleared by a poll read landing on the conversion-complete edge is
never re-asserted -- and the poll loop hangs forever
(Adafruit_CircuitPython_TMP117 issue #10). The fix waits the deterministic conversion
time instead of polling.

What this script does
---------------------
* **Part A** reproduces the ORIGINAL polling path (reaching into driver internals on
  purpose) *with a timeout* so the demo itself can't hang, and counts stalls. On affected
  hardware you'll see it stall intermittently -- that's the bug.
* **Part B** is the regression guard: it hammers the FIXED ``take_single_measurement()``
  across averaging settings and asserts every call returns a sane value within a
  reasonable time. If the polling regression is ever reintroduced, Part B will instead
  hang here (it stops printing) -- that hang is the failure signal on hardware.

Flash it to a board with a TMP117/TMP119 and watch the serial console. Expect roughly a
minute of runtime. Part A intentionally touches ``_mode`` / ``_read_status`` /
``_read_temperature`` to recreate the pre-fix code path; that's acceptable in a test.
"""

import time

import board

from adafruit_tmp117 import TMP117, AverageCount

# MOD=11 one-shot trigger, matching adafruit_tmp117._ONE_SHOT_MODE. Defined locally so the
# test doesn't import a private module constant.
_ONE_SHOT_MODE = 0b11

# ~15.5 ms typ / 17.5 ms max active conversion per averaged sample (datasheet ref 5/7).
_SINGLE_CONVERSION_MAX_S = 0.0175

# Part B: how many one-shots to run per averaging setting (kept short for slow settings).
ITERATIONS = (
    (AverageCount.AVERAGE_1X, 200),
    (AverageCount.AVERAGE_8X, 60),
    (AverageCount.AVERAGE_32X, 20),
)

# Part A: higher averaging => more poll reads per conversion => stalls reproduce faster.
ORIGINAL_DEMO_AVG = AverageCount.AVERAGE_8X
ORIGINAL_DEMO_ITERS = 100

# TMP117/TMP119 spec operating range; a reading outside this is a failure (e.g. the
# -256 C uninitialized sentinel).
TEMP_MIN_C = -55.0
TEMP_MAX_C = 150.0


def expected_one_shot_seconds(avg_code):
    """Deterministic worst-case time for one one-shot at the given averaging code."""
    samples = AverageCount.string[avg_code]
    return samples * _SINGLE_CONVERSION_MAX_S + 0.002


def original_one_shot(tmp, timeout_s):
    """Recreate the PRE-FIX one-shot path: trigger, then poll clear-on-read Data_Ready.

    Returns the measured temperature, or ``None`` if it stalled (reproduces issue #10).
    The timeout exists ONLY so this demonstration detects the hang instead of hanging.
    """
    tmp._mode = _ONE_SHOT_MODE  # trigger one-shot (internal)
    deadline = time.monotonic() + timeout_s
    while not tmp._read_status()[2]:  # poll Data_Ready (internal, clear-on-read)
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.001)
    return tmp._read_temperature()


def part_a_demonstrate_original(tmp):
    print("== Part A: original (pre-fix) polling behavior ==")
    tmp.averaged_measurements = ORIGINAL_DEMO_AVG
    samples = AverageCount.string[ORIGINAL_DEMO_AVG]
    # Generous per-read timeout: many times the expected conversion so a real conversion
    # is never mistaken for a stall.
    timeout_s = expected_one_shot_seconds(ORIGINAL_DEMO_AVG) * 6 + 0.3
    print("  averaging x{}, per-read timeout {:.2f}s, {} iterations".format(
        samples, timeout_s, ORIGINAL_DEMO_ITERS))

    stalls = 0
    first_stall = None
    for i in range(ORIGINAL_DEMO_ITERS):
        result = original_one_shot(tmp, timeout_s)
        if result is None:
            stalls += 1
            if first_stall is None:
                first_stall = i + 1
            print("  [{}] STALLED: Data_Ready never observed <- reproduces issue #10".format(i + 1))

    if stalls:
        print("  -> original path stalled {}/{} times (first at #{}).".format(
            stalls, ORIGINAL_DEMO_ITERS, first_stall))
    else:
        print("  -> no stall this run; the race is probabilistic. Try more iterations or")
        print("     higher averaging. The fixed path below avoids the race entirely.")
    print("")


def part_b_regression_guard(tmp):
    print("== Part B: regression guard on fixed take_single_measurement() ==")
    print("  (if the polling bug returns, this section HANGS instead of finishing)")
    failures = 0
    for avg_code, iters in ITERATIONS:
        tmp.averaged_measurements = avg_code
        samples = AverageCount.string[avg_code]
        bound_s = expected_one_shot_seconds(avg_code) * 1.5 + 0.05
        worst_s = 0.0
        for i in range(iters):
            start = time.monotonic()
            temp = tmp.take_single_measurement()
            elapsed = time.monotonic() - start
            if elapsed > worst_s:
                worst_s = elapsed
            if elapsed > bound_s:
                failures += 1
                print("  x{} [{}] SLOW: {:.3f}s > bound {:.3f}s".format(
                    samples, i + 1, elapsed, bound_s))
            if not TEMP_MIN_C <= temp <= TEMP_MAX_C:
                failures += 1
                print("  x{} [{}] OUT OF RANGE: {:.2f} C".format(samples, i + 1, temp))
        print("  averaging x{:<2} {} reads OK (worst call {:.3f}s, bound {:.3f}s)".format(
            samples, iters, worst_s, bound_s))
    print("")
    return failures


def main():
    # First try the popular STEMMA_I2C on Feathers and QtPy among others
    try:
        i2c = board.STEMMA_I2C()  # Built-in STEMMA QT connector
    except Exception:  # noqa: BLE001 - board may not expose STEMMA_I2C
        i2c = None
    if i2c is None:
        i2c = board.I2C()  # uses board.SCL and board.SDA

    tmp117 = TMP117(i2c)
    print("TMP117/TMP119 found. Starting one-shot regression test.\n")

    part_a_demonstrate_original(tmp117)
    failures = part_b_regression_guard(tmp117)

    if failures == 0:
        print("REGRESSION GUARD: PASS -- every one-shot completed with a sane value, no stalls.")
    else:
        print("REGRESSION GUARD: FAIL -- {} problem(s) detected.".format(failures))


main()
