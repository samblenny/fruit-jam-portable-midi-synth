# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# Related Docs:
# - https://docs.circuitpython.org/projects/tlv320/en/latest/api.html
# - https://learn.adafruit.com/adafruit-tlv320dac3100-i2s-dac/overview
# - https://docs.circuitpython.org/en/latest/docs/environment.html
# - https://docs.circuitpython.org/en/latest/shared-bindings/audiobusio/
# - https://docs.circuitpython.org/en/latest/shared-bindings/audiomixer/
# - https://midi.org/specs
# - https://github.com/todbot/circuitpython-synthio-tricks
#
from audiobusio import I2SOut
from board import (
    I2C, I2S_BCLK, I2S_DIN, I2S_MCLK, I2S_WS, PERIPH_RESET
)
from digitalio import DigitalInOut, Direction, Pull
import displayio
import gc
from micropython import const
import os
import synthio
import sys
from time import sleep
from usb.core import USBError, USBTimeoutError
import usb_host

from adafruit_tlv320 import TLV320DAC3100

from sb_usb_midi import find_usb_device, MIDIInputDevice


# DAC and Synthesis parameters
SAMPLE_RATE = const(11025)
CHAN_COUNT  = const(2)
BUFFER_SIZE = const(1024)
#==============================================================
# CAUTION! When this is set to True, the headphone jack will
# send a line-level output suitable use with a mixer or powered
# speakers, but that will be _way_ too loud for earbuds. For
# finer control of volume, you can set dac.dac_volume below.
LINE_LEVEL  = const(False)
#==============================================================

# Change this to True if you want more MIDI output on the serial console
DEBUG = False


def init_dac_audio_synth(i2c):
    # Configure TLV320 I2S DAC for audio output and make a Synthesizer.
    # - i2c: a reference to board.I2C()
    # - returns tuple: (dac: TLV320DAC3100, audio: I2SOut, synth: Synthesizer)
    #
    # The I2S pinout changed between Fruit Jam board revision B and revision D.
    # The change got committed to CircuitPython between the 10.0.0-alpha.6 and
    # 10.0.0-alpha.7 releases (see commit 9dd53eb).
    #
    # Table of old and new I2S pins definitions:
    #   | I2S Signal | Rev B Pin           | Rev D Pin |
    #   | ---------- | ------------------- | --------- |
    #   | I2S_MCLK   | GPIO27 (rev D WS)   | GPIO25    |
    #   | I2S_BCLK   | GPIO26 (same)       | GPIO26    |
    #   | I2S_WS     | GPIO25 (rev D MCLK) | GPIO27    |
    #   | I2S_DIN    | GPIO24 (same)       | GPIO24    |
    #
    # Since I'm developing this on a rev B board, the code checks an
    # environment variable to allow for swapping the pins. If you have a rev B
    # board, you need to add `FRUIT_JAM_BOARD_REV = "B"` in your
    # CIRCUITPY/settings.toml file.
    #
    # You could easily modify this for a Metro RP2350 with a TLV320 DAC
    # breakout board. To do that, first change the `from board import ...` line
    # up top to match the pins you want to use. Then change this function to
    # have an `audio = I2SOut(bit_clock=...)` line for your pinout.
    #
    # 1. Reset DAC (reset is active low)
    rst = DigitalInOut(PERIPH_RESET)
    rst.direction = Direction.OUTPUT
    rst.value = False
    sleep(0.1)
    rst.value = True
    sleep(0.05)
    # 2. Configure sample rate, bit depth, and output port
    dac = TLV320DAC3100(i2c)
    dac.configure_clocks(sample_rate=SAMPLE_RATE, bit_depth=16)
    dac.speaker_mute = True
    dac.headphone_output = True
    # 3. Set volume for for line-level or headphone level
    print("Initial dac_volume", dac.dac_volume)
    print("Initial headphone_volume", dac.headphone_volume)
    if LINE_LEVEL:
        # This gives a line output level suitable for plugging into a mixer or
        # the AUX input of a powered speaker (THIS IS TOO LOUD FOR HEADPHONES!)
        dac.dac_volume = -44
        dac.headphone_volume = -64
    else:
        # This is a reasonable volume for my cheap JVC Gumy earbuds. They tend
        # to be louder than other headphones, so probably this ought to be a
        # generally safe volume level. For headphones that need a stronger
        # signal, carefully increase dac_volume (closer to 0 is louder).
        dac.dac_volume = -58
        dac.headphone_volume = -64
    print("Current dac_volume", dac.dac_volume)
    print("Current headphone_volume", dac.headphone_volume)
    # 4. Initialize I2S, checking environment variable to control swapping of
    #    the MCLK and WS from their default values (for rev B prototype boards)
    # =====
    # To adapt this for Metro RP2350, this is where you would modify the code
    # with an `audio = I2SOut(...)` line to match the pinout for your DAC. You
    # would also need to change the `from board import ...` line up top.
    # =====
    if os.getenv("FRUIT_JAM_BOARD_REV") == "B":
        print("USING FRUIT JAM REV B BOARD: SWAPPING I2S PINS!")
        audio = I2SOut(bit_clock=I2S_BCLK, word_select=I2S_MCLK, data=I2S_DIN)
    else:
        print("Using default I2S pin definitions (board rev D or newer)")
        audio = I2SOut(bit_clock=I2S_BCLK, word_select=I2S_WS, data=I2S_DIN)
    # 5. Configure synthio patch to generate audio
    vca = synthio.Envelope(
        attack_time=0.002, decay_time=0.01, sustain_level=0.4,
        release_time=0, attack_level=0.6
    )
    synth = synthio.Synthesizer(
        sample_rate=SAMPLE_RATE, channel_count=CHAN_COUNT, envelope=vca
    )
    audio.play(synth)
    return (dac, audio, synth)


def main():
    # Turn off the default DVI display to free up CPU
    displayio.release_displays()
    gc.collect()

    # Set up the audio stuff for a basic synthesizer
    i2c = I2C()
    (dac, audio, synth) = init_dac_audio_synth(i2c)

    # Cache function references (MicroPython performance boost trick)
    fast_wr = sys.stdout.write
    panic = synth.release_all
    press = synth.press
    release = synth.release

    # Main loop: scan USB host bus for MIDI device, connect, start event loop.
    # This grabs the first MIDI device it finds. Reset board to re-scan bus.
    while True:
        fast_wr("USB Host: scanning bus...\n")
        gc.collect()
        device_cache = {}
        try:
            # This loop will end as soon as it finds a ScanResult object (r)
            r = None
            while r is None:
                sleep(0.4)
                r = find_usb_device(device_cache)
            # Use ScanResult object (r) to check if USB device descriptor info
            # matches the class/subclass/protocol pattern for a MIDI device. If
            # the device doesn't match, MIDIInputDevice will raise an exception
            # and trigger another iteration through the outer while True loop.
            dev = MIDIInputDevice(r)
            fast_wr(" found MIDI device vid:pid %04X:%04X\n" % (r.vid, r.pid))
            # Collect garbage to hopefully limit heap fragmentation.
            r = None
            device_cache = {}
            gc.collect()
            # MIDI Event Input Loop: Poll for input until USB error.
            #
            # CAUTION: This loop needs to be as efficient as possible. Any
            # extra work here directly adds time to USB latency.
            #     As I write this on July 26, 2025, using CircuitPython
            # 10.0.0-beta.0, this code produces stuck or dropped notes
            # relatively often. I'm not sure about how it's happening, but my
            # guess is it has to do with interactions in the CircuitPython core
            # between interrupts for audio and the USB stack.
            #    If anybody feels inspired to dig into what's going on, by all
            # means, please do! To reproduce the problem, just hook up a USB
            # MIDI keyboard and bang away for a while. within a minute or two
            # you should get some stuck or dropped notes.
            #
            cin = chan = num = val = 0x00
            for data in dev.input_event_generator():
                # Begin handling midi packet which should be None or a 4-byte
                # memoryview.
                if data is None:
                    continue

                # data[0] has CN (Cable Number) and CIN (Code Index Number). By
                # discarding CN with `& 0x0f`, we ignore the virtual MIDI port
                # that the messages arrive from. Ignoring CN would be bad for a
                # fancy DAW or synth setup where you needed to route MIDI
                # among multiple devices. But, that doesn't matter here. We do
                # need CIN to distinguish between note on, note off, Control
                # Change (CC), and so on. For the channel, adding 1 gives us
                # human-friendly channel numbers in the range of 1 to 16.
                #
                cin = data[0] & 0x0f
                chan = (data[1] & 0xf) + 1
                num = data[2]
                val = data[3]

                # This decodes MIDI events by comparing constants against bytes
                # from a memoryview. Using a class to do this parsing would add
                # many extra heap allocations and dictionary lookups. That
                # stuff is slow, and we want to go _fast_. For details about
                # the MIDI 1.0 standard, see https://midi.org/specs
                #
                if cin == 0x08 and (21 <= num <= 108):
                    # Note off
                    release(num)
                elif cin == 0x09 and (21 <= num <= 108):
                    # Note on
                    press(num)
                elif cin == 0x0b and num == 123 and val == 0:
                    # CC 123 means stop all notes ("panic")
                    panic()
                    fast_wr('PANIC %d %d %d\n' % (chan, num, val))
                if DEBUG:
                    if cin == 0x08:
                        # Note On
                        fast_wr('Off %d %d %d\n' % (chan, num, val))
                    elif cin == 0x09:
                        # Note Off
                        fast_wr('On  %d %d %d\n' % (chan, num, val))
                    elif cin == 0x0b:
                        # CC control change
                        fast_wr('CC  %d %d %d\n' % (chan, num, val))
                    elif cin == 0x0a:
                        # MPE polyphonic key pressure (aftertouch)
                        fast_wr('MPE %d %d %d\n' % (chan, num, val))
                    elif cin == 0x0d:
                        # CP channel key pressure (aftertouch)
                        fast_wr('CP  %d %d %d\n' % (chan, num, val))
                    elif cin == 0x0e:
                        # PB pitch bend
                        fast_wr('PB  %d %d %d\n' % (chan, num, val))
                    # Ignore the rest: SysEx, System Realtime, or whatever
        except USBError as e:
            # This sometimes happens when devices are unplugged. Not always.
            print("USBError: '%s' (device unplugged?)" % e)
            show_scan_msg = True
        except ValueError as e:
            # This can happen if an initialization handshake glitches
            print(e)
            show_scan_msg = True


main()
