#!/usr/bin/env python3
"""Add PF818 scanner and lights to an R4 image without mounting or writing disks.

Accepts the R4 TF or eMMC .img (including .img.gz); no old JSON manifest needed.
Requires debugfs, e2fsck, tune2fs, dtc, fdtoverlay, fdtget and an ARM64 scanner binary.
"""
import argparse
from datetime import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import uuid
import zlib
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / 'adaptation/round5'
BUILD = REPO / 'build/round5/image'
DTB = 'rockchip/rk3399-pf818-r5.dtb'
KERNEL = '6.18.57-ophub'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(argv, accepted=(0,)):
    p = subprocess.run([str(a) for a in argv], text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    with (BUILD / 'build.log').open('a') as f:
        f.write(f'{argv!r}\n{p.stdout}\n')
    if p.returncode not in accepted:
        raise RuntimeError(f'{argv[0]} exited {p.returncode}:\n{p.stdout}')
    return p.stdout


def quoted(value):
    value = str(value)
    if any(c in value for c in '\\"\n\r'):
        raise ValueError(f'Unsupported debugfs path: {value!r}')
    return f'"{value}"'


def debug(image, commands, write=False):
    path = BUILD / 'debugfs.commands'
    path.write_text('\n'.join(commands) + '\n')
    result = run(['debugfs', *(['-w'] if write else []), '-f', path, image])
    if any(s in result for s in ('File not found', 'already exists', 'File exists',
                                'not found by ext2_lookup', 'Could not allocate',
                                'while looking up', "Couldn't parse", 'Usage:')):
        raise RuntimeError(result)
    return result


def exists(image, path):
    return 'Inode:' in run(['debugfs', '-R', f'stat {quoted(path)}', image])


def dump(image, source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    debug(image, [f'dump {quoted(source)} {quoted(target)}'])
    if not target.is_file():
        raise RuntimeError(f'Failed to extract {source}')
    return target


def remove(image, target):
    if exists(image, target):
        debug(image, [f'rm {quoted(target)}'], True)


def put(image, source, target, mode=0o644):
    parents = list(Path(target).parents)[:-1]
    for parent in reversed(parents):
        if not exists(image, parent):
            debug(image, [f'mkdir {quoted(parent)}'], True)
    remove(image, target)
    debug(image, [f'write {quoted(source)} {quoted(target)}',
                  f'set_inode_field {quoted(target)} uid 0',
                  f'set_inode_field {quoted(target)} gid 0',
                  f'set_inode_field {quoted(target)} mode 0{0o100000 | mode:o}'], True)


def textfile(name, content):
    p = BUILD / name
    p.write_text(content)
    return p


def read_gpt(path, *, fixed_layout=True):
    with path.open('rb') as f:
        headers = []
        for lba in (1, path.stat().st_size // 512 - 1):
            f.seek(lba * 512)
            h = bytearray(f.read(512))
            if h[:8] != b'EFI PART':
                raise ValueError('Expected a complete GPT R4 disk image')
            size, expected = struct.unpack_from('<II', h, 12)
            if not 92 <= size <= 512:
                raise ValueError('Invalid GPT header length')
            struct.pack_into('<I', h, 16, 0)
            if zlib.crc32(h[:size]) != expected:
                raise ValueError('GPT header CRC mismatch')
            struct.pack_into('<I', h, 16, expected)
            entry_lba, count, entry_size, crc = struct.unpack_from('<QIII', h, 72)
            if count > 4096 or entry_size != 128:
                raise ValueError('Unexpected GPT entry layout')
            f.seek(entry_lba * 512)
            entries = bytearray(f.read(count * entry_size))
            if zlib.crc32(entries) != crc:
                raise ValueError('GPT partition table CRC mismatch')
            headers.append((lba, h, entry_lba, entries))
        if headers[0][3] != headers[1][3]:
            raise ValueError('Primary and backup GPT entries differ')
        partitions = []
        for i in range(count):
            e = entries[i * 128:(i + 1) * 128]
            if e[:16] != bytes(16):
                start, end = struct.unpack_from('<QQ', e, 32)
                partitions.append((start * 512, (end - start + 1) * 512))
    if fixed_layout and partitions != [(32768 * 512, 128 * 1024**2), (294912 * 512, 2432 * 1024**2)]:
        raise ValueError(f'Expected the fixed R4 partition layout, got {partitions}')
    return headers, partitions


def refresh_gpt(path, headers):
    disk_guid = uuid.uuid4().bytes_le
    entries = bytearray(headers[0][3])
    for offset in range(0, len(entries), 128):
        if entries[offset:offset + 16] != bytes(16):
            entries[offset + 16:offset + 32] = uuid.uuid4().bytes_le
    with path.open('r+b') as f:
        for lba, original, entry_lba, _ in headers:
            h = bytearray(original)
            h[56:72] = disk_guid
            struct.pack_into('<I', h, 88, zlib.crc32(entries))
            struct.pack_into('<I', h, 16, 0)
            size = struct.unpack_from('<I', h, 12)[0]
            struct.pack_into('<I', h, 16, zlib.crc32(h[:size]))
            f.seek(entry_lba * 512); f.write(entries)
            f.seek(lba * 512); f.write(h)
    read_gpt(path)


def copy_region(source, target, offset, length):
    source.seek(offset)
    while length:
        chunk = source.read(min(length, 16 * 1024**2))
        if not chunk:
            raise EOFError('Image ended inside a partition')
        target.write(chunk)
        length -= len(chunk)


def region_sha(path, offset, length):
    h = hashlib.sha256()
    with path.open('rb') as f:
        f.seek(offset)
        while length:
            chunk = f.read(min(length, 16 * 1024**2))
            if not chunk:
                raise EOFError('Unexpected image end')
            h.update(chunk); length -= len(chunk)
    return h.hexdigest()


def verify_lights(dtb):
    """Check resolved GPIO controller/offset/polarity and off-at-boot settings."""
    for name, bank, offset in (('green', 1, 0), ('red', 2, 28), ('fill', 0, 6)):
        path = f'/pf818-leds/{name}'
        controller = int(run(['fdtget', '-t', 'x', dtb,
                              f'/pinctrl/gpio@{("ff720000", "ff730000", "ff780000")[bank]}', 'phandle']).strip(), 16)
        gpios = [int(v, 16) for v in run(['fdtget', '-t', 'x', dtb, path, 'gpios']).split()]
        if gpios != [controller, offset, 0]:
            raise ValueError(f'Wrong {name} LED GPIO: {gpios}')
        if run(['fdtget', dtb, path, 'default-state']).strip() != 'off':
            raise ValueError(f'{name} LED must be off by default')
        label = {'green': 'green:status', 'red': 'red:status', 'fill': 'white:flash'}[name]
        if run(['fdtget', dtb, path, 'label']).strip() != label:
            raise ValueError(f'Wrong {name} LED name')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=os.environ.get('PF818_R4_IMAGE'))
    parser.add_argument('--binary', type=Path, default=REPO / 'build/round5/pf818-scan')
    parser.add_argument('--target', choices=('tf', 'emmc', 'both'), default='both')
    parser.add_argument('--gzip', action='store_true', help='also create .img.gz')
    parser.add_argument('--gzip-only', action='store_true', help='retain only verified .img.gz and metadata')
    parser.add_argument('--cleanup', action='store_true', help='remove generated intermediate .img files after success')
    args = parser.parse_args()
    if args.source is None:
        parser.error('Set --source or PF818_R4_IMAGE to the R4 .img or .img.gz')
    source = args.source.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    if not source.is_file() or not binary.is_file():
        parser.error('Source image and compiled scanner binary must exist')
    elf = binary.read_bytes()[:20]
    if elf[:6] != b'\x7fELF\x02\x01' or len(elf) < 20 or struct.unpack_from('<H', elf, 18)[0] != 183:
        parser.error('--binary must be an ARM64 Linux ELF executable')
    for tool in ('debugfs', 'e2fsck', 'tune2fs', 'dtc', 'fdtoverlay', 'fdtget'):
        if shutil.which(tool) is None:
            parser.error(f'Missing build dependency: {tool}')
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'build.log').write_text('')
    generated_images = set()
    if source.suffix == '.gz':
        print('Decompress R4 source', flush=True)
        with gzip.open(source, 'rb') as src, (BUILD / 'source.img').open('wb') as dst:
            shutil.copyfileobj(src, dst, 16 * 1024**2)
        image = BUILD / 'source.img'
        generated_images.add(image)
    else:
        image = source
    headers, partitions = read_gpt(image)
    print('Extract and inspect R4 partitions', flush=True)
    for i, (offset, length) in enumerate(partitions, 1):
        part = BUILD / f'source-{i}.img'
        generated_images.add(part)
        with image.open('rb') as src, part.open('wb') as dst:
            copy_region(src, dst, offset, length)
    boot_source, root_source = BUILD / 'source-1.img', BUILD / 'source-2.img'
    release = dump(root_source, '/etc/pf818-release', BUILD / 'source-release').read_text()
    if not re.search(r'^ADAPTATION=R4$', release, re.M):
        raise ValueError('Source must be an R4 image')
    kernel_config = dump(boot_source, f'/config-{KERNEL}', BUILD / 'kernel.config').read_text()
    if 'CONFIG_USB_SERIAL_XR=m' not in kernel_config:
        raise ValueError('The tested xr_serial module is not enabled in this kernel')
    for option in ('CONFIG_LEDS_CLASS=y', 'CONFIG_LEDS_GPIO=y', 'CONFIG_LEDS_TRIGGER_TIMER=y'):
        if option not in kernel_config:
            raise ValueError(f'Missing built-in LED support: {option}')
    driver = f'/lib/modules/{KERNEL}/kernel/drivers/usb/serial/xr_serial.ko'
    dump(root_source, driver, BUILD / 'xr_serial.ko')
    if b'usb:v04E2p1402' not in (BUILD / 'xr_serial.ko').read_bytes():
        raise ValueError('xr_serial module lacks the scanner USB ID')
    base_dtb = dump(boot_source, '/dtb/rockchip/rk3399-pf818-r4.dtb', BUILD / 'r4.dtb')
    overlay = BUILD / 'pf818-scanner-power.dtbo'
    lights_overlay = BUILD / 'pf818-lights.dtbo'
    final_dtb = BUILD / 'rk3399-pf818-r5.dtb'
    run(['dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', overlay, CONFIG / 'pf818-scanner-power.dts'])
    run(['dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', lights_overlay, CONFIG / 'pf818-lights.dts'])
    run(['fdtoverlay', '-i', base_dtb, '-o', final_dtb, overlay, lights_overlay])
    run(['dtc', '-q', '-I', 'dtb', '-O', 'dts', '-o', BUILD / 'r5.dts', final_dtb])
    if 'pf818-scanner-power' not in (BUILD / 'r5.dts').read_text():
        raise ValueError('Scanner power overlay did not apply')
    verify_lights(final_dtb)
    # Read back these R4 components again after each build to check retention.
    retained = [driver, f'/lib/modules/{KERNEL}/extra/panel_pf818.ko',
                '/usr/local/lib/pf818-nfc/libpf818-reader.so',
                '/usr/local/lib/pf818-nfc/liblog.so', '/usr/local/sbin/pf818-nfc-read']
    original_hashes = {p: sha(dump(root_source, p, BUILD / 'retained' / p.lstrip('/'))) for p in retained}
    old_root_uuid = run(['tune2fs', '-l', root_source]).split('Filesystem UUID:')[1].split()[0]
    old_boot_uuid = run(['tune2fs', '-l', boot_source]).split('Filesystem UUID:')[1].split()[0]
    source_hash = sha(image)
    stamp = datetime.now(ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m-%d_%H%M')
    targets = ('tf', 'emmc') if args.target == 'both' else (args.target,)
    output = REPO / 'output'
    output.mkdir(exist_ok=True)
    for target in targets:
        print(f'Build R5 {target.upper()}', flush=True)
        boot, root = BUILD / 'bootfs.img', BUILD / 'rootfs.img'
        generated_images.update((boot, root))
        shutil.copyfile(boot_source, boot); shutil.copyfile(root_source, root)
        root_uuid, boot_uuid = str(uuid.uuid4()), str(uuid.uuid4())
        for part, value, label in ((root, root_uuid, 'ROOT'), (boot, boot_uuid, 'BOOT')):
            run(['tune2fs', '-U', value, '-L', f'PF818_{target.upper()}_{label}', part])
        for name in ('armbianEnv.txt', 'extlinux/extlinux.conf'):
            text = dump(boot, '/' + name, BUILD / name).read_text()
            text = text.replace(old_root_uuid, root_uuid).replace('rockchip/rk3399-pf818-r4.dtb', DTB)
            text = re.sub(r'PF818-R4(?:-EMMC|-TF)?', f'PF818-R5-{target.upper()}', text)
            put(boot, textfile('boot-config', text), '/' + name)
        put(boot, final_dtb, '/dtb/' + DTB)
        fstab = dump(root, '/etc/fstab', BUILD / 'fstab').read_text()
        fstab = fstab.replace(old_root_uuid, root_uuid).replace(old_boot_uuid, boot_uuid)
        put(root, textfile('fstab-new', fstab), '/etc/fstab')
        ophub = dump(root, '/etc/ophub-release', BUILD / 'ophub-release').read_text()
        put(root, textfile('ophub-new', ophub.replace('rk3399-pf818-r4.dtb', 'rk3399-pf818-r5.dtb')), '/etc/ophub-release')
        payload = [(binary, '/usr/local/bin/pf818-scan', 0o755),
                   (CONFIG / 'pf818-led', '/usr/local/bin/pf818-led', 0o755),
                   (CONFIG / '70-pf818-scanner.rules', '/etc/udev/rules.d/70-pf818-scanner.rules', 0o644),
                   (CONFIG / 'pf818-scanner.modules', '/etc/modules-load.d/pf818-scanner.conf', 0o644)]
        for src, dst, mode in payload:
            put(root, src, dst, mode)
        unit = '/etc/systemd/system/pf818-emmc-grow.service'
        link = '/etc/systemd/system/multi-user.target.wants/pf818-emmc-grow.service'
        remove(root, link); remove(root, unit)
        remove(root, '/var/lib/pf818/emmc-expanded')
        if target == 'emmc':
            script = (REPO / 'adaptation/emmc/pf818-emmc-grow').read_text().replace('@ROOT_UUID@', root_uuid)
            put(root, textfile('pf818-emmc-grow', script), '/usr/local/sbin/pf818-emmc-grow', 0o755)
            put(root, REPO / 'adaptation/emmc/pf818-emmc-grow.service', unit)
            debug(root, [f'symlink {quoted(link)} {quoted(unit)}'], True)
        else:
            debug(root, [f'symlink {quoted(unit)} /dev/null'], True)
        release_text = (f'ADAPTATION=R5\nSTORAGE_TARGET={target.upper()}\nBUILD_TIME={stamp}\n'
                        f'BASE_IMAGE={source.name}\nDEVICE_TREE={DTB}\nROOT_UUID={root_uuid}\n'
                        f'BOOT_UUID={boot_uuid}\nFIRST_BOOT_RESIZE={"emmc-only" if target == "emmc" else "false"}\n')
        put(root, textfile('pf818-release', release_text), '/etc/pf818-release')
        put(boot, textfile('PF818-R5.txt', release_text + 'Scanner: pf818-scan --once --timeout 30\nLights: pf818-led status; all off by default.\n'), '/PF818-R5.txt')
        checks = {}
        for src, dst, _ in payload:
            checks[dst] = sha(dump(root, dst, BUILD / 'readback' / dst.lstrip('/'))) == sha(src)
        for dst, expected in original_hashes.items():
            checks[dst + '_retained'] = sha(dump(root, dst, BUILD / 'readback' / dst.lstrip('/'))) == expected
        for name in (f'vmlinuz-{KERNEL}', f'initrd.img-{KERNEL}', f'uInitrd-{KERNEL}'):
            checks[name + '_retained'] = sha(dump(boot, '/' + name, BUILD / 'readback' / name)) == sha(dump(boot_source, '/' + name, BUILD / 'original' / name))
        checks['r5_dtb'] = sha(dump(boot, '/dtb/' + DTB, BUILD / 'readback.dtb')) == sha(final_dtb)
        verify_lights(BUILD / 'readback.dtb')
        checks['led_gpio_mapping_and_default_off'] = True
        boot_text = dump(boot, '/armbianEnv.txt', BUILD / 'verify-env').read_text()
        extlinux = dump(boot, '/extlinux/extlinux.conf', BUILD / 'verify-extlinux').read_text()
        checks['boot_config'] = all(root_uuid in text and DTB in text and old_root_uuid not in text for text in (boot_text, extlinux))
        checks['fstab'] = dump(root, '/etc/fstab', BUILD / 'verify-fstab').read_text() == fstab
        unit_stat = run(['debugfs', '-R', f'stat {quoted(unit)}', root])
        checks['grow_service'] = exists(root, link) if target == 'emmc' else 'Fast link dest: "/dev/null"' in unit_stat and not exists(root, link)
        for part in (boot, root):
            run(['e2fsck', '-f', '-n', part])
        checks['filesystem_checks'] = True
        if not all(checks.values()):
            raise RuntimeError(json.dumps(checks, indent=2))
        final = output / f'PF818_R5_{target.upper()}_Armbian_trixie_6.18.57_{stamp}.img'
        if final.exists():
            raise FileExistsError(f'Refusing to overwrite {final}')
        shutil.copyfile(image, final)
        with final.open('r+b') as dst:
            for part, (offset, length) in zip((boot, root), partitions):
                dst.seek(offset)
                with part.open('rb') as src:
                    copy_region(src, dst, 0, length)
        refresh_gpt(final, headers)
        for part, (offset, length) in zip((boot, root), partitions):
            checks[part.name + '_in_image'] = region_sha(final, offset, length) == sha(part)
        checks['bootloader_retained'] = region_sha(final, 34 * 512, 16 * 1024**2 - 34 * 512) == region_sha(image, 34 * 512, 16 * 1024**2 - 34 * 512)
        if not all(checks.values()):
            raise RuntimeError(json.dumps(checks, indent=2))
        manifest = {'adaptation': 'R5', 'storage_target': target.upper(), 'kernel': KERNEL,
                    'source': source.name, 'source_image_sha256': source_hash,
                    'image': final.name, 'image_bytes': final.stat().st_size, 'sha256': sha(final),
                    'build_time': stamp, 'dtb': DTB, 'root_uuid': root_uuid, 'boot_uuid': boot_uuid,
                    'first_boot_resize': 'emmc-only' if target == 'emmc' else False,
                    'scanner': {'usb_id': '04e2:1402', 'driver': 'xr_serial', 'device': '/dev/pf818-scanner',
                                'serial': '115200 8N1, no flow control', 'power': 'GPIO1_C7 high',
                                'android_hardware_test': 'static ARM64 Linux binary read known QR via factory Android kernel',
                                'r5_armbian_boot_test': False},
                    'lights': {'green': 'GPIO1_A0, upper left; green:status',
                               'red': 'GPIO2_D4, immediately right of green; red:status',
                               'fill': 'GPIO0_A6, white lights beside main camera; white:flash',
                               'active_high': True, 'default_state': 'off',
                               'driver': 'gpio-leds', 'android_gpio_and_visual_test': True,
                               'r5_armbian_boot_test': False},
                    'verification': checks, 'device_write_performed': False}
        final.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
        final.with_suffix('.img.sha256').write_text(f'{manifest["sha256"]}  {final.name}\n')
        if args.gzip or args.gzip_only:
            print(f'Compress {final.name}', flush=True)
            compressed = final.with_suffix('.img.gz')
            with final.open('rb') as src, gzip.open(compressed, 'wb', compresslevel=6) as dst:
                shutil.copyfileobj(src, dst, 16 * 1024**2)
            with gzip.open(compressed, 'rb') as src:
                readback_hash = hashlib.file_digest(src, 'sha256').hexdigest()
            if readback_hash != manifest['sha256']:
                raise ValueError('Compressed image readback hash differs from raw image')
            compressed_hash = sha(compressed)
            compressed.with_suffix('.gz.sha256').write_text(f'{compressed_hash}  {compressed.name}\n')
            manifest.update({'compressed_image': compressed.name,
                             'compressed_bytes': compressed.stat().st_size,
                             'compressed_sha256': compressed_hash})
            manifest['verification']['compressed_readback'] = True
            final.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
            if args.gzip_only:
                final.unlink()
        print(compressed if args.gzip_only else final, flush=True)
    if args.cleanup:
        for path in sorted(generated_images):
            path.unlink(missing_ok=True)
        print('Removed generated intermediate images; source backup retained.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, EOFError) as e:
        sys.exit(str(e))
