#!/usr/bin/env python3
"""Record PF818 input events during a supervised hardware check."""
import fcntl
import os
import select
import struct
import time

streams = {os.open(f"/dev/input/event{i}", os.O_RDONLY | os.O_NONBLOCK): i for i in range(3)}
for fd, number in streams.items():
    if number == 2:
        for code in (0x35, 0x36):
            values = bytearray(24)
            fcntl.ioctl(fd, 0x80184540 + code, values)
            print("ABS_RANGE", code, struct.unpack("iiiiii", values), flush=True)
deadline = time.monotonic() + 120
while time.monotonic() < deadline:
    readable, _, _ = select.select(list(streams), [], [], 1)
    for fd in readable:
        data = os.read(fd, 24 * 64)
        for offset in range(0, len(data), 24):
            seconds, micros, kind, code, value = struct.unpack("llHHi", data[offset:offset+24])
            if kind in (1, 3):
                print(streams[fd], kind, code, value, flush=True)
