# 恢复原厂安卓

## 只从 TF 运行 Linux

若没有把 Linux 写入机内 eMMC，关机、拔出 TF 卡、重新开机即可使用原来的安卓，无需恢复写入。

## 已把 Linux 写入 eMMC

从可启动的 PF818 Linux TF 卡进入系统，再将原厂安卓整盘备份写回 eMMC。备份文件放在 U 盘上或其他可访问的位置；不要放在将被覆盖的 eMMC 上。现有 TF 镜像的固定根分区也装不下这个备份文件。

本机保存的文件是：

```text
PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz
```

它是压缩的整盘原始备份。2026-10-24 的只读核对结果：

- gzip 完整性通过。
- 解压后大小为 **15,634,268,160 字节**，等于本机 eMMC 用户区容量。
- 备份中的 U-Boot、trust 内容与当前运行安卓的真机对应区域一致。
- 解压后完整镜像的 SHA-256 为：

```text
08bc74ae677abdfc928faaab123dee939b6704a0dbc40fe81283c4dda595bb0b
```

### 1. 从 TF 启动并确认目标

```sh
findmnt -no SOURCE /
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS,MODEL
for path in /sys/class/block/mmcblk*/device/type; do
    printf '%s: ' "$path"
    cat "$path"
done
```

确认 `/` 在 TF 卡上；TF 类型是 `SD`，eMMC 类型是 `MMC`。目标 eMMC 容量应为上述大小，其所有分区都应处于未挂载状态。若有分区被挂载，先逐一卸载这些分区；也检查 `swapon --show`，停用位于目标 eMMC 上的交换分区/文件。

后面的 `/dev/mmcblkX` 必须替换为当前 Linux 中实际识别的 eMMC 整盘。安卓当前把它称为 `mmcblk1`，这不代表 Linux 中编号也相同。

```sh
sudo blockdev --getsize64 /dev/mmcblkX
```

本机应返回 `15634268160`。下列步骤适用于原来的这块 eMMC；更换容量不同的存储后需重新评估布局。

### 2. 检查备份并完整写回

把 `/mnt/usb/` 换成备份实际所在目录。先检查压缩包完整性：

```sh
gzip -t /mnt/usb/PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz
```

成功退出后，在 **TF 启动的 Linux 的 Bash** 中执行：

```bash
set -o pipefail
gzip -dc /mnt/usb/PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz | \
  sudo dd of=/dev/mmcblkX bs=4M iflag=fullblock conv=fsync status=progress
```

这会覆盖 eMMC 中的 Linux，并恢复备份时的安卓系统和用户数据。必须写入整盘 `/dev/mmcblkX`，不能写进其中的 `p1` 或 `p2` 分区。保持供电，等待整个管道成功完成；写入总量应为 `15634268160` 字节。

`iflag=fullblock` 用于从管道完整收集输入块，`conv=fsync` 在结束前同步写入；参数含义见 [GNU dd 文档](https://www.gnu.org/software/coreutils/manual/html_node/dd-invocation.html)。

### 3. 读回校验并拔卡启动

写入成功后：

```sh
sync
sudo sha256sum /dev/mmcblkX
```

整盘哈希应与上面的 `08bc74ae...95bb0b` 完整 SHA-256 一致。确认匹配后：

```sh
sudo poweroff
```

断电后拔出 TF 卡，再开机进入安卓。写回后不再执行 Linux 的分区扩容、GPT 修复或格式化操作。

## boot0、boot1 两个文件

`emmc-boot0.img`、`emmc-boot1.img` 是额外的 eMMC 硬件启动区备份，各 4MiB。它们不是安卓的 `boot` 分区；安卓的 `boot` 已包含在整盘主备份中。Linux 内核将硬件启动区单独暴露为 `/dev/mmcblkXboot0` 和 `/dev/mmcblkXboot1`，参见 [内核文档](https://cdn.kernel.org/doc/html/latest/driver-api/mmc/mmc-dev-parts.html)。

本机的两个备份均为全零，并且与当前真机相应区域逐字节一致。本文的 R5 安装方法只写 `/dev/mmcblkX` 用户区，不改变这两个硬件启动区或 eMMC 启动配置，因此按本文路线回刷时无需写 boot0、boot1。请仍保留这两个备份文件。

## 如果 TF 也无法启动

此时需要走 Rockchip Loader / MaskROM USB 恢复路径。官方 [rkdeveloptool](https://github.com/rockchip-linux/rkdeveloptool) 提供 Loader 下载和按扇区写入功能，但本机进入恢复模式的方法及匹配的 DDR/USB Loader 尚未验证，不能把其他 RK3399 板子的短接位置或 Loader 当成 PF818 的已验证方案。

以上已经核对备份和设备布局，**尚未执行实际安卓回刷及启动验收**。这是一套基于本机完整备份的恢复步骤，不是已经完成过一次恢复测试的记录。
