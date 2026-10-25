#!/usr/bin/env python3
"""Build a >=16GB PF818 Live SD image containing Linux and Android installers."""
import argparse
from datetime import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import uuid
import zlib
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_round5 as base

REPO = base.REPO
BUILD = REPO / 'build/live'
CONFIG = REPO / 'adaptation/live'
ROOT_BYTES = 8192 * 1024**2
BOOT_START = 32768
ROOT_START = 294912
base.BUILD = BUILD


def raw_metadata(path):
    digest, length = hashlib.sha256(), 0
    with gzip.open(path, 'rb') as source:
        while chunk := source.read(16 * 1024**2):
            length += len(chunk)
            digest.update(chunk)
    return length, digest.hexdigest()


def write_live_gpt(path, headers, root_bytes=ROOT_BYTES):
    """Retain the two partition starts, enlarge ROOTFS, and relocate backup GPT."""
    sectors = path.stat().st_size // 512
    root_end = ROOT_START + root_bytes // 512 - 1
    entries = bytearray(headers[0][3])
    entry_sectors = (len(entries) + 511) // 512
    backup_entries = sectors - 1 - entry_sectors
    last_usable = backup_entries - 1
    if root_end > last_usable:
        raise ValueError('Root partition overlaps backup GPT')
    struct.pack_into('<Q', entries, 128 + 40, root_end)
    entries[56:128] = 'BOOT'.encode('utf-16-le').ljust(72, b'\0')
    entries[128 + 56:256] = 'LIVE_ROOT'.encode('utf-16-le').ljust(72, b'\0')
    for offset in range(0, len(entries), 128):
        if entries[offset:offset + 16] != bytes(16):
            entries[offset + 16:offset + 32] = uuid.uuid4().bytes_le
    disk_guid = uuid.uuid4().bytes_le
    with path.open('r+b') as image:
        image.seek(0)
        mbr = bytearray(image.read(512))
        struct.pack_into('<II', mbr, 446 + 8, 1, min(sectors - 1, 0xffffffff))
        image.seek(0); image.write(mbr)
        for index, lba, table_lba, alternative in ((0, 1, 2, sectors - 1),
                                                  (1, sectors - 1, backup_entries, 1)):
            header = bytearray(headers[index][1])
            struct.pack_into('<QQ', header, 24, lba, alternative)
            struct.pack_into('<QQ', header, 40, 2 + entry_sectors, last_usable)
            header[56:72] = disk_guid
            struct.pack_into('<Q', header, 72, table_lba)
            struct.pack_into('<I', header, 88, zlib.crc32(entries))
            struct.pack_into('<I', header, 16, 0)
            size = struct.unpack_from('<I', header, 12)[0]
            struct.pack_into('<I', header, 16, zlib.crc32(header[:size]))
            image.seek(table_lba * 512); image.write(entries)
            image.seek(lba * 512); image.write(header)
    parsed, partitions = base.read_gpt(path, fixed_layout=False)
    if partitions != [(BOOT_START * 512, 128 * 1024**2), (ROOT_START * 512, root_bytes)]:
        raise ValueError(f'Wrong Live partitions: {partitions}')
    for lba, header, _, _ in parsed:
        if struct.unpack_from('<Q', header, 24)[0] != lba:
            raise ValueError('GPT self-LBA mismatch')
    return partitions


def metadata_path(image):
    return image.with_suffix('').with_suffix('.json') if image.suffix == '.gz' else image.with_suffix('.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tf-image', type=Path, required=True, help='existing R5 TF .img.gz')
    parser.add_argument('--linux-image', type=Path, required=True, help='R5 eMMC .img.gz with adjacent JSON')
    parser.add_argument('--android-backup', type=Path, required=True, help='stock Android whole-user-area .img.gz')
    parser.add_argument('--openssl', default='openssl', help='OpenSSL executable supporting passwd -6')
    args = parser.parse_args()
    tf, linux, android = (p.expanduser().resolve() for p in
                          (args.tf_image, args.linux_image, args.android_backup))
    for path in (tf, linux, android):
        if not path.is_file() or not path.name.endswith('.img.gz'):
            parser.error(f'Expected regular .img.gz input: {path}')
    for tool in ('debugfs', 'e2fsck', 'tune2fs', 'resize2fs'):
        if shutil.which(tool) is None:
            parser.error(f'Missing build dependency: {tool}')
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'build.log').write_text('')
    linux_meta = json.loads(metadata_path(linux).read_text())
    tf_meta = json.loads(metadata_path(tf).read_text())
    if linux_meta['adaptation'] != 'R5' or linux_meta['storage_target'] != 'EMMC':
        raise ValueError('Linux payload must be an R5 eMMC image')
    if tf_meta['adaptation'] != 'R5' or tf_meta['storage_target'] != 'TF':
        raise ValueError('Live base must be an R5 TF image')
    print('Verify Linux and Android payloads', flush=True)
    linux_bytes, linux_hash = raw_metadata(linux)
    if linux_bytes != linux_meta['image_bytes'] or linux_hash != linux_meta['sha256']:
        raise ValueError('Linux payload differs from its release manifest')
    android_bytes, android_hash = raw_metadata(android)
    if android_bytes <= 0:
        raise ValueError('Empty Android payload')
    bundle = {'format': 1, 'device': 'PF818 / SW7990D Ver1.3', 'images': {
        'linux': {'file': 'images/linux-emmc.img.gz', 'bytes': linux_bytes,
                  'sha256': linux_hash, 'compressed_sha256': base.sha(linux)},
        'android': {'file': 'images/android-stock.img.gz', 'bytes': android_bytes,
                    'sha256': android_hash, 'compressed_sha256': base.sha(android)}}}
    bundle_path = base.textfile('manifest.json', json.dumps(bundle, indent=2) + '\n')
    print('Decompress existing R5 TF base', flush=True)
    source = BUILD / 'source.img'
    with gzip.open(tf, 'rb') as src, source.open('wb') as dst:
        shutil.copyfileobj(src, dst, 16 * 1024**2)
    source_hash = base.sha(source)
    if source_hash != tf_meta['sha256']:
        raise ValueError('TF base differs from its release manifest')
    headers, partitions = base.read_gpt(source)
    boot, root = BUILD / 'bootfs.img', BUILD / 'rootfs.img'
    with source.open('rb') as src:
        for destination, (offset, length) in zip((boot, root), partitions):
            with destination.open('wb') as dst:
                base.copy_region(src, dst, offset, length)
    retained_root = ('/usr/local/bin/pf818-scan', '/usr/local/bin/pf818-led',
                     '/usr/local/lib/pf818-nfc/libpf818-reader.so',
                     f'/lib/modules/{base.KERNEL}/extra/panel_pf818.ko')
    root_hashes = {p: base.sha(base.dump(root, p, BUILD / 'original-root' / Path(p).name))
                   for p in retained_root}
    retained_boot = tuple('/' + name for name in (f'vmlinuz-{base.KERNEL}',
                           f'initrd.img-{base.KERNEL}', f'uInitrd-{base.KERNEL}',
                           'dtb/rockchip/rk3399-pf818-r5.dtb'))
    boot_hashes = {p: base.sha(base.dump(boot, p, BUILD / 'original-boot' / Path(p).name))
                   for p in retained_boot}
    print('Grow Live root filesystem to 8 GiB', flush=True)
    with root.open('r+b') as dst:
        dst.truncate(ROOT_BYTES)
    base.run(['e2fsck', '-f', '-p', root], accepted=(0, 1))
    base.run(['resize2fs', '-f', root, '8192M'])
    root_uuid, boot_uuid = str(uuid.uuid4()), str(uuid.uuid4())
    for image, value, label in ((root, root_uuid, 'ROOT'), (boot, boot_uuid, 'BOOT')):
        base.run(['tune2fs', '-U', value, '-L', f'PF818_LIVE_{label}', image])
    for name in ('armbianEnv.txt', 'extlinux/extlinux.conf'):
        content = base.dump(boot, '/' + name, BUILD / name).read_text()
        content = content.replace(tf_meta['root_uuid'], root_uuid).replace('PF818-R5-TF', 'PF818-R5-LIVE')
        base.put(boot, base.textfile('boot-config', content), '/' + name)
    fstab = base.dump(root, '/etc/fstab', BUILD / 'fstab').read_text()
    fstab = fstab.replace(tf_meta['root_uuid'], root_uuid).replace(tf_meta['boot_uuid'], boot_uuid)
    base.put(root, base.textfile('fstab-new', fstab), '/etc/fstab')
    base.put(root, base.textfile('hostname', 'pf818-live\n'), '/etc/hostname')
    for path in ('/etc/hosts', '/etc/NetworkManager/system-connections/pf818-wired.nmconnection'):
        content = base.dump(root, path, BUILD / Path(path).name).read_text().replace('pf818-r1', 'pf818-live')
        base.put(root, base.textfile('network-new', content), path, 0o600 if path.endswith('.nmconnection') else 0o644)
    print('Configure direct root/1234 login and bilingual login help', flush=True)
    result = subprocess.run([args.openssl, 'passwd', '-6', '-stdin'], input='1234\n',
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    password_hash = result.stdout.strip()
    if result.returncode or not password_hash.startswith('$6$'):
        raise RuntimeError('Need OpenSSL with passwd -6; use --openssl to select it')
    shadow = base.dump(root, '/etc/shadow', BUILD / 'shadow-original').read_text()
    rows = []
    for row in shadow.splitlines():
        fields = row.split(':')
        if fields[0] == 'root':
            fields[1:8] = [password_hash, str(int(time.time() // 86400)), '0', '99999', '7', '', '']
        rows.append(':'.join(fields))
    base.put(root, base.textfile('shadow-live', '\n'.join(rows) + '\n'), '/etc/shadow', 0o600)
    base.put(root, base.textfile('machine-id', 'uninitialized\n'), '/etc/machine-id', 0o444)
    base.remove(root, '/root/.not_logged_in_yet')
    firstlogin = '/etc/profile.d/armbian-check-first-login.sh'
    if base.exists(root, firstlogin):
        base.put(root, base.textfile('first-login-disabled', '# PF818 Live uses root/1234; run passwd to change it.\n'), firstlogin)
    for kind in ('rsa', 'ecdsa', 'ed25519'):
        base.remove(root, f'/etc/ssh/ssh_host_{kind}_key')
        base.remove(root, f'/etc/ssh/ssh_host_{kind}_key.pub')
    stamp = datetime.now(ZoneInfo('Asia/Hong_Kong')).strftime('%Y-%m-%d_%H%M')
    release = (f'ADAPTATION=R5\nSTORAGE_TARGET=LIVE\nBUILD_TIME={stamp}\n'
               f'ROOT_UUID={root_uuid}\nBOOT_UUID={boot_uuid}\nFIRST_BOOT_RESIZE=false\n'
               'DEVICE_TREE=rockchip/rk3399-pf818-r5.dtb\nINSTALLER=pf818-install\n')
    base.put(root, base.textfile('pf818-release', release), '/etc/pf818-release')
    base.put(boot, base.textfile('PF818-R5-LIVE.txt', release + '16GB+ SD card; root/1234; run pf818-install.\n'), '/PF818-R5-LIVE.txt')
    payloads = [(CONFIG / 'pf818-install', '/usr/local/sbin/pf818-install', 0o755),
                (CONFIG / 'pf818-live.sh', '/etc/profile.d/pf818-live.sh', 0o644),
                (bundle_path, '/opt/pf818-installer/manifest.json', 0o644),
                (linux, '/opt/pf818-installer/images/linux-emmc.img.gz', 0o444),
                (android, '/opt/pf818-installer/images/android-stock.img.gz', 0o444)]
    checks = {}
    print('Embed both system packages and verify each readback', flush=True)
    for src, dst, mode in payloads:
        base.put(root, src, dst, mode)
        local = base.dump(root, dst, BUILD / 'readback' / Path(dst).name)
        checks[dst] = base.sha(local) == base.sha(src)
        local.unlink()
    ssh = base.dump(root, '/etc/ssh/sshd_config', BUILD / 'sshd_config').read_text()
    checks['root_ssh_password_login'] = 'PermitRootLogin yes' in ssh and 'PasswordAuthentication yes' in ssh
    checks['ssh_enabled'] = base.exists(root, '/etc/systemd/system/multi-user.target.wants/ssh.service')
    checks['ssh_keygen_enabled'] = base.exists(root, '/etc/systemd/system/ssh.service.wants/sshd-keygen.service')
    checks['first_boot_machine_id'] = base.dump(root, '/etc/machine-id', BUILD / 'readback-machine-id').read_text() == 'uninitialized\n'
    live_shadow = base.dump(root, '/etc/shadow', BUILD / 'shadow-readback').read_text()
    root_fields = next(row.split(':') for row in live_shadow.splitlines() if row.startswith('root:'))
    checks['root_1234_not_expired'] = root_fields[1] == password_hash and root_fields[2] != '0' and not root_fields[7]
    checks['no_account_setup_marker'] = not base.exists(root, '/root/.not_logged_in_yet')
    checks['fstab'] = base.dump(root, '/etc/fstab', BUILD / 'fstab-check').read_text() == fstab
    for image, originals in ((root, root_hashes), (boot, boot_hashes)):
        for path, expected in originals.items():
            local = base.dump(image, path, BUILD / 'retained' / Path(path).name)
            checks[path + '_retained'] = base.sha(local) == expected
    for image in (boot, root):
        base.run(['e2fsck', '-f', '-n', image])
    checks['filesystems_clean'] = True
    if not all(checks.values()):
        raise RuntimeError(json.dumps(checks, indent=2))
    print('Assemble Live image and relocate backup GPT', flush=True)
    output = REPO / 'output'
    output.mkdir(exist_ok=True)
    final = output / f'PF818_R5_LIVE_16GB_Armbian_trixie_6.18.57_{stamp}.img'
    compressed = final.with_suffix('.img.gz')
    if final.exists() or compressed.exists():
        raise FileExistsError(final)
    root_sectors = ROOT_BYTES // 512
    sectors = ((ROOT_START + root_sectors + 33 + 2047) // 2048) * 2048
    loader_hash = base.region_sha(source, 34 * 512, 16 * 1024**2 - 34 * 512)
    with final.open('wb') as dst, source.open('rb') as src:
        dst.truncate(sectors * 512)
        base.copy_region(src, dst, 0, 16 * 1024**2)
        for part, offset, size in ((boot, BOOT_START * 512, 128 * 1024**2),
                                   (root, ROOT_START * 512, ROOT_BYTES)):
            dst.seek(offset)
            with part.open('rb') as data:
                base.copy_region(data, dst, 0, size)
    write_live_gpt(final, headers)
    checks['gpt_and_partition_sizes'] = True
    checks['bootloader_retained'] = base.region_sha(final, 34 * 512, 16 * 1024**2 - 34 * 512) == loader_hash
    for part, offset, size in ((boot, BOOT_START * 512, 128 * 1024**2),
                               (root, ROOT_START * 512, ROOT_BYTES)):
        checks[part.name + '_in_image'] = base.region_sha(final, offset, size) == base.sha(part)
    if not all(checks.values()):
        raise RuntimeError(json.dumps(checks, indent=2))
    image_hash = base.sha(final)
    # Free duplicate large build files before compression, keeping existing small-card outputs.
    for path in (source, boot, root):
        path.unlink()
    print('Compress one complete Live image (no split files)', flush=True)
    with final.open('rb') as src, gzip.open(compressed, 'wb', compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, 16 * 1024**2)
    size, readback_hash = raw_metadata(compressed)
    if size != final.stat().st_size or readback_hash != image_hash:
        raise ValueError('Live compressed image readback failed')
    checks['compressed_readback'] = True
    manifest = {'adaptation': 'R5', 'storage_target': 'LIVE', 'minimum_card_gb': 16,
                'root_mib': 8192, 'build_time': stamp, 'source_tf': tf.name,
                'source_tf_sha256': source_hash, 'image': final.name,
                'image_bytes': size, 'sha256': image_hash,
                'compressed_image': compressed.name, 'compressed_bytes': compressed.stat().st_size,
                'compressed_sha256': base.sha(compressed), 'root_uuid': root_uuid,
                'boot_uuid': boot_uuid, 'login': 'root / 1234; no first-login setup',
                'installer': 'sudo pf818-install', 'bundled_images': bundle['images'],
                'verification': checks, 'live_boot_test': False, 'emmc_write_performed': False}
    final.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
    final.with_suffix('.img.sha256').write_text(f'{image_hash}  {final.name}\n')
    compressed.with_suffix('.gz.sha256').write_text(f'{manifest["compressed_sha256"]}  {compressed.name}\n')
    final.unlink()
    for name in ('shadow-original', 'shadow-live', 'shadow-readback'):
        (BUILD / name).unlink(missing_ok=True)
    print(compressed, flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
