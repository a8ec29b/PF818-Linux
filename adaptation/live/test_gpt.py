#!/usr/bin/env python3
"""Validate enlarged primary/backup GPT using sparse temporary image files."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_live
import build_round5


class LiveGPTTests(unittest.TestCase):
    def test_growth_relocates_backup_and_keeps_starts(self):
        entries = bytearray(128 * 128)
        for offset, start, end in ((0, 32768, 294911), (128, 294912, 5275647)):
            entries[offset:offset + 16] = bytes(range(1, 17))
            entries[offset + 16:offset + 32] = b'x' * 16
            struct.pack_into('<QQ', entries, offset + 32, start, end)
        header = bytearray(512)
        header[:8] = b'EFI PART'
        struct.pack_into('<II', header, 8, 0x10000, 92)
        struct.pack_into('<II', header, 80, 128, 128)
        headers = [(1, header, 2, entries), (5277695, header, 5277663, entries)]
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'live.img'
            with image.open('wb') as f:
                f.truncate(160 * 1024**2)
            size = 2 * 1024**2
            parts = build_live.write_live_gpt(image, headers, size)
            self.assertEqual(parts, [(32768 * 512, 128 * 1024**2), (294912 * 512, size)])
            parsed, _ = build_round5.read_gpt(image, fixed_layout=False)
            self.assertEqual(parsed[0][3], parsed[1][3])
            self.assertNotEqual(parsed[0][3][16:32], b'x' * 16)
            self.assertEqual(struct.unpack_from('<Q', parsed[0][1], 32)[0], image.stat().st_size // 512 - 1)
            self.assertEqual(struct.unpack_from('<Q', parsed[1][1], 32)[0], 1)
            self.assertLess(struct.unpack_from('<Q', parsed[1][1], 48)[0], parsed[1][2])


if __name__ == '__main__':
    unittest.main()
