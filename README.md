<!-- SPDX-License-Identifier: MIT -->
<!-- SPDX-FileCopyrightText: Copyright 2025 Sam Blenny -->
# Fruit Jam Portable MIDI Synth

This is a minimalist polyphonic square wave synth for Fruit Jam that's intended
for portable use with a USB power bank. The only output is audio to the board's
headphone jack. The only input is from a USB MIDI controller connected to the
board's USB host port. To set the volume, you can edit the code.

The main interesting thing about this project is that it demonstrates how to
make a CircuitPython synth with MIDI events coming from the USB host interface
rather than a USB device interface or UART MIDI. Also, this works as a good
stress test of the CircuitPython USB host stack in combination with audio
output using I2S and synthio.

This code was developed and tested on CircuitPython 10.0.0-beta.0 with a
pre-release revision B Fruit Jam prototype which uses a different I2S pinout
from the current rev D boards. Keep in mind that what's written here may be out
of date by the time CircuitPython 10.0.0 is released and the production
revision of the Fruit Jam boards become available from the shop.


## Known Issues

1. Stuck and Dropped Notes

   As I write this on July 26, 2025, running on CircuitPython 10.0.0-beta.0,
   this code produces stuck or dropped notes relatively often. I'm not sure
   about how it's happening, but my guess is it has to do with interactions in
   the CircuitPython core between interrupts for audio and the USB stack.

   If anybody feels inspired to dig into what's going on, please do! To
   reproduce the problem, just hook up a USB MIDI keyboard and bang away for a
   while. Within a minute or two you should get some stuck or dropped notes.

2. Audio on Left Headphone Channel Only

   I developed this code on a Fruit Jam rev B prototype board, so its I2S
   pinout is different than on the latest rev D boards. On my rev B, I'm only
   getting audio output on the left channel of my headphone jack. After
   checking all the cabling and software level stuff I could find to check, I
   still don't know what the problem is. So, I'm guessing there may be a
   hardware issue with my prototype board. There's a fair chance that the code
   is fine and it will produce stereo audio on production boards once they
   become available from the shop.


## Usage

The code for this project is meant to be installed onto the CIRCUITPY drive of
a Fruit Jam board by either using the `make sync` make target of this repo's
[Makefile](Makefile) or by manually copying the project bundle files (see
releases page for .zip attachment of project bundle).

Important Configuration Notes:

1. **CAUTION**: The default DAC volume level is set up for a line level output
   to use with a mixer, powered speaker, or other device with its own volume
   adjustment capability. To use headphones, you need to edit
   [code.py](code.py) to set a lower value for `dac.dac_volume` (see comments
   in source code).

2. To use this code with a **rev B** prototype board, you need to edit your
   `CIRCUITPY/settingings.toml` file to include the line:

   ```
   FRUIT_JAM_BOARD_REV = "B"
   ```

   The code checks the `FRUIT_JAM_BOARD_REV` environment variable to decide if
   it can use the default I2S pinout or if it needs to swap pins.


After Configuration:

1. Connect a powered speaker, mixer, or whatever to the headphone jack

2. Power the board

3. Plug a USB MIDI controller to the USB host port

4. Wait a few seconds for the USB MIDI device to be detected

5. Play some notes


Troubleshooting:

If the above steps don't work for you, you can try connecting to the Fruit Jam
board's serial console using a serial monitor program like PyCharm, Mu, tio, or screen. On the serial console, check for status or error messages. If you try
to use a MIDI controller that requires the full 500 mA for USB 2.0, you might
have problems. In that case, you could try a powered USB hub or a USB OTG style
cable that splits power and data onto two different jacks.


## Suitable MIDI Controllers

For a portable battery powered setup, you'll want a MIDI controller that is
relatively small and that doesn't draw too much current. For discussion of the
pros and cons of various controllers, you can check forums like reddit or
modwiggler.

Based on my reading of forums, reviews, and manufacturer websites, I made the
list below with some controllers that might be suitable. I've only tried a
couple of these, but I've seen people online say that they like them (others
disagree). Keep in mind that 25 key keyboards have some inherent limitations,
caveat emptor, etc. Anyhow, in alphabetical order...

- Arturia MicroLab mk3
- Korg MicroKEY-25
- Korg NanoKEY2
- Korg NanoKEY Fold
- Korg NanoPAD2
- Muse Kinetics (Keith McMillen) K-Board C


## Suitable Speakers or Headphones

1. I've mostly been testing with a line-level signal out of the Fruit Jam
   into a small desktop mixer to drive a pair of cheap JVC Gumy earbuds.

2. It also works to plug the earbuds in directly, **BUT** you must edit the
   code to reduce the DAC volume.

3. It also works to use a Bluetooth speaker with 3.5mm aux input jack. But,
   watch out for speakers with silly DSP features that add lots of latency (some
   speakers have high latency even on the aux jack, so check reviews).

4. You could use small computer speakers that have a 3.5mm audio plug and a USB
   plug for power. For this to work, you might want a USB power bank with two
   charging output ports.


## Board Revision Note

The I2S pinout changed between Fruit Jam board revision B and revision D. The
change got committed to CircuitPython between the 10.0.0-alpha.6 and
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
