import websocket
import time
import json
import re
import hid
import math
import rel
from dataclasses import dataclass
from threading import Thread, Event, Lock
from enum import Enum, IntEnum
from time import sleep


# Global vars
display_mgr = ''
device = ''
buttonlist = []
values = []

ws = ''


BUTTONS_CNT = 99  # TODO
PAGE_LINES = 14  # Header + 6 * label + 6 * cont + textbox
PAGE_CHARS_PER_LINE = 24
PAGE_BYTES_PER_CHAR = 3
PAGE_BYTES_PER_LINE = PAGE_CHARS_PER_LINE * PAGE_BYTES_PER_CHAR
PAGE_BYTES_PER_PAGE = PAGE_BYTES_PER_LINE * PAGE_LINES

buttons_press_event = [0] * BUTTONS_CNT


class DEVICEMASK(IntEnum):
    NONE = 0
    MCDU = 0x01
    PFP3N = 0x02
    PFP4 = 0x04
    PFP7 = 0x08
    CAP = 0x10
    FO = 0x20
    OBS = 0x40


class ButtonType(Enum):
    SWITCH = 0
    TOGGLE = 1
    SEND_0 = 2
    SEND_1 = 3
    SEND_2 = 4
    SEND_3 = 5
    SEND_4 = 6
    SEND_5 = 7
    NONE = 5  # for testing


class Leds(Enum):
    BACKLIGHT = 0  # 0 .. 255
    SCREEN_BACKLIGHT = 1  # 0 .. 255
    FAIL = 8
    FM = 9
    MCDU = 10
    MENU = 11
    FM1 = 12
    IND = 13
    RDY = 14
    STATUS = 15
    FM2 = 16


class DrefType(Enum):
    DATA = 0
    CMD = 1
    NONE = 2  # for testing


@dataclass
class Button:
    id: int
    label: str
    dataref: str = None
    dreftype: DrefType = DrefType.DATA
    type: ButtonType = ButtonType.NONE
    led: Leds = None


values_processed = Event()
xplane_connected = False
buttonlist = []
values = []

led_brightness = 180

device_config = DEVICEMASK.NONE


class Byte(Enum):
    H0 = 0


@dataclass
class Flag:
    name: str
    byte: Byte
    mask: int
    value: bool = False

# --- USB Manager Class for Device Detection ---


class UsbManager:
    def __init__(self):
        self.device = None
        self.device_config = 0

    def connect_device(self, vid: int, pid: int):
        try:
            self.device = hid.device()
            self.device.open(vid, pid)
        except AttributeError:
            print("Using hidapi mac version")
            self.device = hid.Device(vid=vid, pid=pid)

        if self.device is None:
            raise RuntimeError("Device not found")

        print("Device connected.")

    def find_device(self):
        devlist = [
            {'vid': 0x4098, 'pid': 0xbb36, 'name': 'MCDU - Captain',
                'mask': DEVICEMASK.MCDU | DEVICEMASK.CAP},
            {'vid': 0x4098, 'pid': 0xbb3e, 'name': 'MCDU - First Officer',
                'mask': DEVICEMASK.MCDU | DEVICEMASK.FO},
            {'vid': 0x4098, 'pid': 0xbb3a, 'name': 'MCDU - Observer',
                'mask': DEVICEMASK.MCDU | DEVICEMASK.OBS},
            {'vid': 0x4098, 'pid': 0xbc1e,
                'name': 'PFP 3N (not tested)', 'mask': DEVICEMASK.PFP3N},
            {'vid': 0x4098, 'pid': 0xbc1d,
                'name': 'PFP 4 (not tested)', 'mask': DEVICEMASK.PFP4},
            {'vid': 0x4098, 'pid': 0xba01,
                'name': 'PFP 7 (not tested)', 'mask': DEVICEMASK.PFP7}
        ]
        for d in devlist:
            print(f"Searching for {d['name']}... ", end='')
            for dev in hid.enumerate():
                if dev['vendor_id'] == d['vid'] and dev['product_id'] == d['pid']:
                    print("found")
                    self.device_config |= d['mask']
                    return d['vid'], d['pid'], self.device_config
            print("not found")
        return None, None, 0


class DisplayManager:
    col_map = {
        'L': 0x0000,  # black with grey background
        'A': 0x0021,  # amber
        'W': 0x0042,  # white
        'B': 0x0063,  # cyan
        'G': 0x0084,  # green
        'M': 0x00A5,  # magenta
        'R': 0x00C6,  # red
        'Y': 0x00E7,  # yellow
        'E': 0x0108,  # grey
        ' ': 0x0042  # use white
    }

    def __init__(self, device):
        self.device = device
        self.page = [[' ' for _ in range(PAGE_BYTES_PER_LINE)]
                     for _ in range(PAGE_LINES)]
        device.write(bytes([0xf0, 0x0, 0x1, 0x38, 0x32, 0xbb, 0x0, 0x0, 0x1e, 0x1, 0x0, 0x0, 0xc4, 0x24, 0xa, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x18, 0x1, 0x0, 0x0, 0xc4,
                     0x24, 0xa, 0x0, 0x0, 0x8, 0x0, 0x0, 0x0, 0x34, 0x0, 0x18, 0x0, 0xe, 0x0, 0x18, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0xc4, 0x24, 0xa, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x2, 0x38, 0x0, 0x0, 0x0, 0x1, 0x0, 0x5, 0x0, 0x0, 0x0, 0x2, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0xc4,
                     0x24, 0xa, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x1, 0x0, 0x6, 0x0, 0x0, 0x0, 0x3, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x3, 0x38, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0x0, 0x0, 0x0, 0xff, 0x4, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0,
                     0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0x0, 0xa5, 0xff, 0xff, 0x5, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x4, 0x38, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0xff, 0xff, 0xff, 0xff, 0x6, 0x0, 0x0, 0x0, 0x0,
                     0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0xff, 0xff, 0x0, 0xff, 0x7, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x5, 0x38, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0x3d, 0xff, 0x0,
                     0xff, 0x8, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0xff, 0x63, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x6, 0x38, 0xff, 0xff, 0x9, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0,
                     0x0, 0x2, 0x0, 0x0, 0x0, 0xff, 0xff, 0xa, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x7, 0x38, 0x0, 0x0, 0x2, 0x0, 0x0, 0xff, 0xff, 0xff, 0xb, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72,
                     0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0x42, 0x5c, 0x61, 0xff, 0xc, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x8, 0x38, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0x77, 0x77, 0x77, 0xff, 0xd, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0,
                     0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x2, 0x0, 0x5e, 0x73, 0x79, 0xff, 0xe, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x9, 0x38, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0x20, 0x20, 0x20, 0xff, 0xf, 0x0, 0x0, 0x0, 0x0, 0x0,
                     0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0x0, 0xa5, 0xff, 0xff, 0x10, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0xa, 0x38, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0xff, 0xff, 0xff, 0xff,
                     0x11, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0xff, 0xff, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0xb, 0x38, 0xff, 0x12, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0,
                     0x3, 0x0, 0x3d, 0xff, 0x0, 0xff, 0x13, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0xc, 0x38, 0x0, 0x3, 0x0, 0xff, 0x63, 0xff, 0xff, 0x14, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19,
                     0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0x0, 0x0, 0xff, 0xff, 0x15, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0xd, 0x38, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0x0, 0xff, 0xff, 0xff, 0x16, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19,
                     0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0x42, 0x5c, 0x61, 0xff, 0x17, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0xe, 0x38, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0x77, 0x77, 0x77, 0xff, 0x18, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
                     0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x3, 0x0, 0x5e, 0x73, 0x79, 0xff, 0x19, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0xf, 0x38, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x4, 0x0, 0x0, 0x0, 0x0, 0x0, 0x1a,
                     0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x4, 0x0, 0x1, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x10, 0x38, 0x1b, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x19, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0xe, 0x0, 0x0, 0x0, 0x4,
                     0x0, 0x2, 0x0, 0x0, 0x0, 0x1c, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x32, 0xbb, 0x0, 0x0, 0x1a, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0x1, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))
        device.write(bytes([0xf0, 0x0, 0x11, 0x12, 0x2, 0x32, 0xbb, 0x0, 0x0, 0x1c, 0x1, 0x0, 0x0, 0x76, 0x72, 0x19, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0,
                     0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0]))

    def startupscreen(self, new_version: str = None):
        self.clear()
        self.write_line_to_page(0, 3,  'MCDU for MSFS', 'W')
        self.write_line_to_page(1, 3,  'FlyByWire SimBridge', 'W')
        self.write_line_to_page(12, 0, 'www.github.com/schenlap', 'W', True)
        self.write_line_to_page(13, 0, '/winwing_mcdu', 'W', True)
        self.write_line_to_page(8, 1, 'waiting for SimBridge ', 'A')
        self.write_line_to_page(3, 1, f'version {0.1}', 'W')
        if new_version:
            self.write_line_to_page(4, 1, f'New version {new_version}', 'A')
            self.write_line_to_page(5, 1, f'available', 'A')
        self.set_from_page()

    def _data_from_col_font(self, color: str, font_small: bool = False):
        if type(color) == int:
            color = chr(color)
        if color.upper() not in self.col_map:
            raise ValueError(f"Invalid color '{color}'")
        if font_small:
            color = self.col_map[color.upper()] + 0x016b
        else:
            color = self.col_map[color.upper()]
        data_low = color & 0x0ff
        data_high = (color >> 8) & 0xff
        return (data_low, data_high)

    def empty_page(self):
        self.page = [[' ' for _ in range(PAGE_BYTES_PER_LINE)]
                     for _ in range(PAGE_LINES)]

    def clear(self):
        blank_line = [0xf2] + [0x42, 0x00, ord(' ')] * PAGE_CHARS_PER_LINE
        for _ in range(16):
            self.device.write(bytes(blank_line))

    def write_line_repeated(self, text: str, repeat: int = 16):
        encoded = [ord(c) for c in text]
        c = 0
        for _ in range(repeat):
            buf = [0xf2]
            for _ in range(21):
                buf.extend([0x42, 0x00, encoded[c]])
                c = (c + 1) % len(encoded)
            self.device.write(bytes(buf))

    def set_from_page(self, page=None, vertslew_key=0):
        if page == None:  # use internal page
            page = self.page
        buf = []
        for i in range(PAGE_LINES):
            for j in range(PAGE_CHARS_PER_LINE):
                color = page[i][j * PAGE_BYTES_PER_CHAR]
                font_small = page[i][j * PAGE_BYTES_PER_CHAR + 1]
                data_low, data_high = self._data_from_col_font(
                    color, font_small)
                buf.append(data_low)
                buf.append(data_high)
                val = ord(page[i][j * PAGE_BYTES_PER_CHAR +
                          PAGE_BYTES_PER_CHAR - 1])
                if val == 35:
                    buf.extend([0xe2, 0x98, 0x90])
                # elif val == 60: # <
                #     buf.extend([0xe2, 0x86, 0x90])
                # elif val == 62: # >
                #     buf.extend([0xe2, 0x86, 0x92])
                elif val == 96:  # °
                    buf.extend([0xc2, 0xb0])
                # elif val == "A": # down arrow
                #    buf.extend([0xe2, 0x86, 0x93])
                # elif val == "ö": # up arrow
                #    buf.extend([0xe2, 0x86, 0x91])
                else:
                    if i == PAGE_LINES - 1 and j == PAGE_CHARS_PER_LINE - 2 and (vertslew_key == 1 or vertslew_key == 2):
                        buf.extend([0xe2, 0x86, 0x91])
                    elif i == PAGE_LINES - 1 and j == PAGE_CHARS_PER_LINE - 1 and (vertslew_key == 1 or vertslew_key == 3):
                        buf.extend([0xe2, 0x86, 0x93])
                    else:
                        buf.append(val)

        while len(buf):
            max_len = min(63, len(buf))
            usb_buf = buf[:max_len]
            usb_buf.insert(0, 0xf2)
            if max_len < 63:
                usb_buf.extend([0] * (63 - max_len))
            self.device.write(bytes(usb_buf))
            del buf[:max_len]

    def write_line_to_page(self, line, pos, text: str, color: str = 'W', font_small: bool = False):
        if line < 0 or line >= PAGE_LINES:
            raise ValueError("Line number out of range")
        if pos < 0 or pos + len(text) > PAGE_CHARS_PER_LINE:
            raise ValueError("Position number out of range")
        if len(text) > PAGE_CHARS_PER_LINE:
            raise ValueError("Text too long for line")

        # data_low, data_high = self._data_from_col_font(color, font_small)
        pos = pos * PAGE_BYTES_PER_CHAR
        c = 0
        buf = []
        for c in range(len(text)):
            self.page[line][pos + c * PAGE_BYTES_PER_CHAR] = color
            self.page[line][pos + c * PAGE_BYTES_PER_CHAR + 1] = font_small
            self.page[line][pos + c * PAGE_BYTES_PER_CHAR +
                            PAGE_BYTES_PER_CHAR - 1] = text[c]


def create_button_list_mcdu():
    buttonlist.append(Button(0, "LSK1L", "event:left:L1",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(1, "LSK2L", "event:left:L2",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(2, "LSK3L", "event:left:L3",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(3, "LSK4L", "event:left:L4",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(4, "LSK5L", "event:left:L5",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(5, "LSK6L", "event:left:L6",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(6, "LSK1R", "event:left:R1",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(7, "LSK2R", "event:left:R2",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(8, "LSK3R", "event:left:R3",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(9, "LSK4R", "event:left:R4",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(10, "LSK5R", "event:left:R5",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(11, "LSK6R", "event:left:R6",
                      DrefType.CMD, ButtonType.TOGGLE))  # 0x800
    buttonlist.append(Button(12, "DIRTO", "event:left:DIR",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(13, "PROG", "event:left:PROG",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(14, "PERF", "event:left:PERF",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(15, "INIT", "event:left:INIT",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(16, "DATA", "event:left:DATA",
                      DrefType.CMD, ButtonType.TOGGLE))
    # buttonlist.append(Button(17, "EMTYR", "toliss_airbus/iscs_open",
    #                   DrefType.CMD, ButtonType.TOGGLE))  # 17 emtpy, map to open ICSC screen
    buttonlist.append(
        Button(18, "BRT", "event:left:BRT", DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(19, "FPLN", "event:left:FPLN",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(20, "RADNAV", "event:left:RAD",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(21, "FUEL", "event:left:FUEL",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(22, "SEC-FPLN", "event:left:SEC",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(23, "ATC", "event:left:ATC",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(24, "MENU", "event:left:MENU",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(25, "DIM", "event:left:DIM",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(
        Button(26, "AIRPORT", "event:left:AIRPORT", DrefType.CMD, ButtonType.TOGGLE))
    # buttonlist.append(Button(27, "PURSER", "AirbusFBW/purser/fwd",
    #                   DrefType.CMD, ButtonType.TOGGLE))  # 27 empty, map to CALL purser FWD
    buttonlist.append(Button(28, "SLEW_LEFT", "event:left:LEFT",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(29, "SLEW_UP", "event:left:UP",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(
        Button(30, "SLEW_RIGHT", "event:left:RIGHT", DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(31, "SLEW_DOWN", "event:left:DOWN",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(32, "KEY1", "event:left:1",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(33, "KEY2", "event:left:2",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(34, "KEY3", "event:left:3",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(35, "KEY4", "event:left4",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(36, "KEY5", "event:left:5",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(37, "KEY6", "event:left:6",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(38, "KEY7", "event:left:7",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(39, "KEY8", "event:left:8",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(40, "KEY9", "event:left:9",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(41, "DOT", "event:left:DOT",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(42, "KEY0", "event:left:0",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(
        43, "PLUSMINUS", "event:left:PLUSMINUS", DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(44, "KEYA", "event:left:A",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(45, "KEYB", "event:left:B",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(46, "KEYC", "event:left:C",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(47, "KEYD", "event:left:D",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(48, "KEYE", "event:left:E",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(49, "KEYF", "event:left:F",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(50, "KEYG", "event:left:G",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(51, "KEYH", "event:left:H",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(52, "KEYI", "event:left:I",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(53, "KEYJ", "event:left:J",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(54, "KEYK", "event:left:K",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(55, "KEYL", "event:left:L",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(56, "KEYM", "event:left:M",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(57, "KEYN", "event:left:N",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(58, "KEYO", "event:left:O",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(59, "KEYP", "event:left:P",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(60, "KEYQ", "event:left:Q",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(61, "KEYR", "event:left:R",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(62, "KEYS", "event:left:S",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(63, "KEYT", "event:left:T",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(64, "KEYU", "event:left:U",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(65, "KEYV", "event:left:V",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(66, "KEYW", "event:left:W",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(67, "KEYX", "event:left:X",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(68, "KEYY", "event:left:Y",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(69, "KEYZ", "event:left:Z",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(70, "SLASH", "event:left:DIV",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(71, "SPACE", "event:left:SP",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(72, "OVERFLY", "event:left:OVFY",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(73, "Clear", "event:left:CLR",
                      DrefType.CMD, ButtonType.TOGGLE))
    buttonlist.append(Button(75, "LCDBright", "event:left:BRIGHTUP",
                      DrefType.DATA, ButtonType.NONE, Leds.SCREEN_BACKLIGHT))
    buttonlist.append(Button(75, "Backlight", "ckpt/fped/lights/mainPedLeft/anim",
                      DrefType.DATA, ButtonType.NONE, Leds.BACKLIGHT))


def xor_bitmask(a, b, bitmask):
    return (a & bitmask) != (b & bitmask)


def mcdu_button_event():
    # print(f'events: press: {buttons_press_event}, release: {buttons_release_event}')
    for b in buttonlist:

        if not any(buttons_press_event):  # and not any(buttons_release_event):
            break
        if b.id == None:
            continue
        if buttons_press_event[b.id]:
            buttons_press_event[b.id] = 0

            if device_config & DEVICEMASK.FO:
                b.dataref = b.dataref.replace(
                    'AirbusFBW/MCDU1', 'AirbusFBW/MCDU2')

            # print(f'button {b.label} pressed')
            if b.type == ButtonType.TOGGLE:
                val = b.dataref
                if b.dreftype == DrefType.DATA:
                    print(
                        f'set dataref {b.dataref} from {bool(val)} to {not bool(val)}')
                    # xp.WriteDataRef(b.dataref, not bool(val))
                elif b.dreftype == DrefType.CMD:
                    ws.send(b.dataref)
                    print(f'send command {b.dataref}')
                    # xp.sendCommand(b.dataref)
            elif b.type == ButtonType.SWITCH:
                # val = datacache[b.dataref]
                # if b.dreftype == DrefType.DATA:
                #     print(f'set dataref {b.dataref} to 1')
                #     # xp.WriteDataRef(b.dataref, 1)
                # elif b.dreftype == DrefType.CMD:
                    print(f'send command {b.dataref}')
                    # xp.sendCommand(b.dataref)
            # elif b.type == ButtonType.SEND_0:
            #     if b.dreftype == DrefType.DATA:
            #         print(f'set dataref {b.dataref} to 0')
            #         # xp.WriteDataRef(b.dataref, 0)
            # elif b.type == ButtonType.SEND_1:
            #     if b.dreftype == DrefType.DATA:
            #         print(f'set dataref {b.dataref} to 1')
            #         # xp.WriteDataRef(b.dataref, 1)
            # elif b.type == ButtonType.SEND_2:
            #     if b.dreftype == DrefType.DATA:
            #         print(f'set dataref {b.dataref} to 2')
            #         # xp.WriteDataRef(b.dataref, 2)
            # elif b.type == ButtonType.SEND_3:
            #     if b.dreftype == DrefType.DATA:
            #         print(f'set dataref {b.dataref} to 3')
            #         # xp.WriteDataRef(b.dataref, 3)
            # elif b.type == ButtonType.SEND_4:
            #     if b.dreftype == DrefType.DATA:
            #         print(f'set dataref {b.dataref} to 4')
            #         # xp.WriteDataRef(b.dataref, 4)
            # elif b.type == ButtonType.SEND_5:
            #     if b.dreftype == DrefType.DATA:
            #         print(f'set dataref {b.dataref} to 5')
            #         # xp.WriteDataRef(b.dataref, 5)
            else:
                print(f'no known button type for button {b.label}')
        # if buttons_release_event[b.id]:
        #     buttons_release_event[b.id] = 0
        #     print(f'button {b.label} released')
        #     if b.type == ButtonType.SWITCH:
        #         print("asd")
        #         #xp.WriteDataRef(b.dataref, 0)


def mcdu_create_events(usb_mgr, display_mgr):
    global values
    sleep(2)  # wait for values to be available
    buttons_last = 0
    while True:

        # set_datacache(usb_mgr, display_mgr, values.copy())
        values_processed.set()
        sleep(0.005)
        # print('#', end='', flush=True) # TEST1: should print many '#' in console
        try:
            data_in = usb_mgr.device.read(0x81, 25)
        except Exception as error:
            print(f' *** continue after usb-in error: {error} ***')  # TODO
            sleep(0.5)  # TODO remove
            continue
        if len(data_in) == 14:  # we get this often but don't understand yet. May have someting to do with leds set
            continue
        if len(data_in) != 25:
            print(f'rx data count {len(data_in)} not valid')
            continue
        # print(f"data_in: {data_in}")

        # create button bit-pattern
        buttons = 0
        for i in range(12):
            buttons |= data_in[i + 1] << (8 * i)
        # print(hex(buttons)) # TEST2: you should see a difference when pressing buttons
        for i in range(BUTTONS_CNT):
            mask = 0x01 << i
            if xor_bitmask(buttons, buttons_last, mask):
                # print(f"buttons: {format(buttons, "#04x"):^14}")
                if buttons & mask:
                    buttons_press_event[i] = 1
                # else: Button releasing not necessary in simbrief
                #     buttons_release_event[i] = 1

                mcdu_button_event()

        buttons_last = buttons


def update_mcdu(display_mgr, data):
    display_mgr.empty_page()

    # Update status LEDs
    update_annunciators(data['annunciators'])

    # Update brightness
    screen_backlight_brightness = math.ceil(data['displayBrightness'] * 255)
    backlight_brightness = math.ceil(data['integralBrightness'] * 255)

    winwing_mcdu_set_leds(Leds.SCREEN_BACKLIGHT, screen_backlight_brightness)
    winwing_mcdu_set_leds(Leds.BACKLIGHT, backlight_brightness)

    # TITLE TEXT
    text, spaces, color, font_small = line_parser(data['title'])

    # If there are no spaces for title, guesstimate where it should be
    if spaces == 0:
        print('Warning: no title location')
        spaces = math.floor(12 - (len(text) / 2))

    display_mgr.write_line_to_page(0, spaces, text, color, font_small)

    # SCRATCHPAD TEXT
    text, spaces, color, font_small = line_parser(data['scratchpad'])

    # If there are no spaces for title, guesstimate where it should be
    if spaces == 0:
        print('Warning: no scratchpad location')
        spaces = 0

    display_mgr.write_line_to_page(13, spaces, text, color, font_small)

    update_mcdu_lines(data.get('lines', {}))

    # Finalize the update
    # display_mgr.clear()
    display_mgr.set_from_page()


def update_mcdu_lines(lines):
    global display_mgr

    for i, line in enumerate(lines):
        # Index for line heigth should always be lower to accomodate for title
        idx = i + 1

        seg1, seg2, seg3 = line
        s1_present = bool(seg1)
        s2_present = bool(seg2)
        s3_present = bool(seg3)

        # Try to split seg1 if seg2/3 are empty
        if not s2_present and not s3_present:
            if len(check_empty_line(seg1)) == 0:
                continue

            if '{sp}{sp}{sp}{sp}' in seg1:
                before, sep, after = seg1.partition('{sp}{sp}{sp}{sp}')
                s1_text, s1_spaces, s1_color, s1_font_small = line_parser(
                    before)
                s2_text, s2_spaces, s2_color, s2_font_small = line_parser(
                    sep + after)
                s2_present = len(check_empty_line(s2_text)) > 0
            else:
                s1_text, s1_spaces, s1_color, s1_font_small = line_parser(seg1)
                s2_text = s2_spaces = s2_color = s2_font_small = None

            if s1_present:
                display_mgr.write_line_to_page(
                    idx, s1_spaces, s1_text, s1_color, s1_font_small)

            if s2_present:
                s2_spaces = (s2_spaces or 0) + s1_spaces + len(s1_text)

                display_mgr.write_line_to_page(
                    idx, s2_spaces, s2_text.rstrip(), s2_color, s2_font_small)
            continue

        # Parse all present segments
        s1 = line_parser(seg1) if s1_present else None
        s2 = line_parser(seg2) if s2_present else None
        s3 = line_parser(seg3) if s3_present else None

        if s1:
            s1_text, s1_spaces, s1_color, s1_font_small = s1
            display_mgr.write_line_to_page(
                idx, s1_spaces, s1_text, s1_color, s1_font_small)

        if s2:
            s2_text, s2_spaces, s2_color, s2_font_small = s2
            s2_spaces = 24 - (len(s2_text) + s2_spaces)
            display_mgr.write_line_to_page(
                idx, s2_spaces, s2_text, s2_color, s2_font_small)

        if s3:
            s3_text, s3_spaces, s3_color, s3_font_small = s3
            total_width = len(s3_text) + s3_spaces
            s3_spaces = math.ceil(
                (PAGE_CHARS_PER_LINE / 2) - (total_width / 2))
            display_mgr.write_line_to_page(
                idx, s3_spaces, s3_text, s3_color, s3_font_small)


def check_empty_line(line):
    return re.sub(r"\{[a-zA-Z0-9 _-]+\}", "", line)


def line_parser(line):
    final_line = ''
    spaces = 0
    color = 'W'
    font_small = False

    # Remove the starting white from (almost) every line
    if line.startswith('{white}'):
        final_line = line[7:]
    else:
        final_line = line

    while final_line.startswith("{sp}") or final_line.startswith('\\xa0'):
        spaces += 1
        final_line = final_line[4:]

    if final_line.startswith("{small}"):
        font_small = True
        final_line = final_line[7:]

    if final_line.startswith("{big}"):
        font_small = False
        final_line = final_line[5:]


    full_color, color = determine_color(final_line)

    # Remove {color}
    if final_line.startswith(f'{{{full_color}}}'):
        final_line = final_line[len(full_color)+2:]

    # Somtimes size is defined after the color
    if final_line.startswith("{small}"):
        font_small = True
        final_line = final_line[7:]


    final_line = final_line.replace('{sp}', ' ')
    final_line = final_line.replace('\xa0', ' ')

    # Remove all other tokens like {end}, {small}, {big}, {inop}, etc.
    final_line = re.sub(r"\{[a-zA-Z0-9 _-]+\}", "", final_line)


    # Strip trailing spaces (but keep internal multiple spaces)
    # Only do this if there is >1 space
    # Since some segements rely on single trailing space for correct position
    if final_line.endswith('  '):
        final_line = final_line.rstrip()

    # Sometimes small text is indicated by a single space in front
    if final_line.startswith(' ') and len(final_line) > 2 and final_line[2] != ' ':
        font_small = True

    # Trim final_line to max 24 characters, since some lines are >24 even without spaces
    if (len(final_line) + spaces) > 24:
        final_line = final_line[:(24-spaces)]

    # Replace chars with correct ones
    final_line = final_line.replace('_', chr(35))  # Empty square
    final_line = final_line.replace('°', chr(96))  # Degree icon
    final_line = final_line.replace('|', '/')  # Empty square
    final_line = final_line.replace('Δ', '^')  # Replace Delta symbol
    # Replace any remaining { with <, as it should be an arrow
    final_line = final_line.replace('{', '<')

    return final_line, spaces, color, font_small


def determine_color(text: str):
    color_key_map = {
        "white": "W",
        "green": "G",
        "blue": "B",
        "amber": "A",
        "cyan": "B",
        "magenta": "M",
        "yellow": "Y",
        "red": "R",
        "grey": "E",
        "inop": "E"  # Removes the inop tag and sets the color
    }
    for color_name, key in color_key_map.items():
        match_token = "{"+color_name+"}"
        # Only search in the start of the text
        # Since sometimes, the color is after the text
        if match_token in text[:10]:
            return color_name, key
    print(f"No color found, defaulting to white. Text {text}")
    return "white", "W"


def update_annunciators(annunciators):

    annunciator_to_led = {
        "fail": Leds.FAIL,
        "fmgc": Leds.FM,
        "mcdu_menu": Leds.MCDU,
        "menu": Leds.MENU,
        "fm1": Leds.FM1,
        "ind": Leds.IND,
        "rdy": Leds.RDY,
        "fm2": Leds.FM2
    }

    for attribute, value in annunciators.items():
        led_enum = annunciator_to_led.get(attribute)
        if led_enum:
            brightness = 1 if value else 0
            winwing_mcdu_set_leds(led_enum, brightness)


def winwing_mcdu_set_leds(leds, brightness):
    if isinstance(leds, list):
        for i in range(len(leds)):
            winwing_mcdu_set_led(leds[i], brightness)
    else:
        winwing_mcdu_set_led(leds, brightness)


def winwing_mcdu_set_led(led, brightness):
    global device
    data = [0x02, 0x32, 0xbb, 0, 0, 3, 0x49,
            led.value, brightness, 0, 0, 0, 0, 0]
    if 'data' in locals():
        cmd = bytes(data)
        device.write(cmd)


# --- Handle simbrige websocket ---

def on_open(ws):
    global display_mgr
    print("Opened connection")
    display_mgr.write_line_to_page(8, 1, 'Connected to SimBridge', 'G')
    display_mgr.write_line_to_page(9, 1, 'Waiting for display', 'A')
    display_mgr.set_from_page()


def on_close(ws, close_status_code, close_msg):
    global display_mgr
    print(f"WebSocket closed: {close_status_code} - {close_msg}")
    display_mgr.startupscreen()


def on_error(ws, error):
    global display_mgr
    print(f"WebSocket error: {error}")

    winwing_mcdu_set_leds(Leds.SCREEN_BACKLIGHT, 128)
    winwing_mcdu_set_leds(Leds.FAIL, 1)
    display_mgr.startupscreen()
    display_mgr.write_line_to_page(4, 1, 'Connection to ', 'R')
    display_mgr.write_line_to_page(5, 1, 'SimBridge failed ', 'R')
    display_mgr.write_line_to_page(6, 1, str(error)[0:22], 'R', True)

    display_mgr.set_from_page()
    sleep(5)

    display_mgr.empty_page()
    display_mgr.clear()
    display_mgr.startupscreen()

    websocket_thread = Thread(target=setup_websocket)


def on_message(ws, message):
    global display_mgr
    print(f"Message received: {message}")

    winwing_mcdu_set_leds(Leds.FAIL, 0)

    if message.startswith("update:"):
        dict_left = json.loads(message[len("update:"):]).get('left', {})
        update_mcdu(display_mgr, dict_left)


def setup_websocket():
    global ws
    ws = websocket.WebSocket()
    try:
        ws = websocket.WebSocketApp("ws://localhost:8380/interfaces/v1/mcdu",
                                    on_open=on_open,
                                    on_message=on_message,
                                    on_error=on_error,
                                    on_close=on_close)
        ws.run_forever()

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        return

    return None


# --- Main ---
def main():
    global display_mgr
    global device

    usb = UsbManager()

    vid, pid, device_config = usb.find_device()
    if not vid or not pid:
        print("No compatible MCDU USB device found.")
        return

    usb.connect_device(vid, pid)

    device = usb.device

    display_mgr = DisplayManager(device)

    create_button_list_mcdu()

    display_mgr.empty_page()
    display_mgr.clear()
    display_mgr.startupscreen()

    usb_thread = Thread(target=mcdu_create_events, args=[usb, display_mgr])
    usb_thread.start()

    websocket_thread = Thread(target=setup_websocket)
    websocket_thread.start()


if __name__ == "__main__":
    main()
