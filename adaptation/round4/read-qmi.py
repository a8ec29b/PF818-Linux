#!/usr/bin/env python3
"""Query QMI CTL service versions without allocating clients or starting data."""
import json
import os
from pathlib import Path
import select
import struct
import time

device = '/dev/cdc-wdm0'
fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
try:
    # QMUX: CTL, client 0. CTL: transaction 1, GetVersionInfo (0x0021).
    os.write(fd, bytes.fromhex('01 0b 00 00 00 00 00 01 21 00 00 00'))
    deadline = time.monotonic() + 5
    response = b''
    while time.monotonic() < deadline:
        if not select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
            break
        response = os.read(fd, 65536)
        if response[4:6] == b'\x00\x00' and response[6:10] == b'\x01\x01\x21\x00':
            break
    if not response[6:10] == b'\x01\x01\x21\x00':
        raise SystemExit('No matching QMI CTL GetVersionInfo response')
    fields = {}
    offset = 12
    while offset < len(response):
        tag, length = struct.unpack_from('<BH', response, offset)
        fields[tag] = response[offset + 3:offset + 3 + length]
        offset += 3 + length
    result, error = struct.unpack('<HH', fields[2])
    if result:
        raise SystemExit(f'QMI GetVersionInfo failed: {error}')
    services = []
    names = {0: 'CTL', 1: 'WDS', 2: 'DMS', 3: 'NAS', 11: 'UIM', 26: 'WDA'}
    for i in range(fields[1][0]):
        service, major, minor = struct.unpack_from('<BHH', fields[1], 1 + i * 5)
        services.append({'id': service, 'name': names.get(service, f'0x{service:02X}'),
                         'version': f'{major}.{minor}'})
    print(json.dumps({'device': device,
                      'driver': Path('/sys/class/usbmisc/cdc-wdm0/device/driver').resolve().name,
                      'qmi_result': 'success', 'service_count': len(services),
                      'services': services}, indent=2))
finally:
    os.close(fd)
