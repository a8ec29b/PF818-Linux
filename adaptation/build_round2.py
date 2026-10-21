#!/usr/bin/env python3
"""Add the PF818 panel and inputs to the known working R1 TF image."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
import os
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_round1 as base
REPO = base.REPO
BUILD = REPO / 'build/round2'
CONFIG = REPO / 'adaptation/round2'
R1 = Path(os.environ.get('PF818_R1_IMAGE', str(REPO / 'output/PF818_R1_Armbian_trixie_6.18.57_2026-10-20.img')))
STAMP = datetime.now().strftime('%Y-%m-%d_%H%M')
base.SOURCE = R1
base.BUILD = BUILD
base.OUTPUT = REPO / f'output/PF818_R2_Armbian_trixie_6.18.57_{STAMP}.img'

def update_boot():
    image = BUILD / 'bootfs.img'
    base.run(['cp', '--reflink=auto', BUILD / 'source-1.img', image])
    stage = BUILD / 'boot-stage'
    stage.mkdir(exist_ok=True)
    dtc = ['dtc']
    base.run(dtc + ['-q', '-I', 'dts', '-O', 'dtb', '-o', BUILD / 'rk3399-pf818-r2.dtb', CONFIG / 'rk3399-pf818-r2.dts'])
    commands = [f'''write "{BUILD / 'rk3399-pf818-r2.dtb'}" "/dtb/rockchip/rk3399-pf818-r2.dtb"''']
    for name in ('armbianEnv.txt', 'extlinux/extlinux.conf'):
        local = stage / name
        base.dump(image, '/' + name, local)
        text = local.read_text().replace('rk3399-pf818.dtb', 'rk3399-pf818-r2.dtb')
        text = text.replace('PF818-R1', 'PF818-R2')
        local.write_text(text)
        commands += [f'rm "/{name}"', f'write "{local}" "/{name}"']
    note = stage / 'PF818-R2.txt'
    note.write_text(f'PF818 R2, {STAMP}\nDSI0 M08 panel; landscape login with fbterm.\nGoodix GT911 touch; GPIO power key and five SARADC keys.\nHostname: pf818-r1; Ethernet DHCP; root / 1234; SSH port 22.\nFixed TF partitions. Boot logs: /boot/pf818-logs/.\n')
    commands.append(f'write "{note}" "/PF818-R2.txt"')
    base.debugfs(image, commands, write=True)
    for name in (f'vmlinuz-{base.KERNEL}', f'initrd.img-{base.KERNEL}', f'uInitrd-{base.KERNEL}'):
        base.dump(image, '/' + name, stage / name)

def update_root():
    image = BUILD / 'rootfs.img'
    base.run(['cp', '--reflink=auto', BUILD / 'source-2.img', image])
    payload = BUILD / 'root-payload'
    payload.mkdir(exist_ok=True)
    commands = []

    def write(source, target, *, replace=False, mode=420):
        if replace:
            commands.append(f'rm "{target}"')
        commands.extend([f'write "{source}" "{target}"', f'set_inode_field "{target}" uid 0', f'set_inode_field "{target}" gid 0', f'set_inode_field "{target}" mode 0{32768 | mode:o}'])
    commands.append(f'mkdir "/usr/lib/modules/{base.KERNEL}/extra"')
    for source in sorted((BUILD / 'runtime-files/lib/modules' / base.KERNEL).rglob('*')):
        if source.is_file():
            target = f'/usr/lib/modules/{base.KERNEL}/' + str(source.relative_to(BUILD / 'runtime-files/lib/modules' / base.KERNEL))
            write(source, target, replace=source.name.startswith('modules.'))
    for source in sorted((BUILD / 'runtime-files/var/lib/dpkg/info').iterdir()):
        write(source, '/var/lib/dpkg/info/' + source.name)
    package = BUILD / 'fbterm-package'
    base.run(['dpkg-deb', '-x', BUILD / 'fbterm_1.7-5+b1_arm64.deb', package])
    commands += ['mkdir "/usr/share/doc/fbterm"']
    for source in sorted(package.rglob('*')):
        if source.is_file():
            mode = 493 if source.name == 'fbterm' and source.parent.name == 'bin' else 420
            write(source, '/' + str(source.relative_to(package)), mode=mode)
    status = payload / 'dpkg-status'
    base.dump(image, '/var/lib/dpkg/status', status)
    status.write_text(status.read_text().rstrip() + '\n\n' + (BUILD / 'fbterm.status').read_text().rstrip() + '\n\n')
    write(status, '/var/lib/dpkg/status', replace=True)
    commands.append('mkdir "/etc/systemd/system/getty@tty1.service.d"')
    write(CONFIG / 'zz-pf818-landscape.conf', '/etc/systemd/system/getty@tty1.service.d/zz-pf818-landscape.conf')
    load = payload / 'pf818-display.conf'
    load.write_text('panel_pf818\n')
    write(load, '/etc/modules-load.d/pf818-display.conf')
    release = payload / 'pf818-release'
    release.write_text(f'ADAPTATION=R2\nBUILD_TIME={STAMP}\nBASE_IMAGE={R1.name}\nDEVICE_TREE=rockchip/rk3399-pf818-r2.dtb\n')
    write(release, '/etc/pf818-release', replace=True)
    ophub = payload / 'ophub-release'
    base.dump(image, '/etc/ophub-release', ophub)
    ophub.write_text(ophub.read_text().replace('rk3399-pf818.dtb', 'rk3399-pf818-r2.dtb'))
    write(ophub, '/etc/ophub-release', replace=True)
    base.debugfs(image, commands, write=True)

def main():
    BUILD.mkdir(exist_ok=True)
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
    manifest.update({'adaptation': 'R2', 'build_time': STAMP, 'dtb': 'rockchip/rk3399-pf818-r2.dtb', 'panel_module_sha256': hashlib.file_digest((BUILD / 'panel_pf818.ko').open('rb'), 'sha256').hexdigest(), 'fbterm_version': '1.7-5+b1', 'panel': 'DSI0 1200x1920 at 60 Hz', 'console': 'fbterm, clockwise 90 degrees'})
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(base.OUTPUT)
if __name__ == '__main__':
    main()
