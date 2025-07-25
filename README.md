<!-- SPDX-License-Identifier: MIT -->
<!-- SPDX-FileCopyrightText: Copyright 2025 Sam Blenny -->
# Fruit Jam Portable MIDI Synth

**DRAFT: WORK IN PROGRESS**

This code was developed and tested on CircuitPython 10.0.0-beta.0 with a
pre-release revision B Fruit Jam prototype. Keep in mind that things may change
by the time CircuitPython 10.0.0 is released.


## Important Board Revision Note

The I2S pinout changed between Fruit Jam board revision B and revision D. The
change got commited to CircuitPython between the 10.0.0-alpha.6 and
10.0.0-alpha.7 releases (see circuitpython
[commit 9dd53eb](https://github.com/adafruit/circuitpython/commit/9dd53eb6c34994dc7ef7e2a4f21dfd7c7d8dbbd9)).

Table of old and new I2S pins definitions:

| I2S Signal | Rev B Pin           | Rev D Pin |
| ---------- | ------------------- | --------- |
| I2S_MCLK   | GPIO27 (rev D WS)   | GPIO25    |
| I2S_BCLK   | GPIO26 (same)       | GPIO26    |
| I2S_WS     | GPIO25 (rev D MCLK) | GPIO27    |
| I2S_DIN    | GPIO24 (same)       | GPIO24    |

Since I'm developing this on a rev B board, the code checks an environment
variable to allow for swapping the pins.  If you have a rev D or later board,
you can ignore the I2S pinout change. **But, if you have a rev B board
(pre-production prototype), you need to add** `FRUIT_JAM_BOARD_REV = "B"` **in
your CIRCUITPY/settings.toml file**. Otherwise, the code won't have any way to
detect that it needs to swap the I2S pins.
