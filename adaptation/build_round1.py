#!/usr/bin/env python3
"""Repack the supplied ophub image offline; no mounts or package rebuilds."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import struct
import subprocess
import uuid
from datetime import datetime
REPO = Path(__file__).resolve().parent.parent
os.chdir(REPO)
SOURCE = Path(os.environ.get('PF818_BASE_IMAGE', str(REPO / 'Armbian_26.11.0_rockchip_sw799_trixie_6.18.57_server_2026.10.17.img')))
BUILD = REPO / 'build/round1'
CONFIG = REPO / 'adaptation/round1'
OUTPUT = REPO / f'output/PF818_R1_Armbian_trixie_6.18.57_{datetime.now():%Y-%m-%d_%H%M}.img'
KERNEL = '6.18.57-ophub'
BOOT_UUID = 'ee249ea8-b608-41dc-b6ac-717fb0fe5c04'
ROOT_UUID = '53322b0a-875e-476f-9d97-b2f9213af1cb'
ROOT_BLOCKS = 622592
BOOT_BYTES = 128 * 1024 * 1024

def run(args, *, data=None, log=None):
    result = subprocess.run([str(a) for a in args], input=data, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log:
        (BUILD / log).write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f'{args[0]} exited {result.returncode}:\n{result.stdout}')
    return result.stdout

def debugfs(image, commands, write=False):
    command_file = BUILD / 'debugfs.commands'
    command_file.write_text('\n'.join(commands) + '\n')
    args = ['debugfs'] + (['-w'] if write else []) + ['-f', command_file, image]
    result = run(args)
    with (BUILD / 'debugfs.log').open('a') as log:
        log.write(result)
    errors = ('File not found', 'already exists', 'not found by ext2_lookup', 'Could not allocate', 'while looking up', "Couldn't parse", 'Usage:')
    if any((error in result for error in errors)):
        raise RuntimeError(result)
    return result

def dump(image, source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    debugfs(image, [f'dump "{source}" "{target}"'])

def extract_partitions():
    with SOURCE.open('rb') as src:
        src.seek(512)
        header = src.read(512)
        entry_lba, count, entry_size = struct.unpack_from('<QII', header, 72)
        partitions = []
        for i in range(count):
            src.seek(entry_lba * 512 + i * entry_size)
            entry = src.read(entry_size)
            if entry[:16] == bytes(16):
                continue
            start, end = struct.unpack_from('<QQ', entry, 32)
            partitions.append((start * 512, (end - start + 1) * 512))
        for i, (offset, length) in enumerate(partitions, 1):
            target = BUILD / f'source-{i}.img'
            if target.exists() and target.stat().st_size == length:
                continue
            print(f'Extract partition {i}', flush=True)
            src.seek(offset)
            with target.open('wb') as dst:
                remaining = length
                while remaining:
                    chunk = src.read(min(remaining, 16 * 1024 * 1024))
                    dst.write(chunk)
                    remaining -= len(chunk)

def prepare_dtc():
    return ['dtc']

def prepare_boot(dtc):
    stage = BUILD / 'boot-stage'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    boot = BUILD / 'source-1.img'
    names = ['boot.cmd', 'boot.scr', 'boot.bmp', 'boot-desktop.png', 'armbian_first_run.txt.template', f'config-{KERNEL}', f'System.map-{KERNEL}', f'initrd.img-{KERNEL}', f'uInitrd-{KERNEL}', f'vmlinuz-{KERNEL}']
    for name in names:
        dump(boot, '/' + name, stage / name)
    original_dtb = BUILD / 'rk3399-bozz-sw799.dtb'
    dump(boot, '/dtb/rockchip/rk3399-bozz-sw799.dtb', original_dtb)
    run(dtc + ['-q', '-I', 'dtb', '-O', 'dts', '-o', BUILD / 'sw799.dts', original_dtb])
    dtbdir = stage / 'dtb/rockchip'
    dtbdir.mkdir(parents=True)
    shutil.copy2(original_dtb, dtbdir / original_dtb.name)
    run(dtc + ['-q', '-I', 'dts', '-O', 'dtb', '-o', dtbdir / 'rk3399-pf818.dtb', CONFIG / 'rk3399-pf818.dts'], log='dtc.log')
    run(dtc + ['-q', '-I', 'dtb', '-O', 'dts', '-o', BUILD / 'pf818.dts', dtbdir / 'rk3399-pf818.dtb'])
    (stage / 'Image').symlink_to(f'vmlinuz-{KERNEL}')
    (stage / 'uInitrd').symlink_to(f'uInitrd-{KERNEL}')
    (stage / f'dtb-{KERNEL}').symlink_to('dtb')
    (stage / 'armbianEnv.txt').write_text(f'verbosity=7\nbootlogo=false\nconsole=both\nearlycon=on\nfdtfile=rockchip/rk3399-pf818.dtb\nrootdev=UUID={ROOT_UUID}\nrootfstype=ext4\nrootflags=rw,errors=remount-ro\noverlay_prefix=rk3399\noverlays=\nextraargs=rw rootwait no_console_suspend plymouth.enable=0 usbcore.autosuspend=-1\nextraboardargs=net.ifnames=0\ndocker_optimizations=off\n')
    (stage / 'extlinux').mkdir()
    (stage / 'extlinux/extlinux.conf').write_text(f'DEFAULT PF818-R1\nTIMEOUT 10\nLABEL PF818-R1\n  LINUX /Image\n  INITRD /uInitrd\n  FDT /dtb/rockchip/rk3399-pf818.dtb\n  APPEND root=UUID={ROOT_UUID} rootwait rootfstype=ext4 rw console=ttyS2,1500000 console=tty1 earlycon loglevel=7 no_console_suspend consoleblank=0 net.ifnames=0 plymouth.enable=0 usbcore.autosuspend=-1\n')
    (stage / 'pf818-logs').mkdir()
    (stage / 'PF818-R1.txt').write_text('PF818 / SW799 R1, 2026-10-20\nHostname: pf818-r1; wired Ethernet: DHCP; SSH port: 22\nRoot password is inherited from the supplied ophub image: 1234\nAutomatic filesystem expansion is disabled.\nBoot diagnostics: /boot/pf818-logs/; journal: /var/log/journal/\n')
    boot_image = BUILD / 'bootfs.img'
    with boot_image.open('wb') as dst:
        dst.truncate(BOOT_BYTES)
    run(['mke2fs', '-q', '-F', '-t', 'ext4', '-b', '4096', '-I', '256', '-N', '4096', '-m', '0', '-O', '^64bit,^metadata_csum,^metadata_csum_seed,^orphan_file', '-E', 'root_owner=0:0,lazy_itable_init=0,lazy_journal_init=0', '-L', 'BOOT', '-U', BOOT_UUID, '-d', stage, boot_image], log='bootfs-create.log')
    commands = []
    for path in [stage] + sorted(stage.rglob('*')):
        name = '/' + str(path.relative_to(stage)) if path != stage else '/'
        commands += [f'set_inode_field "{name}" uid 0', f'set_inode_field "{name}" gid 0']
    debugfs(boot_image, commands, write=True)

def prepare_root():
    root = BUILD / 'rootfs.img'
    run(['cp', '--reflink=auto', BUILD / 'source-2.img', root])
    payload = BUILD / 'root-payload'
    payload.mkdir(exist_ok=True)
    commands = []

    def write(path, content, mode=420, replace=False):
        local = payload / path.lstrip('/')
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(content)
        if replace:
            commands.append(f'rm "{path}"')
        commands.extend([f'write "{local}" "{path}"', f'set_inode_field "{path}" mode 0{32768 | mode:o}', f'set_inode_field "{path}" uid 0', f'set_inode_field "{path}" gid 0'])

    def read(path):
        local = BUILD / 'readback.txt'
        dump(root, path, local)
        return local.read_text()
    write('/etc/hostname', 'pf818-r1\n', replace=True)
    write('/etc/machine-id', 'uninitialized\n', mode=292, replace=True)
    hosts = read('/etc/hosts')
    hosts = '\n'.join(('127.0.1.1\tpf818-r1' if line.startswith('127.0.1.1') else line for line in hosts.splitlines())) + '\n'
    write('/etc/hosts', hosts, replace=True)
    write('/etc/fstab', f'UUID={ROOT_UUID} / ext4 defaults,noatime,commit=10,errors=remount-ro 0 1\nUUID={BOOT_UUID} /boot ext4 defaults,noatime,commit=10 0 2\ntmpfs /tmp tmpfs defaults,nosuid 0 0\n', replace=True)
    write('/root/.no_rootfs_resize', 'no\n', replace=True)
    commands.append('rm "/root/.not_logged_in_yet"')
    for unit in ('armbian-resize-filesystem.service', 'armbian-firstrun.service'):
        commands += [f'rm "/etc/systemd/system/multi-user.target.wants/{unit}"', f'symlink "/etc/systemd/system/{unit}" /dev/null']
    for key in ('rsa', 'ecdsa', 'ed25519'):
        commands += [f'rm "/etc/ssh/ssh_host_{key}_key"', f'rm "/etc/ssh/ssh_host_{key}_key.pub"']
    write('/etc/NetworkManager/system-connections/pf818-wired.nmconnection', '[connection]\nid=pf818-wired\nuuid=1d9c4522-0468-4cda-a4cc-098bfb381818\ntype=ethernet\nautoconnect=true\nautoconnect-priority=100\nautoconnect-retries=0\n[ethernet]\n[ipv4]\nmethod=auto\ndhcp-hostname=pf818-r1\n[ipv6]\nmethod=auto\n', mode=384)
    write('/etc/modules-load.d/pf818.conf', 'cdc_ether\n')
    ramlog = read('/etc/default/armbian-ramlog').replace('ENABLED=true', 'ENABLED=false')
    write('/etc/default/armbian-ramlog', ramlog, replace=True)
    commands.append('mkdir "/etc/systemd/journald.conf.d"')
    write('/etc/systemd/journald.conf.d/pf818.conf', '[Journal]\nStorage=persistent\nSystemMaxUse=32M\nSystemKeepFree=128M\nSyncIntervalSec=15s\n')
    write('/usr/local/sbin/pf818-bootlog', (CONFIG / 'pf818-bootlog').read_text(), mode=493)
    for unit, target in (('pf818-bootlog.service', 'multi-user.target'), ('pf818-bootlog.timer', 'timers.target')):
        write(f'/etc/systemd/system/{unit}', (CONFIG / unit).read_text())
        commands.append(f'symlink "/etc/systemd/system/{target}.wants/{unit}" /etc/systemd/system/{unit}')
    release = read('/etc/ophub-release').replace("FDTFILE='rk3399-bozz-sw799.dtb'", "FDTFILE='rk3399-pf818.dtb'")
    write('/etc/ophub-release', release, replace=True)
    write('/etc/pf818-release', f'ADAPTATION=R1\nADAPTATION_DATE=2026-10-20\nSOURCE_IMAGE={SOURCE.name}\nDEVICE_TREE=rockchip/rk3399-pf818.dtb\n')
    debugfs(root, commands, write=True)
    run(['e2fsck', '-f', '-y', root], log='rootfs-fsck-before.log')
    run(['tune2fs', '-O', '^orphan_file', root], log='rootfs-tune.log')
    run(['resize2fs', '-f', root, str(ROOT_BLOCKS)], log='rootfs-resize.log')
    run(['e2fsck', '-f', '-n', root], log='rootfs-fsck-final.log')
    run(['e2fsck', '-f', '-n', BUILD / 'bootfs.img'], log='bootfs-fsck-final.log')

def assemble():
    OUTPUT.parent.mkdir(exist_ok=True)
    boot_start = 32768
    boot_sectors = BOOT_BYTES // 512
    root_start = boot_start + boot_sectors
    root_sectors = ROOT_BLOCKS * 8
    total_sectors = (root_start + root_sectors + 33 + 2047) // 2048 * 2048
    with SOURCE.open('rb') as src, OUTPUT.open('wb') as dst:
        dst.truncate(total_sectors * 512)
        dst.write(src.read(16 * 1024 * 1024))
        dst.seek(0)
        dst.write(bytes(34 * 512))
        for image, start in ((BUILD / 'bootfs.img', boot_start), (BUILD / 'rootfs.img', root_start)):
            dst.seek(start * 512)
            with image.open('rb') as part:
                shutil.copyfileobj(part, dst, length=16 * 1024 * 1024)
    table = f'label: gpt\nlabel-id: {uuid.uuid4()}\nunit: sectors\nstart={boot_start}, size={boot_sectors}, type=linux, name=BOOT\nstart={root_start}, size={root_sectors}, type=linux, name=ROOTFS\n'
    run(['sfdisk', '--wipe', 'never', '--wipe-partitions', 'never', OUTPUT], data=table, log='partition-create.log')
    run(['sfdisk', '--verify', OUTPUT], log='partition-verify.log')
    manifest = {'source': SOURCE.name, 'image': OUTPUT.name, 'image_bytes': OUTPUT.stat().st_size, 'boot_mib': 128, 'root_mib': 2432, 'first_boot_resize': False, 'kernel': KERNEL, 'dtb': 'rockchip/rk3399-pf818.dtb', 'hostname': 'pf818-r1', 'sha256': hashlib.file_digest(OUTPUT.open('rb'), 'sha256').hexdigest(), 'source_sha256': hashlib.file_digest(SOURCE.open('rb'), 'sha256').hexdigest()}
    OUTPUT.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
    OUTPUT.with_suffix('.img.sha256').write_text(f"{manifest['sha256']}  {OUTPUT.name}\n")
    (OUTPUT.parent / 'SHA256SUMS').write_text(f"{manifest['sha256']}  {OUTPUT.name}\n")
    print(json.dumps(manifest, indent=2), flush=True)

def verify_image(expected_boot=None):

    def region_hash(stream, offset, length):
        stream.seek(offset)
        digest = hashlib.sha256()
        while length:
            chunk = stream.read(min(length, 16 * 1024 * 1024))
            if not chunk:
                raise RuntimeError('Unexpected end of image')
            digest.update(chunk)
            length -= len(chunk)
        return digest.hexdigest()
    checks = {}
    with SOURCE.open('rb') as src, OUTPUT.open('rb') as image:
        offset, length = (34 * 512, 16 * 1024 * 1024 - 34 * 512)
        checks['bootloader_region_matches_source'] = region_hash(src, offset, length) == region_hash(image, offset, length)
        for name, start in (('bootfs.img', 32768), ('rootfs.img', 294912)):
            part = BUILD / name
            with part.open('rb') as stream:
                expected = hashlib.file_digest(stream, 'sha256').hexdigest()
            checks[name + '_matches_image'] = region_hash(image, start * 512, part.stat().st_size) == expected
    expected_boot = expected_boot or {}
    names = dict.fromkeys([f'vmlinuz-{KERNEL}', f'initrd.img-{KERNEL}', f'uInitrd-{KERNEL}', *expected_boot])
    for name in names:
        if name in expected_boot:
            expected = expected_boot[name]
            label = '_matches_input'
        else:
            expected = BUILD / ('original-' + name)
            dump(BUILD / 'source-1.img', '/' + name, expected)
            label = '_reused_verbatim'
        actual = BUILD / 'readback/boot' / name
        dump(BUILD / 'bootfs.img', '/' + name, actual)
        checks[name + label] = expected.read_bytes() == actual.read_bytes()
    if not all(checks.values()):
        raise RuntimeError(json.dumps(checks))
    (BUILD / 'verification.json').write_text(json.dumps(checks, indent=2) + '\n')
if __name__ == '__main__':
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'debugfs.log').write_text('')
    print('Reuse ophub partitions, kernel, initramfs, modules and packages', flush=True)
    extract_partitions()
    dtc = prepare_dtc()
    print('Build PF818 device tree and 128 MiB boot filesystem', flush=True)
    prepare_boot(dtc)
    print('Apply root filesystem settings and shrink to 2432 MiB', flush=True)
    prepare_root()
    print('Assemble Etcher-compatible GPT disk image', flush=True)
    assemble()
    verify_image()
