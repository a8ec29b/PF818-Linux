#!/usr/bin/env python3
"""Add the verified Bluetooth and EC20 configuration to the R2 TF image."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_round1 as base
REPO = base.REPO
BUILD = REPO / 'build/round3'
CONFIG = REPO / 'adaptation/round3'
R2 = Path(os.environ.get('PF818_R2_IMAGE', str(REPO / 'output/PF818_R2_Armbian_trixie_6.18.57_2026-10-20_1829.img')))
STAMP = datetime.now().strftime('%Y-%m-%d_%H%M')
PACKAGE = BUILD / 'bluez_5.82-1.1+rpt2_arm64.deb'
base.SOURCE = R2
base.BUILD = BUILD
base.OUTPUT = REPO / f'output/PF818_R3_Armbian_trixie_6.18.57_{STAMP}.img'

def update_boot():
    image = BUILD / 'bootfs.img'
    base.run(['cp', '--reflink=auto', BUILD / 'source-1.img', image])
    stage = BUILD / 'boot-stage'
    stage.mkdir(exist_ok=True)
    dtb = BUILD / 'rk3399-pf818-r3.dtb'
    base.run(['dtc', '-q', '-I', 'dts', '-O', 'dtb', '-o', dtb, CONFIG / 'rk3399-pf818-r3.dts'])
    commands = [f'write "{dtb}" "/dtb/rockchip/{dtb.name}"']
    for name in ('armbianEnv.txt', 'extlinux/extlinux.conf'):
        local = stage / name
        base.dump(image, '/' + name, local)
        local.write_text(local.read_text().replace('rk3399-pf818-r2.dtb', dtb.name).replace('PF818-R2', 'PF818-R3'))
        commands += [f'rm "/{name}"', f'write "{local}" "/{name}"']
    note = stage / 'PF818-R3.txt'
    note.write_text(f'PF818 R3, {STAMP}\nBCM43430 2.4 GHz Wi-Fi; use AP channels 1-11.\nAP6212A Bluetooth on UART0; EC20 power on GPIO1_A1.\nModem status: pf818-modem-status.\nLandscape login, touchscreen and six buttons inherited from R2.\nFixed TF partitions; Ethernet DHCP; root / 1234.\n')
    commands.append(f'write "{note}" "/PF818-R3.txt"')
    base.debugfs(image, commands, write=True)
    for name in (f'vmlinuz-{base.KERNEL}', f'initrd.img-{base.KERNEL}', f'uInitrd-{base.KERNEL}'):
        base.dump(image, '/' + name, stage / name)

def update_root():
    image = BUILD / 'rootfs.img'
    base.run(['cp', '--reflink=auto', BUILD / 'source-2.img', image])
    package = BUILD / 'bluez-package'
    base.run(['dpkg-deb', '-x', PACKAGE, package])
    commands = []
    directories = set()

    def exists(target):
        return 'Inode:' in base.run(['debugfs', '-R', f'stat "{target}"', image])

    def directory(target):
        if target not in directories:
            if not exists(target):
                commands.append(f'mkdir "{target}"')
            directories.add(target)

    def write(source, target, mode=420, gid=0):
        if exists(target):
            commands.append(f'rm "{target}"')
        commands.extend([f'write "{source}" "{target}"', f'set_inode_field "{target}" uid 0', f'set_inode_field "{target}" gid {gid}', f'set_inode_field "{target}" mode 0{32768 | mode:o}'])
    for source in sorted(package.rglob('*')):
        target = '/' + str(source.relative_to(package))
        if source.is_symlink():
            commands.append(f'symlink "{target}" "{os.readlink(source)}"')
        elif source.is_dir():
            directory(target)
        else:
            write(source, target, source.stat().st_mode & 511)
    for source in sorted((BUILD / 'var/lib/dpkg/info').glob('bluez.*')):
        write(source, '/var/lib/dpkg/info/' + source.name, source.stat().st_mode & 511)
    status = BUILD / 'dpkg-status'
    base.dump(image, '/var/lib/dpkg/status', status)
    status.write_text(status.read_text().rstrip() + '\n\n' + (BUILD / 'pf818-r3-bluez.status').read_text().rstrip() + '\n\n')
    write(status, '/var/lib/dpkg/status')
    for name, entry, mode, gid in (('group', 'bluetooth:x:109:', 420, 0), ('gshadow', 'bluetooth:!::', 416, 42)):
        local = BUILD / name
        base.dump(image, '/etc/' + name, local)
        local.write_text(local.read_text().rstrip() + '\n' + entry + '\n')
        write(local, '/etc/' + name, mode, gid)
    directory('/etc/systemd/system/bluetooth.target.wants')
    directory('/etc/systemd/user')
    directory('/etc/systemd/user/default.target.wants')
    for target, link in (('/etc/systemd/system/dbus-org.bluez.service', '/usr/lib/systemd/system/bluetooth.service'), ('/etc/systemd/system/bluetooth.target.wants/bluetooth.service', '/usr/lib/systemd/system/bluetooth.service'), ('/etc/systemd/user/default.target.wants/mpris-proxy.service', '/usr/lib/systemd/user/mpris-proxy.service')):
        commands.append(f'symlink "{target}" "{link}"')
    write(CONFIG / 'read-modem.py', '/usr/local/sbin/pf818-modem-status', 493)
    release = BUILD / 'pf818-release'
    release.write_text(f'ADAPTATION=R3\nBUILD_TIME={STAMP}\nBASE_IMAGE={R2.name}\nDEVICE_TREE=rockchip/rk3399-pf818-r3.dtb\n')
    write(release, '/etc/pf818-release')
    ophub = BUILD / 'ophub-release'
    base.dump(image, '/etc/ophub-release', ophub)
    ophub.write_text(ophub.read_text().replace('rk3399-pf818-r2.dtb', 'rk3399-pf818-r3.dtb'))
    write(ophub, '/etc/ophub-release')
    base.debugfs(image, commands, write=True)

def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'debugfs.log').write_text('')
    base.extract_partitions()
    update_boot()
    update_root()
    for name in ('bootfs', 'rootfs'):
        base.run(['e2fsck', '-f', '-n', BUILD / f'{name}.img'], log=f'{name}-fsck-final.log')
    base.assemble()
    base.verify_image()
    manifest_path = base.OUTPUT.with_suffix('.json')
    manifest = json.loads(manifest_path.read_text())
    manifest.update({'adaptation': 'R3', 'build_time': STAMP, 'dtb': 'rockchip/rk3399-pf818-r3.dtb', 'bluez_version': '5.82-1.1+rpt2', 'bluez_deb_sha256': hashlib.file_digest(PACKAGE.open('rb'), 'sha256').hexdigest(), 'wifi': 'BCM43430/1, 2.4 GHz; AP channel 6 verified', 'bluetooth': 'BCM43430A1, UART0, existing AP6212 HCD', 'modem': 'Quectel EC20F, GPIO1_A1, option + qmi_wwan'})
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(base.OUTPUT)
if __name__ == '__main__':
    main()
