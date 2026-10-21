#!/usr/bin/env python3
"""Activate an ISO14443-A card through the PF818 factory reader library."""
import ctypes
import json
import sys
import time
from pathlib import Path

library = ctypes.CDLL(str(Path(__file__).resolve().parent / 'libpf818-reader.so'))
u8 = ctypes.c_uint8
pointer = ctypes.POINTER(u8)
configure = library._Z10config_pcd8pcd_info
configure.argtypes = [ctypes.c_uint64]
configure(1)  # SPI, TSC9883/CLRC663
spi_init = library._Z8spi_initPKciiji
spi_init.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_int]
fd = spi_init(b'/dev/spidev0.0', 0, 8, 1000000, 1)
if fd < 0:
    sys.exit('Unable to open /dev/spidev0.0')
activate = library._Z20TSC9883_PcdActivateAPhS_S_S_
activate.argtypes = [pointer, pointer, pointer, pointer]
activate.restype = ctypes.c_int8
field_off = library._Z16TSC9883_FieldOffv
field_on = library._Z15TSC9883_FieldOnv
read_register = library._Z15TSC9883_ReadRegh
read_register.argtypes = [u8]
read_register.restype = u8
found = False
try:
    print(json.dumps({'chip_version': f'{read_register(0x7f):02X}'}), flush=True)
    for attempt in range(1, 6):
        field_off()
        time.sleep(0.02)
        field_on()
        time.sleep(0.02)
        atqa, uid, length, sak = (u8 * 2)(), (u8 * 16)(), u8(), u8()
        status = activate(atqa, uid, ctypes.byref(length), ctypes.byref(sak))
        print(json.dumps({
            'attempt': attempt, 'status': status,
            'atqa': bytes(atqa).hex().upper(),
            'uid_length': length.value,
            'uid': bytes(uid[:length.value]).hex().upper(),
            'sak': f'{sak.value:02X}'
        }), flush=True)
        if status == 0:
            found = True
            break
        time.sleep(0.2)
finally:
    field_off()
    library._Z9spi_closev()
sys.exit(0 if found else 1)
