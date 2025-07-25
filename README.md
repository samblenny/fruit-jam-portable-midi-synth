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

| I2S Signal | Rev B Pin | Rev C Pin         |
| ---------- | --------- | ----------------- |
| I2S_MCLK   | GPIO27    | GPIO25 (old WS)   |
| I2S_BCLK   | GPIO26    | GPIO26 (same)     |
| I2S_WS     | GPIO25    | GPIO27 (old MCLK) |
| I2S_DIN    | GPIO24    | GPIO24 (same)     |
| I2S_IRQ    | n/a       | GPIO23 (new)      |

Since I'm developing this on a rev B board, the code checks an environment
variable to allow for swapping the pins.  If you have a rev C or later board,
you can ignore the I2S pinout change. **But, if you have a rev B board
(pre-production prototype), you need to add** `FRUIT_JAM_BOARD_REV = "B"` **in
your CIRCUITPY/settings.toml file**. Otherwise, the code won't have any way to
detect that it needs to swap the I2S pins.
