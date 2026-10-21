#!/usr/bin/env python3
"""Read EC20 status through its USB AT interface without starting a data session."""
import os
from pathlib import Path
import select
import termios
import time

ports = []
for tty in Path('/sys/class/tty').glob('ttyUSB*'):
    interface = (tty / 'device').resolve().parent
    usb = interface.parent
    if (usb / 'idVendor').exists() and (usb / 'idVendor').read_text().strip() == '2c7c':
        if (interface / 'bInterfaceNumber').read_text().strip() == '02':
            ports.append('/dev/' + tty.name)
if len(ports) != 1:
    raise SystemExit(f'Expected one Quectel AT interface, found {ports}')

port = ports[0]
print('AT_PORT=' + port, flush=True)
fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
settings = termios.tcgetattr(fd)
settings[0] = settings[1] = settings[3] = 0
settings[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
settings[4] = settings[5] = termios.B115200
settings[6][termios.VMIN] = 0
settings[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, settings)
try:
    for command in ('AT', 'AT+GMM', 'AT+GMR', 'AT+CPIN?', 'AT+QCCID', 'AT+CSQ',
                    'AT+CREG?', 'AT+CGREG?', 'AT+CEREG?', 'AT+CGATT?',
                    'AT+QCFG="usbnet"'):
        termios.tcflush(fd, termios.TCIFLUSH)
        os.write(fd, (command + '\r').encode())
        response = b''
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if select.select([fd], [], [], 0.2)[0]:
                response += os.read(fd, 8192)
                if b'\r\nOK\r\n' in response or b'ERROR' in response:
                    break
        print(response.decode(errors='replace').strip(), flush=True)
finally:
    os.close(fd)
