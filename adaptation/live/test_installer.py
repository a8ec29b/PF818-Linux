#!/usr/bin/env python3
"""Installer checks use temporary regular files and mocked device discovery only."""
import contextlib
import gzip
import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader('pf818_installer', str(HERE / 'pf818-install'))
spec = importlib.util.spec_from_loader(loader.name, loader)
installer = importlib.util.module_from_spec(spec)
loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = b'PF818 installer test\0\xff' * 1000
        self.digest = hashlib.sha256(self.data).hexdigest()
        (self.root / 'images').mkdir()
        self.image = self.root / 'images/linux-emmc.img.gz'
        with gzip.open(self.image, 'wb') as f:
            f.write(self.data)
        self.entry = {'file': 'images/linux-emmc.img.gz', 'bytes': len(self.data), 'sha256': self.digest}
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps({'format': 1, 'images': {'linux': self.entry}}))
        self.target = self.root / 'fake-emmc.bin'
        self.target.write_bytes(b'x' * (len(self.data) + 1024))
        self.env = {'root': '/dev/mmcblk9p2', 'target': self.target, 'bytes': self.target.stat().st_size}
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()

    def tearDown(self):
        self.quiet.__exit__(None, None, None)
        self.temp.cleanup()

    def test_language_selection(self):
        for values, expected in ((['1'], 'zh'), (['2'], 'en'), (['bad', '2'], 'en'), (['0'], None)):
            with patch('builtins.input', side_effect=values):
                self.assertEqual(installer.select_language(), expected)

    def test_android_requires_exact_capacity(self):
        installer.validate_capacity('linux', 200, 100)
        installer.validate_capacity('android', 200, 200)
        for kind, size, image in (('linux', 99, 100), ('android', 201, 200), ('android', 199, 200)):
            with self.assertRaises(installer.InstallError):
                installer.validate_capacity(kind, size, image)

    def test_bundle_path_cannot_escape(self):
        self.entry['file'] = '../other.img.gz'
        self.manifest.write_text(json.dumps({'format': 1, 'images': {'linux': self.entry}}))
        with self.assertRaises(installer.InstallError):
            installer.payload(self.root, 'linux')

    def test_valid_and_corrupt_archive(self):
        installer.verify_archive(self.image, len(self.data), self.digest, lambda _: None)
        self.image.write_bytes(self.image.read_bytes()[:-8])
        with self.assertRaises((EOFError, OSError)):
            installer.verify_archive(self.image, len(self.data), self.digest, lambda _: None)

    def test_bad_hash_never_releases_or_writes_target(self):
        self.entry['sha256'] = '0' * 64
        self.manifest.write_text(json.dumps({'format': 1, 'images': {'linux': self.entry}}))
        before = self.target.read_bytes()
        with patch.object(installer, 'environment', return_value=self.env), \
             patch.object(installer, 'source_is_separate'), \
             patch.object(installer, 'release_target') as release, \
             patch.object(installer, 'flash_archive') as flash, \
             self.assertRaises(installer.InstallError):
            installer.action('linux', self.root)
        release.assert_not_called(); flash.assert_not_called()
        self.assertEqual(self.target.read_bytes(), before)

    def test_cancellation_never_writes(self):
        before = self.target.read_bytes()
        with patch.object(installer, 'environment', return_value=self.env), \
             patch.object(installer, 'source_is_separate'), \
             patch.object(installer, 'release_target') as release, \
             patch.object(installer, 'flash_archive') as flash, \
             patch('builtins.input', return_value='cancel'):
            self.assertFalse(installer.action('linux', self.root))
        release.assert_not_called(); flash.assert_not_called()
        self.assertEqual(self.target.read_bytes(), before)

    def test_confirmed_action_writes_and_verifies_prefix(self):
        with patch.object(installer, 'environment', return_value=self.env), \
             patch.object(installer, 'source_is_separate'), \
             patch.object(installer, 'release_target') as release, \
             patch('builtins.input', return_value=f'INSTALL {self.target}'):
            self.assertTrue(installer.action('linux', self.root))
        release.assert_called_once_with(self.target)
        self.assertEqual(self.target.read_bytes(), self.data + b'x' * 1024)

    def test_readback_failure_is_reported(self):
        original_sync = installer.os.fsync
        def corrupt_after_sync(fd):
            original_sync(fd)
            with self.target.open('r+b') as f:
                f.write(b'!')
        with patch.object(installer.os, 'fsync', side_effect=corrupt_after_sync), \
             self.assertRaises(installer.InstallError) as error:
            installer.flash_archive(self.image, self.target, len(self.data), self.digest,
                                    lambda _: None, lambda _: None)
        self.assertEqual(error.exception.key, 'readback')

    def test_root_on_emmc_is_rejected(self):
        sys_block = self.root / 'sys'
        (sys_block / 'mmcblk9/device').mkdir(parents=True)
        (sys_block / 'mmcblk9/device/type').write_text('MMC\n')
        compatible = self.root / 'compatible'
        compatible.write_bytes(b'bozztek,pf818\0rockchip,rk3399\0')
        with patch.object(installer, 'SYS_BLOCK', sys_block), \
             patch.object(installer, 'COMPATIBLE', compatible), \
             patch.object(installer, 'run', side_effect=['/dev/mmcblk9p2', 'mmcblk9']), \
             self.assertRaises(installer.InstallError) as error:
            installer.environment()
        self.assertEqual(error.exception.key, 'sd')

    def test_source_on_target_is_rejected(self):
        with patch.object(installer, 'run', return_value='/dev/mmcblk1p2'), \
             patch.object(installer, 'target_devices', return_value={Path('/dev/mmcblk1p2')}), \
             self.assertRaises(installer.InstallError) as error:
            installer.source_is_separate(self.image, Path('/dev/mmcblk1'))
        self.assertEqual(error.exception.key, 'source')

    def test_release_only_target_mounts_and_swap(self):
        replies = [json.dumps({'swapdevices': [{'name': '/swap-on-target'}, {'name': '/swap-on-sd'}]}),
                   '/dev/mmcblk1p2', '/dev/mmcblk0p2',
                   json.dumps({'filesystems': [{'source': '/dev/mmcblk0p2', 'target': '/'},
                                               {'source': '/dev/mmcblk1p2', 'target': '/mnt/emmc'}]})]
        with patch.object(installer, 'target_devices', return_value={Path('/dev/mmcblk1'), Path('/dev/mmcblk1p2')}), \
             patch.object(installer, 'run', side_effect=replies), \
             patch.object(installer.subprocess, 'run') as command:
            installer.release_target(Path('/dev/mmcblk1'))
        self.assertEqual([call.args[0] for call in command.call_args_list],
                         [['swapoff', '/swap-on-target'], ['umount', '--', '/mnt/emmc']])

    def test_login_hint_and_environment(self):
        script = shlex.quote(str(HERE / 'pf818-live.sh'))
        tail = '; printf "ENV:%s|%s\\n" "$PF818_LIVE" "$PF818_INSTALLER"'
        plain = subprocess.run(['/bin/bash', '-c', '. ' + script + tail], text=True, capture_output=True, check=True)
        self.assertEqual(plain.stdout.strip(), 'ENV:1|/usr/local/sbin/pf818-install')
        interactive = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-ic', '. ' + script + tail],
                                     text=True, capture_output=True, check=True)
        self.assertIn('安装 Linux 或恢复 Android', interactive.stdout)
        self.assertIn('Install Linux or restore Android', interactive.stdout)
        self.assertIn('passwd', interactive.stdout)


if __name__ == '__main__':
    unittest.main()
