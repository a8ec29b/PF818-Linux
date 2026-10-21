#!/usr/bin/env python3
"""Integrate the verified PF818 NFC reader and modem tools into the R3 image."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import os
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_round1 as base
REPO = base.REPO
BUILD = REPO / 'build/round4/image'
CONFIG = REPO / 'adaptation/round4'
READER = REPO / 'build/round4/linux-reader'
R3 = Path(os.environ.get('PF818_R3_IMAGE', str(REPO / 'output/PF818_R3_Armbian_trixie_6.18.57_2026-10-20_1856.img')))
STAMP = datetime.now().strftime('%Y-%m-%d_%H%M')
DTB = 'rk3399-pf818-r4.dtb'
base.SOURCE = R3
base.BUILD = BUILD
base.OUTPUT = REPO / f'output/PF818_R4_Armbian_trixie_6.18.57_{STAMP}.img'
PAYLOAD = [(CONFIG / '70-pf818-nfc.rules', '/etc/udev/rules.d/70-pf818-nfc.rules', 420), (CONFIG / 'pf818-nfc-bind', '/usr/local/sbin/pf818-nfc-bind', 493), (CONFIG / 'pf818-nfc-read', '/usr/local/sbin/pf818-nfc-read', 493), (CONFIG / 'reader/read-uid.py', '/usr/local/lib/pf818-nfc/read-uid.py', 420), (READER / 'libpf818-reader.so', '/usr/local/lib/pf818-nfc/libpf818-reader.so', 420), (READER / 'liblog.so', '/usr/local/lib/pf818-nfc/liblog.so', 420), (CONFIG / 'read-modem.py', '/usr/local/sbin/pf818-modem-status', 493), (CONFIG / 'read-qmi.py', '/usr/local/sbin/pf818-qmi-status', 493)]

def update_boot():
    image = BUILD / 'bootfs.img'
    base.run(['cp', '--reflink=auto', BUILD / 'source-1.img', image])
    stage = BUILD / 'boot-stage'
    stage.mkdir(exist_ok=True)
    dtb = BUILD / DTB
    dtc = ['dtc']
    base.run(dtc + ['-q', '-I', 'dts', '-O', 'dtb', '-o', dtb, CONFIG / 'rk3399-pf818-r4.dts'])
    base.run(dtc + ['-q', '-I', 'dtb', '-O', 'dts', '-o', BUILD / 'compiled.dts', dtb])
    commands = [f'write "{dtb}" "/dtb/rockchip/{DTB}"']
    for name in ('armbianEnv.txt', 'extlinux/extlinux.conf'):
        local = stage / name
        base.dump(image, '/' + name, local)
        local.write_text(local.read_text().replace('rk3399-pf818-r3.dtb', DTB).replace('PF818-R3', 'PF818-R4'))
        commands += [f'rm "/{name}"', f'write "{local}" "/{name}"']
    note = stage / 'PF818-R4.txt'
    note.write_text(f'PF818 R4, {STAMP}\nSPI0 NFC reader with GPIO3_B2 low; UID tool: pf818-nfc-read.\nEC20 QMI query: pf818-qmi-status; SIM/ICCID: pf818-modem-status.\nLandscape console, touch, six buttons, USB, Ethernet and wireless inherited from R3.\nFixed TF partitions; Ethernet DHCP; root / 1234.\n')
    commands.append(f'write "{note}" "/PF818-R4.txt"')
    base.debugfs(image, commands, write=True)
    for name in (f'vmlinuz-{base.KERNEL}', f'initrd.img-{base.KERNEL}', f'uInitrd-{base.KERNEL}'):
        base.dump(image, '/' + name, stage / name)

def update_root():
    image = BUILD / 'rootfs.img'
    base.run(['cp', '--reflink=auto', BUILD / 'source-2.img', image])
    commands = ['mkdir "/usr/local/lib/pf818-nfc"']

    def write(source, target, mode=420):
        if 'Inode:' in base.run(['debugfs', '-R', f'stat "{target}"', image]):
            commands.append(f'rm "{target}"')
        commands.extend([f'write "{source}" "{target}"', f'set_inode_field "{target}" uid 0', f'set_inode_field "{target}" gid 0', f'set_inode_field "{target}" mode 0{32768 | mode:o}'])
    for source, target, mode in PAYLOAD:
        write(source, target, mode)
    release = BUILD / 'pf818-release'
    release.write_text(f'ADAPTATION=R4\nBUILD_TIME={STAMP}\nBASE_IMAGE={R3.name}\nDEVICE_TREE=rockchip/{DTB}\n')
    write(release, '/etc/pf818-release')
    ophub = BUILD / 'ophub-release'
    base.dump(image, '/etc/ophub-release', ophub)
    ophub.write_text(ophub.read_text().replace('rk3399-pf818-r3.dtb', DTB))
    write(ophub, '/etc/ophub-release')
    base.debugfs(image, commands, write=True)

def verify_payload():
    checks = {}
    image = BUILD / 'rootfs.img'
    for source, target, mode in PAYLOAD:
        local = BUILD / 'readback' / target.lstrip('/')
        base.dump(image, target, local)
        checks[target] = local.read_bytes() == source.read_bytes()
    for name in ('armbian-resize-filesystem.service', 'armbian-firstrun.service'):
        stat = base.run(['debugfs', '-R', f'stat /etc/systemd/system/{name}', image])
        checks[name + '_masked'] = 'Fast link dest: "/dev/null"' in stat
    for path in ('/etc/systemd/user/obex.service.d/pf818-opp.conf', '/var/lib/bluetooth'):
        stat = base.run(['debugfs', '-R', f'stat {path}', image])
        checks[path + '_absent'] = 'Inode:' not in stat
    connections = base.run(['debugfs', '-R', 'ls -p /etc/NetworkManager/system-connections', image])
    profiles = [line.split('/')[5] for line in connections.splitlines() if line.startswith('/')]
    checks['only_wired_network_profile'] = sorted(set(profiles) - {'.', '..', 'lost+found'}) == ['pf818-wired.nmconnection']
    dtb_readback = BUILD / 'readback.dtb'
    base.dump(BUILD / 'bootfs.img', '/dtb/rockchip/' + DTB, dtb_readback)
    checks['dtb_in_boot'] = dtb_readback.read_bytes() == (BUILD / DTB).read_bytes()
    (BUILD / 'payload-verification.json').write_text(json.dumps(checks, indent=2) + '\n')
    if not all(checks.values()):
        raise RuntimeError(json.dumps(checks, indent=2))

def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'debugfs.log').write_text('')
    print('Extract clean R3 partitions', flush=True)
    base.extract_partitions()
    update_boot()
    update_root()
    verify_payload()
    for name in ('bootfs', 'rootfs'):
        base.run(['e2fsck', '-f', '-n', BUILD / f'{name}.img'], log=f'{name}-fsck-final.log')
    print('Assemble and verify fixed-size TF image', flush=True)
    base.assemble()
    base.verify_image()
    manifest_path = base.OUTPUT.with_suffix('.json')
    manifest = json.loads(manifest_path.read_text())
    previous = json.loads(R3.with_suffix('.json').read_text())
    manifest.update({key: previous[key] for key in ('bluez_version', 'wifi', 'bluetooth', 'modem')})
    manifest.update({'adaptation': 'R4', 'build_time': STAMP, 'dtb': 'rockchip/' + DTB, 'nfc': 'SPI0 CS0, 1 MHz, GPIO3_B2 output-low; ISO14443-A UID', 'modem_validation': 'qmicli DMS GetModel and QMI CTL GetVersionInfo succeeded; replacement SIM ICCID read', 'qmi_service_count': 30, 'payload_sha256': {target: hashlib.file_digest(source.open('rb'), 'sha256').hexdigest() for source, target, mode in PAYLOAD}})
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(base.OUTPUT, flush=True)
if __name__ == '__main__':
    main()
