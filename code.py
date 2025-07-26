# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# Related Docs:
# - https://docs.circuitpython.org/projects/tlv320/en/latest/api.html
# - https://learn.adafruit.com/adafruit-tlv320dac3100-i2s-dac/overview
# - https://docs.circuitpython.org/en/latest/docs/environment.html
# - https://docs.circuitpython.org/en/latest/shared-bindings/audiobusio/
# - https://docs.circuitpython.org/en/latest/shared-bindings/audiomixer/
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
#=============================================================
# DANGER!!! Set this to False if you want to use heaphones!!!
# When this is True, the headphone jack will send a line-level
# output suitable use with a mixer or powered speakers.
LINE_LEVEL  = const(True)
#=============================================================

# Change this to True if you want more MIDI output on the serial console
DEBUG = False


def main():
    # Turn off the default DVI display to free up CPU
    displayio.release_displays()
    gc.collect()

    # Configure TLV320DAC3100 I2S DAC for Audio Output.
    #
    # CAUTION: The I2S pinout changed between Fruit Jam board revision B and
    # revision D. The change got commited to CircuitPython between the
    # 10.0.0-alpha.6 and 10.0.0-alpha.7 releases (see commit 9dd53eb).
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
    # environment variable to allow for swapping the pins. IF YOU HAVE A REV D
    # OR LATER BOARD, YOU CAN IGNORE THIS. But, if you have a rev B board, you
    # need to add `FRUIT_JAM_BOARD_REV = "B"` in your CIRCUITPY/settings.toml
    # file.

    # 1. Reset DAC (reset is active low)
    rst = DigitalInOut(PERIPH_RESET)
    rst.direction = Direction.OUTPUT
    rst.value = False
    sleep(0.1)
    rst.value = True
    sleep(0.05)

    # 2. Configure sample rate, bit depth, and output port
    i2c = I2C()
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
        # WARNING: This is a reasonable volume for my cheap JVC Gumy earbuds.
        # They tend to be louder than other headpones, so probably this ought
        # to be a safe volume level. BUT BE CAREFUL! Try it with headphones
        # away from your ears to begin with.
        dac.dac_volume = -64
        dac.headphone_volume = -64
    print("Current dac_volume", dac.dac_volume)
    print("Current headphone_volume", dac.headphone_volume)

    # 4. Initialize I2S, checking environment variable to control swapping of
    #    the MCLK and WS from their default values (for rev C+ boards)
    if os.getenv("FRUIT_JAM_BOARD_REV") == "B":
        print("USING FRUIT JAM REV B BOARD: SWAPPING I2S PINS!")
        audio = I2SOut(bit_clock=I2S_BCLK, word_select=I2S_MCLK, data=I2S_DIN)
    else:
        print("Using default I2S pin definitions (not a rev B board)")
        audio = I2SOut(bit_clock=I2S_BCLK, word_select=I2S_WS, data=I2S_DIN)

    # Configure synthio patch to generate audio
    vca = synthio.Envelope(
        attack_time=0.001, decay_time=0.01, sustain_level=0.4,
        release_time=0, attack_level=0.6
    )
    synth = synthio.Synthesizer(
        sample_rate=SAMPLE_RATE, channel_count=CHAN_COUNT, envelope=vca
    )
    audio.play(synth)

    # Preallocate reusable Note objects to avoid heap allocation delays later.
    # CAUTION: I'm not sure if this is how the synthio developers meant for
    # this to be used. I'm guessing this way is good. But, it might actually be
    # causing a lot of extra CPU load? Not sure how to test that.
    notes = [None] * 127
    for i in range(21, 108+1):
        notes[i] = synthio.Note(synthio.midi_to_hz(i))

    # Cache function references (MicroPython performance boost trick)
    fast_wr = sys.stdout.write
    panic = synth.release_all
    press = synth.press
    release = synth.release

    # Main loop: scan for usb MIDI device, connect, handle input events.
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
            # Use ScanResult object to check if USB device descriptor info
            # matches the class/subclass/protocol pattern for a MIDI device
            dev = MIDIInputDevice(r)
            fast_wr(" found MIDI device vid:pid %04X:%04X\n" % (r.vid, r.pid))
            # Collect garbage to hopefully limit heap fragmentation.
            r = None
            device_cache = {}
            gc.collect()
            # Poll for input until USB error.
            # CAUTION: This loop needs to be as efficient as possible. Any
            # extra work here directly adds time to USB and audio latency.
            cin = num = val = None
            for data in dev.input_event_generator():
                # Beginn handling midi packet which should be None or a 4-byte
                # memoryview.
                if data is None:
                    continue

                # data[0] has CN (Cable Number) and CIN (Code Index Number). By
                # discarding CN with `& 0x0f`, we ignore which virtual midi
                # port the message arrived from. Doing that would be bad for a
                # fancy DAW or synth setup where you needed to route MIDI
                # among multiple devices. But, for this, ignoring CN is fine.
                # We do need CIN though to distinguish between note on, note
                # off, Control Change (CC), and so on.
                #
                cin = data[0] & 0x0f

                # This decodes MIDI events by comparing constants against bytes
                # from a memoryview. Using a class to do this parsing would use
                # many extra heap allocations and dictionary lookups. That
                # stuff is slow, and we want to go _fast_.
                #
                (chan, num, val) = ((data[1] & 0xf) + 1, data[2], data[3])
                if cin == 0x08 and (21 <= num <= 108):
                    # Note off
                    release(notes[num])
                    if DEBUG:
                        fast_wr('Off %d %d %d\n' % (chan, num, val))
                elif cin == 0x09 and (21 <= num <= 108):
                    # Note on
                    press(notes[num])
                    if DEBUG:
                        fast_wr('On  %d %d %d\n' % (chan, num, val))
                elif cin == 0x0b and num == 123 and val == 0:
                    # CC 123 conventionally means stop all notes ("panic")
                    panic()
                    fast_wr('PANIC %d %d %d\n' % (chan, num, val))
                elif DEBUG:
                    if cin == 0x0b:
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
