#!/usr/bin/env python3
"""Exercise LED selection and trigger transitions against temporary sysfs files."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

loader = importlib.machinery.SourceFileLoader('pf818_led', str(Path(__file__).with_name('pf818-led')))
spec = importlib.util.spec_from_loader(loader.name, loader)
led = importlib.util.module_from_spec(spec)
loader.exec_module(led)


class LightsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        led.ROOT = Path(self.temp.name)
        for name in led.LIGHTS.values():
            path = led.ROOT / name
            path.mkdir()
            for file, content in {'brightness': '0\n', 'max_brightness': '1\n',
                                  'trigger': '[none] timer\n', 'delay_on': '500\n',
                                  'delay_off': '500\n'}.items():
                (path / file).write_text(content)

    def tearDown(self):
        self.temp.cleanup()

    def read(self, light, file):
        return (led.ROOT / led.LIGHTS[light] / file).read_text().strip()

    def test_fill_changes_only_white_camera_light(self):
        self.assertEqual(led.main(['fill', 'on']), 0)
        self.assertEqual(self.read('fill', 'brightness'), '1')
        self.assertEqual(self.read('green', 'brightness'), '0')
        self.assertEqual(self.read('red', 'brightness'), '0')
        self.assertEqual(led.main(['fill', 'off']), 0)
        self.assertEqual(self.read('fill', 'brightness'), '0')

    def test_blink_then_off_clears_trigger(self):
        self.assertEqual(led.main(['red', 'blink', '--on-ms', '200', '--off-ms', '800']), 0)
        self.assertEqual(self.read('red', 'trigger'), 'timer')
        self.assertEqual(self.read('red', 'delay_on'), '200')
        self.assertEqual(self.read('red', 'delay_off'), '800')
        self.assertEqual(self.read('green', 'brightness'), '0')
        self.assertEqual(led.main(['red', 'off']), 0)
        self.assertEqual(self.read('red', 'trigger'), 'none')
        self.assertEqual(self.read('red', 'brightness'), '0')

    def test_status_reports_active_trigger_without_writes(self):
        (led.ROOT / led.LIGHTS['green'] / 'trigger').write_text('none [timer]\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(led.main(['status']), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data['green']['trigger'], 'timer')
        self.assertEqual(set(data), {'green', 'red', 'fill'})
        self.assertEqual(self.read('green', 'trigger'), 'none [timer]')

    def test_rejected_fill_blink_has_no_side_effects(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            led.main(['fill', 'blink'])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.read('fill', 'brightness'), '0')
        self.assertEqual(self.read('fill', 'trigger'), '[none] timer')


if __name__ == '__main__':
    unittest.main()
