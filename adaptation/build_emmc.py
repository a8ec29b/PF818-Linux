#!/usr/bin/env python3
"""Prepare PF818 TF/eMMC images from the tested R4 image, entirely offline."""
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import sys
import os
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_round1 as base
REPO = base.REPO
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', choices=('tf', 'emmc'), default='emmc')
args = parser.parse_args()
EMMC = args.target == 'emmc'
TARGET = args.target.upper()
BUILD = REPO / f'build/{args.target}'
CONFIG = REPO / 'adaptation/emmc'
R4 = Path(os.environ.get('PF818_R4_IMAGE', str(REPO / 'output/PF818_R4_Armbian_trixie_6.18.57_2026-10-20_2021.img')))
STAMP = datetime.now().strftime('%Y-%m-%d_%H%M')
BOOT_UUID = str(uuid.uuid4())
ROOT_UUID = str(uuid.uuid4())
SOURCE_DTB = 'rockchip/rk3399-pf818-r4.dtb'
DTB = SOURCE_DTB
base.SOURCE = R4
base.BUILD = BUILD
FLAVOR = f'PF818_R4_{TARGET}'
base.OUTPUT = REPO / f'output/{FLAVOR}_Armbian_trixie_6.18.57_{STAMP}.img'

def edit_file(image, source, target, commands, mode=420):
    if 'Inode:' in base.run(['debugfs', '-R', f'stat "{target}"', image]):
        commands.append(f'rm "{target}"')
    commands.extend([f'write "{source}" "{target}"', f'set_inode_field "{target}" uid 0', f'set_inode_field "{target}" gid 0', f'set_inode_field "{target}" mode 0{32768 | mode:o}'])

def update_boot():
    image = BUILD / 'bootfs.img'
    base.run(['cp', '--reflink=auto', BUILD / 'source-1.img', image])
    base.run(['tune2fs', '-U', BOOT_UUID, '-L', f'PF818_{TARGET}_BOOT', image], log='bootfs-uuid.log')
    stage = BUILD / 'boot-stage'
    stage.mkdir(exist_ok=True)
    commands = []
    for name in ('armbianEnv.txt', 'extlinux/extlinux.conf'):
        local = stage / name
        base.dump(image, '/' + name, local)
        text = local.read_text().replace(base.ROOT_UUID, ROOT_UUID).replace(SOURCE_DTB, DTB).replace('PF818-R4', FLAVOR.replace('_', '-'))
        local.write_text(text)
        edit_file(image, local, '/' + name, commands)
    for name in ('PF818-R1.txt', 'PF818-R2.txt', 'PF818-R3.txt', 'PF818-R4.txt'):
        if 'Inode:' in base.run(['debugfs', '-R', f'stat /{name}', image]):
            commands.append(f'rm "/{name}"')
    note_name = FLAVOR.replace('_', '-') + '.txt'
    note = stage / note_name
    note.write_text(f'PF818 R4 {TARGET} image, {STAMP}\n' + 'R4 kernel and initramfs retained.\n' + f'R4 bootloader, modules and packages retained.\nDevice tree: {DTB}\n' + ('On eMMC boot, GPT partition 2 and ext4 grow once to available capacity.\nOn TF boot, partitions remain unchanged.\n' if EMMC else 'Fixed partitions; no first-boot expansion.\n') + f'ROOT UUID: {ROOT_UUID}\nBOOT UUID: {BOOT_UUID}\nEthernet DHCP; SSH root / 1234.\n')
    edit_file(image, note, '/' + note_name, commands)
    base.debugfs(image, commands, write=True)
    for name in (f'vmlinuz-{base.KERNEL}', f'initrd.img-{base.KERNEL}', f'uInitrd-{base.KERNEL}'):
        base.dump(image, '/' + name, stage / name)

def update_root():
    image = BUILD / 'rootfs.img'
    base.run(['cp', '--reflink=auto', BUILD / 'source-2.img', image])
    base.run(['tune2fs', '-U', ROOT_UUID, '-L', f'PF818_{TARGET}_ROOT', image], log='rootfs-uuid.log')
    commands = []
    fstab = BUILD / 'fstab'
    base.dump(image, '/etc/fstab', fstab)
    fstab.write_text(fstab.read_text().replace(base.ROOT_UUID, ROOT_UUID).replace(base.BOOT_UUID, BOOT_UUID))
    edit_file(image, fstab, '/etc/fstab', commands)
    if EMMC:
        grow = BUILD / 'pf818-emmc-grow'
        grow.write_text((CONFIG / 'pf818-emmc-grow').read_text().replace('@ROOT_UUID@', ROOT_UUID))
        edit_file(image, grow, '/usr/local/sbin/pf818-emmc-grow', commands, 493)
        edit_file(image, CONFIG / 'pf818-emmc-grow.service', '/etc/systemd/system/pf818-emmc-grow.service', commands)
        commands.append('symlink "/etc/systemd/system/multi-user.target.wants/pf818-emmc-grow.service" /etc/systemd/system/pf818-emmc-grow.service')
    release = BUILD / 'pf818-release'
    release.write_text(f"ADAPTATION=R4\nSTORAGE_TARGET={TARGET}\nBUILD_TIME={STAMP}\nBASE_IMAGE={R4.name}\nDEVICE_TREE={DTB}\nROOT_UUID={ROOT_UUID}\nBOOT_UUID={BOOT_UUID}\nFIRST_BOOT_RESIZE={('emmc-only' if EMMC else 'false')}\n")
    edit_file(image, release, '/etc/pf818-release', commands)
    base.debugfs(image, commands, write=True)

def verify_payload():
    checks = {}
    root = BUILD / 'rootfs.img'
    payload = [(BUILD / 'fstab', '/etc/fstab'), (BUILD / 'pf818-release', '/etc/pf818-release')]
    if EMMC:
        payload += [(BUILD / 'pf818-emmc-grow', '/usr/local/sbin/pf818-emmc-grow'), (CONFIG / 'pf818-emmc-grow.service', '/etc/systemd/system/pf818-emmc-grow.service')]
    for source, target in payload:
        local = BUILD / 'readback' / target.lstrip('/')
        base.dump(root, target, local)
        checks[target + '_matches'] = source.read_bytes() == local.read_bytes()
    for name in ('armbianEnv.txt', 'extlinux/extlinux.conf'):
        local = BUILD / 'readback/boot' / name
        base.dump(BUILD / 'bootfs.img', '/' + name, local)
        checks[name + '_root_uuid'] = f'UUID={ROOT_UUID}' in local.read_text() and base.ROOT_UUID not in local.read_text()
    for name, expected in (('bootfs', BOOT_UUID), ('rootfs', ROOT_UUID)):
        actual = base.run(['blkid', '-p', '-s', 'UUID', '-o', 'value', BUILD / f'{name}.img']).strip()
        checks[name + '_unique_uuid'] = actual == expected
    for name in ('armbian-resize-filesystem.service', 'armbian-firstrun.service'):
        stat = base.run(['debugfs', '-R', f'stat /etc/systemd/system/{name}', root])
        checks[name + '_still_masked'] = 'Fast link dest: "/dev/null"' in stat
    stat = base.run(['debugfs', '-R', 'stat /etc/systemd/system/multi-user.target.wants/pf818-emmc-grow.service', root])
    checks['emmc_grow_enabled' if EMMC else 'tf_grow_service_absent'] = 'Fast link dest: "/etc/systemd/system/pf818-emmc-grow.service"' in stat if EMMC else 'Inode:' not in stat
    for target in ('/var/lib/pf818/emmc-expanded', '/etc/systemd/user/obex.service.d/pf818-opp.conf', '/var/lib/bluetooth'):
        stat = base.run(['debugfs', '-R', f'stat "{target}"', root])
        checks[target + '_absent'] = 'Inode:' not in stat
    connections = base.run(['debugfs', '-R', 'ls -p /etc/NetworkManager/system-connections', root])
    profiles = [line.split('/')[5] for line in connections.splitlines() if line.startswith('/')]
    checks['only_wired_network_profile'] = sorted(set(profiles) - {'.', '..', 'lost+found'}) == ['pf818-wired.nmconnection']
    previous = json.loads(R4.with_suffix('.json').read_text())
    for target, expected in previous['payload_sha256'].items():
        local = BUILD / 'readback' / target.lstrip('/')
        base.dump(root, target, local)
        checks[target + '_retained'] = hashlib.file_digest(local.open('rb'), 'sha256').hexdigest() == expected
    original_dtb, final_dtb = (BUILD / 'r4-original.dtb', BUILD / 'r4-final.dtb')
    base.dump(BUILD / 'bootfs.img', '/dtb/' + DTB, final_dtb)
    base.dump(BUILD / 'source-1.img', '/dtb/' + SOURCE_DTB, original_dtb)
    checks['r4_dtb_reused_verbatim'] = original_dtb.read_bytes() == final_dtb.read_bytes()
    if EMMC:
        base.run(['bash', '-n', BUILD / 'pf818-emmc-grow'])
    (BUILD / 'payload-verification.json').write_text(json.dumps(checks, indent=2) + '\n')
    if not all(checks.values()):
        raise RuntimeError(json.dumps(checks, indent=2))

def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'debugfs.log').write_text('')
    base.extract_partitions()
    update_boot()
    update_root()
    verify_payload()
    for name in ('bootfs', 'rootfs'):
        base.run(['e2fsck', '-f', '-n', BUILD / f'{name}.img'], log=f'{name}-fsck-final.log')
    base.assemble()
    base.verify_image(None)
    manifest_path = base.OUTPUT.with_suffix('.json')
    previous = json.loads(R4.with_suffix('.json').read_text())
    manifest = json.loads(manifest_path.read_text())
    manifest.update({key: previous[key] for key in ('bluez_version', 'wifi', 'bluetooth', 'modem', 'nfc', 'modem_validation', 'qmi_service_count', 'payload_sha256')})
    manifest.update({'adaptation': 'R4', 'storage_target': TARGET, 'build_time': STAMP, 'dtb': DTB, 'first_boot_resize': 'emmc-only' if EMMC else False, 'root_uuid': ROOT_UUID, 'boot_uuid': BOOT_UUID, 'resize_method': 'sfdisk GPT relocation and partition 2 growth, partx, resize2fs', 'device_write_performed': False})
    if not EMMC:
        del manifest['resize_method']
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    (BUILD / 'output-path.txt').write_text(str(base.OUTPUT) + '\n')
    print(base.OUTPUT, flush=True)
if __name__ == '__main__':
    main()
