# PF818 Linux 适配

PF818 收银终端的 Linux 外设适配源码，硬件采用 Rockchip RK3399 / SW799 核心板，**底板为 SW7990D Ver1.3**。R5 在已实机验证的 R4 配置上加入独立扫码器、红绿指示灯和摄像头白色补光支持。扫码器已在原厂安卓系统下用静态 ARM64 Linux 程序读出已知二维码，三路灯已逐路点亮并核对实际位置；R5 Armbian 整机启动及 eMMC 安装尚待验证。

基础系统来自 [ophub/amlogic-s9xxx-armbian](https://github.com/ophub/amlogic-s9xxx-armbian)：

| 项目 | 使用版本 |
| --- | --- |
| 原始镜像 | `Armbian_26.11.0_rockchip_sw799_trixie_6.18.57_server_2026.10.17.img` |
| 系统 | Armbian 26.11.0 / Debian trixie / ARM64 |
| 内核 | **6.18.57-ophub** |
| 上游设备树 | `rockchip/rk3399-bozz-sw799.dtb` |

内核镜像、initramfs、引导程序及现有模块直接复用 ophub 成品。适配主要修改底板设备树，另编译一个小型 `panel_pf818` 屏幕模块，加入横屏登录配置、NFC 工具和 EC20 查询工具。没有重编整个内核或重新打包系统 deb。

## 外设状态

| 外设 | 验证情况（扫码器和灯为 R5 新增，其余沿用 R4） |
| --- | --- |
| TF 启动 | 4GB TF 卡启动成功 |
| 有线网口、USB-A | USB `cdc_ether` 网卡 DHCP 与联网通过，USB-A 可用 |
| 内屏 | DSI0，1200×1920 / 60Hz；fbterm 提供顺时针 90° 横屏登录 |
| 触摸、六个按钮 | Goodix GT911，触摸、多点及六键事件通过 |
| Wi-Fi | BCM43430 / AP6212 系列，仅 2.4GHz；信道 6 联网通过，建议先使用信道 1–11 |
| 蓝牙 | UART0 控制器可用，双向文件传输通过；文件接收服务需自行配置 |
| 两路 USB 摄像头 | AM-VIS0831V 彩色、Sonix 灰度，均完成 1280×720 实拍 |
| NFC | SPI0 CS0，GPIO3_B2 拉低；ISO14443-A 寻卡、选卡及 UID 读取通过 |
| EC20F | GPIO1_A1 供电，`option` / `qmi_wwan` 可识别，QMI 查询及 SIM ICCID 读取通过；拨号联网待使用者验证 |
| GPU | Panfrost 硬件渲染通过 |
| 独立扫码器 | R5 新增：Exar XR22804 UART C（`04e2:1402`），115200 / 8N1；原厂安卓真机上的 Linux 可执行程序读取二维码通过，R5 Armbian 启动后仍需验收 |
| 红绿指示灯 | R5：GPIO1_A0 绿灯、GPIO2_D4 红灯；安卓真机点灯及位置确认通过，Linux 使用 `gpio-leds`，默认关闭 |
| 摄像头白色补光 | R5：GPIO0_A6，顶部主摄像头两侧白灯；安卓真机点灯确认通过，Linux 默认关闭、按需控制 |

内屏保留默认背光设置。实机观察到屏幕附近持续发热，关闭背光后等待约十分钟明显降温；尚未确认具体发热元件。横屏配置用于文本登录，图形桌面的旋转及触摸坐标映射需要另行配置。

## 源码与打包

- `adaptation/round1/`：TF、USB 供电、有线网络及启动日志。
- `adaptation/round2/`：屏幕模块、初始化序列、触摸、按键和横屏登录。
- `adaptation/round3/`：蓝牙与 modem 供电设备树。
- `adaptation/round4/`：最终 R4 设备树、NFC 绑定及用户态适配、QMI / AT 查询工具。
- `adaptation/round5/`：扫码器供电覆盖、udev 规则、原生读取命令、三路 LED 覆盖和控制工具及相关测试。
- `adaptation/emmc/`：eMMC 首次启动扩容脚本和服务。
- `adaptation/build_*.py`：离线镜像打包脚本，使用 `debugfs` 编辑文件系统。

完整准备步骤见 [BUILDING.md](BUILDING.md)。仓库仅保存适配源码与配置；上游镜像、内核、deb、模块成品和原厂 NFC 共享库需自行取得。

R5 可直接从已有 R4 TF / eMMC 镜像派生，不需要重走 R1–R4。使用方法见 [USAGE.md](USAGE.md)，烧录和升级见 [INSTALLING.md](INSTALLING.md)，变化见 [CHANGELOG.md](CHANGELOG.md)。

镜像解压后为 `.img`，约 **2577 MiB**，BOOT 128 MiB、ROOTFS 2432 MiB，可用 balenaEtcher 写入 4GB TF 卡，首次启动保持固定分区。eMMC 镜像从同一 R4 派生，仅在识别到根文件系统来自 eMMC 时扩容第二分区及 ext4。文件名带打包时间，精确到分钟，同时生成 SHA-256 和 JSON 清单。

本次重新打包采用 `--gzip-only --cleanup`：`output/` 只保留 TF/eMMC 两份 `.img.gz`、压缩包与原始镜像的 SHA-256、JSON 清单，不保留多份 2.5GiB 的未压缩镜像。压缩包解压读回哈希通过后才删除对应 `.img`；整轮构建成功后删除本轮生成的临时 `.img`，原厂安卓备份和输入 R4 包保留。

本次更新后的成品在 `output/`：

- TF 启动版：`PF818_R5_TF_Armbian_trixie_6.18.57_2026-10-24_2128.img.gz`。
- eMMC 安装版：`PF818_R5_EMMC_Armbian_trixie_6.18.57_2026-10-24_2128.img.gz`。

每份约 797MiB，旁边保留 `.img.gz.sha256`、`.img.sha256` 和 `.json`。其中 `.img.sha256` 用于解压后镜像或写入内容的校验，不代表目录中还保留了未压缩的 `.img`。

镜像继承基础系统登录账户 `root` / `1234`，有线 DHCP，首次使用应修改密码。Wi-Fi 由使用者配置。

R4 已在 TF 实机验证。此 R4 eMMC 派生镜像完成了离线启动文件复用、文件系统、GPT 及扩容模拟校验；该具体内核与配置组合尚未进行 eMMC 独立启动实测。写入 eMMC 会覆盖原系统，需要自行保存完整原厂备份并确认恢复入口。仓库脚本只生成本地镜像，不自动写设备。

## R5 的扫码器、指示灯与补光调用

扫码器由 `xr_serial` 提供固定节点 `/dev/pf818-scanner`，不依赖安卓框架或原厂扫码库：

```sh
# 等待最多 30 秒，读到一条扫码结果后退出。
pf818-scan --once --timeout 30

# 持续输出 JSON Lines，适合业务程序读取 stdout。
pf818-scan --json
```

普通用户可加入 `dialout` 组并重新登录后访问扫码器。NFC 原有调用仍为 `pf818-nfc-read`，详见 [USAGE.md](USAGE.md)。

三路灯已经在安卓真机上逐一执行三次亮灭，用户确认了下面的位置；均为高电平开、低电平关：

| 名称 | 实际位置 | RK3399 引脚（安卓旧编号） | Linux LED 节点 |
| --- | --- | --- | --- |
| `green` | 设备顶部左上角绿灯 | GPIO1_A0（32） | `/sys/class/leds/green:status` |
| `red` | 紧挨绿灯右边的红灯 | GPIO2_D4（92） | `/sys/class/leds/red:status` |
| `fill` | 顶部主摄像头两侧白色补光灯 | GPIO0_A6（6） | `/sys/class/leds/white:flash` |

**三路均默认关闭**，不设置开机常亮、心跳或网络触发。原厂脚本把 GPIO6 注释为“二维码灯”，但实际点亮的是主摄像头两侧白色补光，R5 按实际位置命名。扫码器内部的照明与这里的摄像头补光分开处理。

```sh
# 查看三路灯当前亮灭及触发器，输出 JSON；读取不需要 root。
pf818-led status

# 开关两颗指示灯。
sudo pf818-led green on
sudo pf818-led green off
sudo pf818-led red on
sudo pf818-led red off

# 红灯按亮 200ms、灭 800ms 闪烁；由内核 timer 执行。
sudo pf818-led red blink --on-ms 200 --off-ms 800
sudo pf818-led red off

# 拍照或人脸采集时按需开启白色补光，采集完成后关闭。
sudo pf818-led fill on
sudo pf818-led fill off
```

该 GPIO 硬件只提供开关，不提供连续调光；白色补光不提供闪烁子命令。控制工具会在切换到常亮/关闭时清除先前的闪烁触发器。灯光设置会保留到下一次操作或关机，应用负责在采集结束后关闭补光。写 LED 默认需要 root 权限，普通业务用户需另行配置对相应 sysfs 属性的写权限。

业务程序可调用 `pf818-led`，也可直接操作标准 LED 属性。以下 Python 示例应在具有 LED 写权限的进程中运行：

```python
from pathlib import Path

fill = Path("/sys/class/leds/white:flash")
(fill / "trigger").write_text("none\n")
try:
    (fill / "brightness").write_text("1\n")
    # 在这里调用摄像头，完成图像采集。
finally:
    (fill / "brightness").write_text("0\n")
```

LED 支持复用现有内核内建的 `CONFIG_LEDS_GPIO=y` 与 timer trigger，只合并设备树覆盖并加入小型 Python 控制工具，不新增常驻服务，也不重编内核。Linux 节点和开机关闭行为已做离线 DTB 校验，**仍需在 R5 Armbian 实际启动后验收**。

## 烧录与恢复：完整操作步骤

两种操作都从 **TF 卡上的 Linux** 中完成：

| 要做的事 | 从哪里启动 | 写入哪个文件 | 写到哪里 |
| --- | --- | --- | --- |
| 把 R5 Linux 安装到机内 | R5 TF 版 | `PF818_R5_EMMC_*.img.gz` | eMMC 整盘 |
| 将机内系统恢复为安卓 | Linux TF 卡 | `PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz` | eMMC 整盘 |

若始终只从 TF 卡运行 Linux，未写过 eMMC，**关机、拔卡、重新开机就能回到原来的安卓**，不需要执行恢复写入。

以下命令使用本次生成的 R5 文件名。使用其他构建版本时，替换对应的文件名及校验文件。**本文的实际写入目标由 TF 系统动态识别，不按安卓里的 `mmcblk1` 编号硬编码。**

### 一、准备 TF 卡和存放镜像的 U 盘

1. 准备至少 4GB TF 卡，用于启动 Linux；另准备至少 4GB、使用 FAT32 或 exFAT 文件系统的 U 盘，用于存放压缩镜像。如需用 Mac 磁盘工具更改 U 盘格式，先保存 U 盘现有数据。
2. 用 balenaEtcher 将 `PF818_R5_TF_Armbian_trixie_6.18.57_2026-10-24_2128.img` 写入 TF 卡，并等待验证完成。若只有 `.img.gz`，先解压得到 `.img`。
3. 将 U 盘卷标设为 `PF818`，下面统一从该卷标挂载。已有 U 盘可直接改卷标，无需为了这些步骤重新格式化。
4. 在 Mac 上把安装/恢复文件复制到 U 盘。以下代码在 **Mac 终端** 执行；如果 U 盘卷名或本地目录不同，只修改开头三个变量：

```bash
PF818_REPO="$HOME/GitHubRepo/PF818-Linux"
PF818_STOCK="$HOME/Downloads/pf818原包文件夹"
PF818_USB="/Volumes/PF818"

# 确认 U 盘已挂载，再创建存放镜像的目录。
test -d "$PF818_USB" || { echo "没有找到 U 盘：$PF818_USB"; exit 1; }
mkdir -p "$PF818_USB/pf818"

# R5 eMMC 安装包，以及压缩包/解压后镜像的校验文件。
cp "$PF818_REPO/output/PF818_R5_EMMC_Armbian_trixie_6.18.57_2026-10-24_2128.img.gz" \
   "$PF818_USB/pf818/"
cp "$PF818_REPO/output/PF818_R5_EMMC_Armbian_trixie_6.18.57_2026-10-24_2128.img.gz.sha256" \
   "$PF818_USB/pf818/"
cp "$PF818_REPO/output/PF818_R5_EMMC_Armbian_trixie_6.18.57_2026-10-24_2128.img.sha256" \
   "$PF818_USB/pf818/"

# 安卓整盘备份，以及额外保存的两个硬件启动区备份。
cp "$PF818_STOCK/PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz" \
   "$PF818_USB/pf818/"
cp "$PF818_STOCK/emmc-boot0.img" "$PF818_STOCK/emmc-boot1.img" \
   "$PF818_USB/pf818/"
sync
```

只进行其中一种操作时，可以只复制对应的镜像。压缩包无需预先解压到 U 盘，下面会边解压边写入。TF 镜像的根分区固定约 2.4GiB，剩余空间放不下这些安装包；若沿用“预先把镜像放进 TF 根分区”的方法，需要先在更大的 TF 卡上扩展分区。

### 二、公共准备：从 TF 启动，识别 eMMC 并挂载 U 盘

#### 1. 从 TF 启动，进入 root Bash

PF818 关机，插入已写好的 TF 卡及 U 盘，再开机进入 Armbian。以下命令全部在 **PF818 的 TF Linux 终端或它的 SSH 会话中** 执行，不是在 Mac 本机执行。

基础账户为 `root`，初始密码 `1234`。普通用户先执行：

```sh
sudo bash
```

已经是 root 时执行 `bash` 即可。随后设置：

```bash
# 后续命令失败时停止当前 Bash；解压管道中的错误也会被报告。
set -e
set -o pipefail

findmnt -no SOURCE /
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS,MODEL
```

#### 2. 确认当前根系统在 TF，并自动识别唯一的 eMMC

复制执行下面整个代码块：

```bash
ROOT_PART="$(readlink -f "$(findmnt -n -o SOURCE /)")"
ROOT_DISK="$(lsblk -n -d -o PKNAME "$ROOT_PART")"

if [ -z "$ROOT_DISK" ] || \
   [ "$(cat "/sys/class/block/$ROOT_DISK/device/type")" != "SD" ]; then
    echo "当前根系统没有确认位于 TF 卡上，停止操作。"
    exit 1
fi

mapfile -t EMMC_NAMES < <(
    for type_file in /sys/class/block/mmcblk*/device/type; do
        [ -f "$type_file" ] || continue
        disk_name="$(basename "$(dirname "$(dirname "$type_file")")")"
        [[ "$disk_name" =~ ^mmcblk[0-9]+$ ]] || continue
        if [ "$(cat "$type_file")" = "MMC" ]; then
            printf '%s\n' "$disk_name"
        fi
    done
)

if [ "${#EMMC_NAMES[@]}" -ne 1 ]; then
    echo "未找到唯一的 eMMC，停止操作。"
    exit 1
fi

EMMC_DEV="/dev/${EMMC_NAMES[0]}"
EMMC_BYTES="$(blockdev --getsize64 "$EMMC_DEV")"
printf '当前 TF 根分区：%s\n目标 eMMC：%s\n目标容量：%s 字节\n' \
    "$ROOT_PART" "$EMMC_DEV" "$EMMC_BYTES"
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS "$EMMC_DEV"
```

本机 eMMC 容量为 **15,634,268,160 字节**。核对输出，确认根系统所在 TF 与目标 eMMC 是不同设备。后续代码使用上面设置的 `EMMC_DEV`；若换了终端或重新登录，需重新执行公共准备。

#### 3. 卸载 eMMC 上正在使用的分区

先检查是否有交换分区或交换文件位于 eMMC 上：

```bash
swapon --show
```

若有，先用 `swapoff` 关闭该条目。例如输出中的路径为 `/dev/mmcblk1p3`，则执行 `swapoff /dev/mmcblk1p3`；若为交换文件，则执行 `swapoff /实际路径/交换文件`。TF 上的交换和 `/dev/zram*` 无需关闭。

下面只卸载目标 eMMC 上已挂载的设备，若卸载失败会停止：

```bash
while IFS= read -r part; do
    if findmnt -r -n -S "$part" >/dev/null; then
        umount --all-targets "$part"
    fi
done < <(lsblk -r -n -p -o NAME "$EMMC_DEV" | tac)

# 再检查一次，目标 eMMC 各项的 MOUNTPOINTS 应为空。
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS "$EMMC_DEV"
```

#### 4. 挂载存放镜像的 U 盘

```bash
USB_PART="$(readlink -f /dev/disk/by-label/PF818)"
test -b "$USB_PART" || { echo "未找到卷标为 PF818 的 U 盘"; exit 1; }

# 如果已经自动挂载，复用其挂载点；否则以只读方式挂载。
USB_MOUNT="$(findmnt -n -o TARGET -S "$USB_PART" || true)"
if [ -z "$USB_MOUNT" ]; then
    mkdir -p /mnt/pf818-usb
    mount -o ro "$USB_PART" /mnt/pf818-usb
    USB_MOUNT=/mnt/pf818-usb
fi

IMAGE_DIR="$USB_MOUNT/pf818"
test -d "$IMAGE_DIR"
ls -lh "$IMAGE_DIR"
```

下面选择“三、安装 R5”或“四、恢复安卓”其中一套执行，不要连续执行两套。

### 三、进入 TF 后，将 R5 Linux 刷入 eMMC

完成上面的公共准备后，在同一个 root Bash 中执行。

#### 1. 检查 R5 安装包

```bash
LINUX_IMAGE="PF818_R5_EMMC_Armbian_trixie_6.18.57_2026-10-24_2128.img.gz"
LINUX_RAW_SUM="PF818_R5_EMMC_Armbian_trixie_6.18.57_2026-10-24_2128.img.sha256"
LINUX_BYTES=2702180352

test "$EMMC_BYTES" -ge "$LINUX_BYTES"
cd "$IMAGE_DIR"
sha256sum -c "$LINUX_IMAGE.sha256"
gzip -t "$LINUX_IMAGE"
test -f "$LINUX_RAW_SUM"
```

应看到校验结果 `OK`。使用的是 **EMMC 版**，TF 版继续留在卡上作为启动与恢复环境。

#### 2. 写入 eMMC 整盘

**此步骤会覆盖机内原来的安卓或 Linux。** 确认目标为上面识别的 eMMC，并保持供电：

```bash
printf '即将把 R5 写入：%s\n' "$EMMC_DEV"
gzip -dc "$IMAGE_DIR/$LINUX_IMAGE" | \
    dd of="$EMMC_DEV" bs=4M iflag=fullblock conv=fsync status=progress
sync
```

等待整个命令成功退出。本次镜像应写入 `2702180352` 字节，约 2.5GiB。`EMMC_DEV` 指整盘，不是末尾带 `p1`、`p2` 的分区。

#### 3. 校验写入内容

R5 镜像比 eMMC 容量小，所以只校验刚写入的镜像长度：

```bash
EXPECTED_LINUX_SHA="$(awk 'NR == 1 {print $1}' "$IMAGE_DIR/$LINUX_RAW_SUM")"
ACTUAL_LINUX_SHA="$(head -c "$LINUX_BYTES" "$EMMC_DEV" | sha256sum | awk '{print $1}')"
printf '镜像校验值：%s\n写入校验值：%s\n' "$EXPECTED_LINUX_SHA" "$ACTUAL_LINUX_SHA"
test "$ACTUAL_LINUX_SHA" = "$EXPECTED_LINUX_SHA"
echo "R5 写入校验通过。"
```

#### 4. 关机、拔 TF，再从 eMMC 启动

```bash
sync
poweroff
```

设备关机后拔出 TF 卡及 U 盘，再开机。首次从 eMMC 启动后检查：

```sh
cat /etc/pf818-release
findmnt -no SOURCE /
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS
systemctl status pf818-emmc-grow.service --no-pager
cat /var/lib/pf818/emmc-expanded
df -h /
pf818-scan --once --timeout 30
```

`STORAGE_TARGET` 应为 `EMMC`，根分区应来自 eMMC；扩容成功后会生成 `/var/lib/pf818/emmc-expanded`。最后一条命令等待扫码 30 秒，读取到一条结果后退出。完整接口见 [USAGE.md](USAGE.md)。

### 四、进入 TF 后，将 eMMC 刷回原来的安卓

此处适用于 **Linux 已经写入 eMMC** 的情况。设备关机，重新插入 Linux TF 卡及存有备份的 U 盘，开机；先完整执行“二、公共准备”。不要从当前 eMMC 内的系统覆盖它自己。

#### 1. 检查原厂备份和目标容量

本机备份已做过只读核对：gzip 完整性通过，解压后大小与整块 eMMC 一致，U-Boot/trust 与当前安卓对应区域一致。备份文件和已知解压后哈希如下：

```bash
ANDROID_IMAGE="PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz"
ANDROID_BYTES=15634268160
EXPECTED_ANDROID_SHA="08bc74ae677abdfc928faaab123dee939b6704a0dbc40fe81283c4dda595bb0b"

if [ "$EMMC_BYTES" -ne "$ANDROID_BYTES" ]; then
    echo "目标容量与本机整盘备份不一致，停止恢复。"
    exit 1
fi

gzip -t "$IMAGE_DIR/$ANDROID_IMAGE"
BACKUP_ANDROID_SHA="$(gzip -dc "$IMAGE_DIR/$ANDROID_IMAGE" | sha256sum | awk '{print $1}')"
printf '已知备份哈希：%s\n当前文件哈希：%s\n' "$EXPECTED_ANDROID_SHA" "$BACKUP_ANDROID_SHA"
test "$BACKUP_ANDROID_SHA" = "$EXPECTED_ANDROID_SHA"
echo "安卓备份校验通过。"
```

此哈希只对应上述这份本机备份。若另行制作了更新的备份，应使用那份备份自己的大小和哈希，不能套用这里的值。

#### 2. 将安卓整盘备份完整写回 eMMC

**此步骤会覆盖 eMMC 中的 Linux 和后续数据，并恢复到备份时的安卓内容。**

```bash
printf '即将将安卓整盘备份写回：%s\n' "$EMMC_DEV"
gzip -dc "$IMAGE_DIR/$ANDROID_IMAGE" | \
    dd of="$EMMC_DEV" bs=4M iflag=fullblock conv=fsync status=progress
sync
```

等待整个命令成功退出，写入量应为 **`15634268160` 字节**。由于是完整写回同一容量的 eMMC，原有 Linux 分区信息也会被覆盖。

#### 3. 校验整块 eMMC

```bash
ACTUAL_ANDROID_SHA="$(sha256sum "$EMMC_DEV" | awk '{print $1}')"
printf '备份校验值：%s\neMMC 校验值：%s\n' "$EXPECTED_ANDROID_SHA" "$ACTUAL_ANDROID_SHA"
test "$ACTUAL_ANDROID_SHA" = "$EXPECTED_ANDROID_SHA"
echo "安卓恢复写入校验通过。"
```

哈希一致后关机：

```bash
sync
poweroff
```

关机后拔出 TF 卡及 U 盘，再开机进入安卓。写回后不再运行 Linux 的分区扩容、GPT 修复或格式化命令。

#### 4. boot0、boot1 是否需要刷回

本机 `emmc-boot0.img`、`emmc-boot1.img` 各 4MiB，均为全零，已与当前真机对应区域逐字节核对一致。本文的 R5 安装只写 eMMC 用户区，未修改这两个硬件启动区或 eMMC 启动配置，**因此按这套安装方法刷过 R5 后，恢复安卓时无需写 boot0、boot1**。继续保存这两个备份文件即可。安卓名为 `boot` 的系统分区已经包含在主备份中，不是这两个硬件启动区。

### 五、当前验证范围与恢复入口

截至本次交付，已完成扫码器的安卓真机接口验证、三路灯的安卓真机点亮及位置确认、R5 镜像离线检查，以及安卓备份完整性/容量/关键引导区域核对。**R5 TF 冷启动、灯控与扫码的 Armbian 启动后验证、eMMC 安装/独立启动、实际安卓回刷启动尚未执行验收。** 本文提供操作步骤，不代表已经在本机完成过一次刷入及刷回测试。

如果 TF 卡也无法启动，需要转用 Rockchip Loader / MaskROM USB 恢复。PF818 的具体恢复入口及匹配的 DDR/USB Loader 目前尚未验证；该路径不在上面的 TF 恢复命令中。相关文件说明见 [RESTORING_ANDROID.md](RESTORING_ANDROID.md)，驱动和工具来源见 [NOTICE.md](NOTICE.md)。

## 上游与来源

感谢 [ophub](https://github.com/ophub) 提供 SW799 的 Armbian 镜像与 [内核成品](https://github.com/ophub/kernel)。设备树以其 SW799 设备树为基础，结合原厂 Android 运行时设备树核对底板连接。屏幕初始化序列来自原厂运行时面板节点；NFC 用户态适配需使用本机原厂应用中的读卡库。来源与许可范围见 [NOTICE.md](NOTICE.md)。
