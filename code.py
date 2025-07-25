# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2025 Sam Blenny
#
# Related Docs:
# - https://docs.circuitpython.org/projects/tlv320/en/latest/api.html
# - https://learn.adafruit.com/adafruit-tlv320dac3100-i2s-dac/overview
# - https://docs.circuitpython.org/en/latest/docs/environment.html
# - https://docs.circuitpython.org/en/latest/shared-bindings/audiobusio/
#
from audiobusio import I2SOut
from board import (
    BUTTON1, BUTTON2, BUTTON3, I2C, I2S_BCLK, I2S_DIN, I2S_WS, PERIPH_RESET
)
from digitalio import DigitalInOut, Direction, Pull
import displayio
import gc
from micropython import const
import os
import supervisor
import sys
from time import sleep
from usb.core import USBError, USBTimeoutError
import usb_host

from adafruit_tlv320 import TLV320DAC3100

from sb_usb_midi import find_usb_device, MIDIInputDevice


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
    #   | I2S Signal | Rev B Pin | Rev C Pin         |
    #   | ---------- | --------- | ----------------- |
    #   | I2S_MCLK   | GPIO27    | GPIO25 (old WS)   |
    #   | I2S_BCLK   | GPIO26    | GPIO26 (same)     |
    #   | I2S_WS     | GPIO25    | GPIO27 (old MCLK) |
    #   | I2S_DIN    | GPIO24    | GPIO24 (same)     |
    #   | I2S_IRQ    | n/a       | GPIO23 (new)      |
    #
    # Since I'm developing this on a rev B board, the code checks an
    # environment variable to allow for swapping the pins. IF YOU HAVE A REV C
    # OR LATER BOARD, YOU CAN IGNORE THIS. But, if you have a rev B board, you
    # need to add `FRUIT_JAM_BOARD_REV = "B"` in your CIRCUITPY/settings.toml
    # file.
    #
    # 1. Reset DAC (reset is active low)
    rst = DigitalInOut(PERIPH_RESET)
    rst.direction = Direction.OUTPUT
    rst.value = False
    sleep(0.1)
    rst.value = True
    # 2. Configure sample rate, bit depth, output port, and volume (dB below 0)
    i2c = I2C()
    dac = TLV320DAC3100(i2c)
    dac.configure_clocks(sample_rate=44100, bit_depth=16)
    dac.headphone_output = True
    dac.dac_volume = -20
    # 3. Initialize I2S, checking environment variable to control swapping of
    #    the BCLK and WS from their default values (for rev C+ boards)
    (bclk, ws) = (I2S_BCLK, I2S_WS)
    if os.getenv("FRUIT_JAM_BOARD_REV") == "B":
        print("USING FRUIT JAM REV B BOARD: SWAPPING I2S PINS!")
        (bclk, ws) = (I2S_WS, I2S_BCLK)
    else:
        print("Using default I2S pin definitions (not a rev B board)")
    audio = I2SOut(bit_clock=bclk, word_select=ws, data=I2S_DIN)

    # Configure synthio patch to generate audio
    print("TODO: CONFIGURE SYNTHIO PATCH")

    # Configure onboard buttons inputs
    b1 = DigitalInOut(BUTTON1)       # Volume down
    b2 = DigitalInOut(BUTTON2)       # Change patch
    b3 = DigitalInOut(BUTTON3)       # Volume up
    b1.direction = Direction.INPUT
    b2.direction = Direction.INPUT
    b3.direction = Direction.INPUT
    b1.pull = Pull.UP
    b2.pull = Pull.UP
    b3.pull = Pull.UP

    # Cache function references (MicroPython performance boost trick)
    fast_wr = sys.stdout.write

    # Main loop: scan for usb MIDI device, connect, handle input events.
    # This grabs the first MIDI device it finds. Reset board to re-scan bus.
    prev_b1 = b1.value
    prev_b2 = b2.value
    prev_b3 = b3.value
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
            # Collect garbage to hopefully limit heap fragmentation. If we're
            # lucky, this may help to avoid gc pauses during MIDI input loop.
            r = None
            device_cache = {}
            gc.collect()
            # Poll for input until USB error.
            # CAUTION: This loop needs to be as efficient as possible. Any
            # extra work here directly adds time to USB MIDI read latency.
            # The pp_skip and cp_skip variables help with thinning out channel
            # and polyphonic key pressure (aftertouch) messages.
            SKIP = const(6)
            pp_skip = SKIP
            cp_skip = SKIP
            for data in dev.input_event_generator():

                # Handle button presses (trigger on falling edge)
                if not b1.value:
                    if prev_b1:
                        prev_b1 = False
                        fast_wr("TODO: IMPLEMENT VOLUME DOWN\n")
                else:
                    prev_b1 = True
                if not b2.value:
                    if prev_b2:
                        prev_b2 = False
                        fast_wr("TODO: IMPLEMENT CHANGE PATCH\n")
                else:
                    prev_b2 = True
                if not b3.value:
                    if prev_b3:
                        prev_b3 = False
                        fast_wr("TODO: IMPLEMENT VOLUME UP\n")
                else:
                    prev_b3 = True

                # Beginn handling midi packet which should be None or a 4-byte
                # memoryview.
                # NOTE: The & 0x0f below is a bitwise logical operation for
                # masking off the CN (Cable Number) bits that indicate which
                # midi port the message arrived from. Ignoring the cable number
                # lets us lets us merge all the midi input streams to filter
                # more efficiently.
                #
                if data is None:
                    continue
                cin = data[0] & 0x0f

                # Filter out all System Real-Time messages. Sequencer playback
                # commonly sends start/stop messages along with _many_ timing
                # clocks. Dropping real-time messages conserves CPU to spend on
                # handling note and cc messages.
                #
                if cin == 0x0f and (0xf8 <= data[1] <= 0xff):
                    continue

                # This decodes MIDI events by comparing constants against bytes
                # from a memoryview. Doing it this way avoids many extra heap
                # allocations and dictionary lookups that would happen in OOP
                # style code with many class propery and method references. The
                # code may be harder to read like this, but in exchange we get
                # lower latency and fewer audio glitches.
                #
                (chan, num, val) = ((data[1] & 0x0f) + 1, data[2], data[3])
                if cin == 0x08:
                    # Note off
                    fast_wr('Off %d %d %d\n' % (chan, num, val))
                elif cin == 0x09:
                    # Note on
                    fast_wr('On  %d %d %d\n' % (chan, num, val))
                elif cin == 0x0a:
                    # Polyphonic key pressure (aftertouch)
                    if pp_skip > 0:
                        # Ignore some of the polyphonic pressure messages
                        # because processing them all can destroy our latency
                        pp_skip -= 1
                        continue
                    pp_skip = SKIP
                    fast_wr('PP  %d %d %d\n' % (chan, num, val))
                elif cin == 0x0b:
                    # CC (control change)
                    if num == 123 and val == 0:
                        # CC 123 = 0 means stop all notes ("all stop", "panic")
                        fast_wr('PANIC %d %d %d\n' % (chan, num, val))
                    else:
                        fast_wr('CC  %d %d %d\n' % (chan, num, val))
                elif cin == 0x0d:
                    # Channel key pressure (aftertouch)
                    if cp_skip > 0:
                        # Ignore some of the channel pressure messages
                        # because processing them all can destroy our latency
                        cp_skip -= 1
                        continue
                    cp_skip = SKIP
                    fast_wr('CP  %d %d\n' % (chan, num))
                elif cin == 0x0e:
                    # Pitch bend
                    fast_wr('PB  %d %d %d\n' % (chan, num, val))
                else:
                    # Ignore other messages: SysEx or whatever
                    pass
        except USBError as e:
            # This sometimes happens when devices are unplugged. Not always.
            print("USBError: '%s' (device unplugged?)" % e)
            show_scan_msg = True
        except ValueError as e:
            # This can happen if an initialization handshake glitches
            print(e)
            show_scan_msg = True


main()
