#!/usr/bin/env python3
"""Exercise the actual CLI through a pseudo-terminal; no scanner required.

Run: python3 adaptation/round5/test_reader.py /path/to/host/pf818-scan
"""
import os
import pty
import subprocess
import sys
import termios
import time
import unittest

BINARY = os.path.abspath(sys.argv.pop(1)) if len(sys.argv) > 1 else 'pf818-scan'


class ReaderTests(unittest.TestCase):
    def check(self, args, chunks, expected):
        master, slave = pty.openpty()
        p = subprocess.Popen([BINARY, '--device', os.ttyname(slave), *args],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 2
            while termios.tcgetattr(slave)[3] & termios.ICANON:
                if p.poll() is not None:
                    self.fail(repr(p.communicate()))
                if time.monotonic() > deadline:
                    self.fail('Reader did not configure the serial port')
                time.sleep(.005)
            # tcflush is part of startup. Give the child time to finish it.
            time.sleep(.02)
            for data, delay in chunks:
                os.write(master, data)
                time.sleep(delay)
            out, err = p.communicate(timeout=3)
            self.assertEqual((p.returncode, out), expected, repr(err))
        finally:
            if p.poll() is None:
                p.kill(); p.wait()
            os.close(master); os.close(slave)

    def test_fragments_and_crlf(self):
        self.check(['--once'], [(b'PF81', .03), (b'8-LINUX', .03),
                   (b'-SCAN-20261024\r\n', 0)], (0, b'PF818-LINUX-SCAN-20261024\n'))

    def test_no_suffix(self):
        self.check(['--once', '--gap-ms', '60'], [(b'no-suffix', 0)], (0, b'no-suffix\n'))

    def test_observed_status(self):
        self.check(['--once', '--gap-ms', '50'], [(b'\0\0\xff\xfc', .12),
                   (b'valid\r\n', 0)], (0, b'valid\n'))

    def test_utf8(self):
        self.check(['--once', '--json'], [('扫码器✓\r\n'.encode(), 0)],
                   (0, '{"text":"扫码器✓","hex":"e689abe7a081e599a8e29c93","bytes":12}\n'.encode()))

    def test_multiline_and_nul(self):
        self.check(['--once', '--json', '--framing', 'gap', '--gap-ms', '50'],
                   [(b'a\nb\x00"\\', 0)],
                   (0, b'{"text":"a\\u000ab\\u0000\\"\\\\","hex":"610a6200225c","bytes":6}\n'))

    def test_binary(self):
        self.check(['--once', '--json', '--gap-ms', '50'], [(b'\xff\xfe', 0)],
                   (0, b'{"text":null,"hex":"fffe","bytes":2}\n'))

    def test_timeout(self):
        self.check(['--once', '--timeout', '1'], [], (2, b''))

    def test_incomplete_frame_at_deadline(self):
        self.check(['--once', '--gap-ms', '1500', '--timeout', '1'],
                   [(b'partial', 0)], (2, b''))


if __name__ == '__main__':
    unittest.main()
