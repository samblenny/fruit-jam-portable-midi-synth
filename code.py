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
DEBUG = True


def init_dac_audio_synth(i2c):
    # Configure Fruit Jam rev D TLV320 I2S DAC and make a Synthesizer.
    # - i2c: a reference to board.I2C()
    # - returns tuple: (dac: TLV320DAC3100, audio: I2SOut, synth: Synthesizer)

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
    dac.speaker_output = False
    dac.headphone_output = True
    # 3. Set volume for for line-level or headphone level
    if LINE_LEVEL:
        # This gives a line output level suitable for plugging into a mixer or
        # the AUX input of a powered speaker (THIS IS TOO LOUD FOR HEADPHONES!)
        dac.headphone_volume = -15.5
    else:
        # Use the default dac_volum & headphone_volume settings that should
        # be suitable for low impedance headphones (earbuds, etc)
        pass
    # 4. Configure I2S for Fruit Jam rev D (rev B swapped WS and MCLK)
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
