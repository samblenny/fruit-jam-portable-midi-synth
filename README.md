<!-- SPDX-License-Identifier: MIT -->
<!-- SPDX-FileCopyrightText: Copyright 2025 Sam Blenny -->
# Fruit Jam Portable MIDI Synth

**DRAFT: WORK IN PROGRESS**

This code was developed and tested on CircuitPython 10.0.0-beta.0 with a
pre-release revision B Fruit Jam prototype. Keep in mind that things may change
by the time CircuitPython 10.0.0 is released.


## Important Board Revision Note

The I2S pinout changed between Fruit Jam board revision B and revision C.
CircuitPython 10.0.0-alpha.6 defines board.I2S_BLCK and board.I2S_MCLK using
the rev B pinout. As of 10.0.0-alpha.7, the pin definitions use the new rev C
pinout. Since I'm developing this on a rev B board, the code checks an
environment variable to allow for swapping the pins.

If you have a rev C or later board, you can ignore the I2S pinout change.
**But, if you have a rev B board (pre-production prototype), you need to add**
`FRUIT_JAM_BOARD_REV = "B"` **in your CIRCUITPY/settings.toml file**.
Otherwise, the code won't have any way to detect that it needs to swap the I2S
pins.
