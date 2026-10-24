# TF 启动与 eMMC 安装

R5 沿用 R4 的烧录路线：**Etcher 写 TF → 从 TF 启动 Armbian → 将 eMMC 镜像写入机内 eMMC**。本仓库的构建脚本不会自动烧录设备。

需要回到安卓时，见 [RESTORING_ANDROID.md](RESTORING_ANDROID.md)。只从 TF 运行 Linux 时，关机拔卡即可；覆盖过 eMMC 时，从 TF 启动后写回安卓整盘备份。

## 1. 选择镜像并写 TF

- `PF818_R5_TF_*.img`：固定分区的 TF 启动版，至少 4GB TF 卡。
- `PF818_R5_EMMC_*.img`：机内 eMMC 安装版，在从 eMMC 启动后自动扩展根分区。
- 同名 `.img.gz` 是压缩分发包，可先解压成 `.img` 再交给 balenaEtcher。

在 Mac 上先核对下载文件旁的 SHA-256，例如在镜像所在目录：

```sh
shasum -a 256 -c PF818_R5_TF_Armbian_trixie_6.18.57_TIMESTAMP.img.gz.sha256
```

解压 TF 镜像，用 balenaEtcher 选择该 `.img` 和 TF 卡，完成写入及验证。设备关机后插入 TF，再开机，从 TF 中的 Armbian 启动。现有基础账户仍是 `root` / `1234`，登录后修改密码；有线网络沿用 DHCP。

只想在 TF 中使用 Linux，到这里即可，不需要写 eMMC。先运行：

```sh
cat /etc/pf818-release
findmnt -no SOURCE /
ls -l /dev/pf818-scanner
pf818-scan --once --timeout 30
```

将测试二维码对准扫码窗口，检查返回内容。完整开发接口见 [USAGE.md](USAGE.md)。

## 2. 准备写入 eMMC 的镜像

原 R4 Release 中“预先把 img 放进 TF 系统，再在设备上写 eMMC”的做法可以继续使用。若仍使用 `chroot` 完成准备，也可以沿用。需要放入的是 **R5 EMMC** 文件。

容量要按实际文件留足：TF 镜像的根分区仍固定约 2.4GiB，本次构建后可用空间约 340MiB，装不下完整 `.img`，也装不下约 797MiB 的压缩包。若要把安装镜像存进 TF 根分区，请使用更大的 TF 卡并先在 Linux 中扩展其第二分区和 ext4。此时建议至少 8GB TF 卡。

另一种准备方式是把 `PF818_R5_EMMC_*.img.gz` 和对应的 `.sha256` 放在 U 盘上。从 TF 启动后挂载 U 盘，在其目录中执行：

```sh
sha256sum -c PF818_R5_EMMC_Armbian_trixie_6.18.57_TIMESTAMP.img.gz.sha256
```

也可通过有线网络传送镜像。这些只改变镜像的存放位置，后面的写入路线与 R4 相同。

## 3. 在 TF 系统中确认 eMMC

以下是使用者在 PF818 Linux 上执行的安装步骤。写入 eMMC 会覆盖原安卓系统；保留原厂完整备份和已知恢复入口。

```sh
findmnt -no SOURCE /
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS,MODEL
for path in /sys/class/block/mmcblk*/device/type; do
    printf '%s: ' "$path"
    cat "$path"
done
```

TF 的 `device/type` 是 `SD`，eMMC 是 `MMC`。确认 `/` 所在分区属于 TF，目标 eMMC 的分区均未挂载。若目标有已挂载分区，先逐一卸载这些分区。**不要假定 `/dev/mmcblk0` 就是 eMMC**，下面的 `mmcblkX` 必须替换成刚确认的目标。

## 4. 写入 eMMC 并从机内启动

若已经把未压缩镜像放在可访问位置：

```sh
sudo dd if=/path/to/PF818_R5_EMMC_Armbian_trixie_6.18.57_TIMESTAMP.img \
  of=/dev/mmcblkX bs=4M conv=fsync status=progress
sync
sudo poweroff
```

若使用 U 盘中的压缩包，可以边解压边写入，不占用 TF 根分区空间：

```bash
set -o pipefail
gzip -dc /path/to/PF818_R5_EMMC_Armbian_trixie_6.18.57_TIMESTAMP.img.gz | \
  sudo dd of=/dev/mmcblkX bs=4M conv=fsync status=progress
```

只有在整个管道成功退出后，再执行 `sync`、关机。拔出 TF 后开机，设备从 eMMC 启动。TF 与 eMMC 两个 R5 镜像使用不同的 UUID，安装时仍推荐关机拔卡后再验证机内启动。

首次 eMMC 启动后检查：

```sh
findmnt -no SOURCE /
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS
systemctl status pf818-emmc-grow.service
cat /var/lib/pf818/emmc-expanded
df -h /
pf818-scan --once --timeout 30
```

eMMC 版保留 R4 的扩容机制：只在根设备类型为 `MMC` 时迁移 GPT 备用表、扩展第二分区及 ext4。TF 版禁用该服务，首次启动不自动扩容。

截至本次交付，已完成原厂安卓真机上的扫码接口验证、Linux 静态读取程序验证及 R5 镜像离线检查；**尚未从 TF 冷启动 R5，也未执行 R5 eMMC 写入或独立启动验证**。原厂 Android 下直接覆盖正在运行的内部存储不属于本文安装流程。
