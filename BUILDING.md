# 构建准备

打包脚本源自 R1 → R4 的逐轮构建流程。它们不会下载依赖或重编上游内核。Linux 主机需要 Python 3.11+、`dtc`（device-tree-compiler）、e2fsprogs、util-linux 及 `dpkg-deb`。公开脚本改为直接调用主机 `dtc`，不再依赖从 ARM 镜像提取的编译器。

所有命令在仓库根目录运行。`build/` 为中间文件，`output/` 为本地成品，两者均由 Git 忽略。

## 1. 基础镜像与 R1

从 ophub 的仓库或发布存档取得 README 指定的原始 SW799 镜像，解压后放在仓库根目录；也可指定绝对路径：

```sh
export PF818_BASE_IMAGE=/absolute/path/Armbian_26.11.0_rockchip_sw799_trixie_6.18.57_server_2026.10.17.img
python3 adaptation/build_round1.py
```

脚本输出文件名含时间。后续通过环境变量明确指定上一步产物，不需要改文件名。

## 2. 屏幕模块与 R2 输入

`panel_pf818` 必须针对 **6.18.57-ophub** 的配置和头文件编译，可在运行该内核的 ARM64 设备上进行：

```sh
make -C /lib/modules/$(uname -r)/build M="$PWD/adaptation/round2/panel" modules
```

在用于准备模块和软件包的 ARM64 构建环境中，将模块安装到 `/lib/modules/6.18.57-ophub/extra/panel_pf818.ko`，执行 `depmod -a 6.18.57-ophub`。从 Debian trixie 取得并安装 `fbterm 1.7-5+b1 arm64`，保留原始 deb。将以下文件复制到主机构建目录：

```text
build/round2/
  panel_pf818.ko
  fbterm_1.7-5+b1_arm64.deb
  fbterm.status
  runtime-files/lib/modules/6.18.57-ophub/extra/panel_pf818.ko
  runtime-files/lib/modules/6.18.57-ophub/modules.*
  runtime-files/var/lib/dpkg/info/fbterm.list
  runtime-files/var/lib/dpkg/info/fbterm.md5sums
```

`modules.*` 使用安装模块后生成的索引文件，不复制上游其他 `.ko`。`fbterm.status` 可在上述环境中通过 `dpkg-query -s fbterm` 导出；dpkg 的 `.list` / `.md5sums` 从 `/var/lib/dpkg/info/` 取得。

```sh
export PF818_R1_IMAGE=/absolute/path/output/PF818_R1_Armbian_trixie_6.18.57_TIMESTAMP.img
python3 adaptation/build_round2.py
```

## 3. BlueZ 与 R3

本次使用的是 Armbian 软件源的 **bluez 5.82-1.1+rpt2 arm64**，来源为 `http://apt.armbian.com` 的 trixie/trixie-utils。它是上游预编译包。准备：

```text
build/round3/
  bluez_5.82-1.1+rpt2_arm64.deb
  pf818-r3-bluez.status
  var/lib/dpkg/info/bluez.*
```

在准备软件包的 ARM64 环境中安装该版本后，以 `dpkg-query -s bluez` 导出状态条目到 `pf818-r3-bluez.status`，复制 `/var/lib/dpkg/info/bluez.*`。包的依赖已由指定基础镜像提供；更换基础系统或包版本需要重新核对。R3 脚本沿用原构建中的 bluetooth GID 109。

```sh
export PF818_R2_IMAGE=/absolute/path/output/PF818_R2_Armbian_trixie_6.18.57_TIMESTAMP.img
python3 adaptation/build_round3.py
```

## 4. NFC 原厂库与 R4

从自己的原厂 Android 应用 APK 中提取 `lib/arm64-v8a/libicreader-lib.so`，放到：

```text
build/round4/runtime-apk/lib/arm64-v8a/libicreader-lib.so
```

适配的是本机实际使用的 `com.zhhq.android.commuter_car.face.megvii2` 应用中的库，不保证其他来源或其他版本兼容。该原厂库未随仓库分发。

```sh
mkdir -p build/round4/linux-reader
python3 adaptation/round4/reader/prepare-library.py
```

`prepare-library.py` 对这份库的副本调整 ELF 依赖与符号版本。再用 ARM64 Linux 编译器生成小型辅助库：

```sh
aarch64-linux-gnu-gcc -shared -fPIC -O2 \
  -o build/round4/linux-reader/liblog.so \
  adaptation/round4/reader/bionic-adapter.c
```

在 ARM64 Linux 本机编译时可用 `gcc` 替换交叉编译器。随后打包：

```sh
export PF818_R3_IMAGE=/absolute/path/output/PF818_R3_Armbian_trixie_6.18.57_TIMESTAMP.img
python3 adaptation/build_round4.py
```

R4 自动绑定 `/dev/spidev0.0`，启动后可用以下命令进行读卡和 modem 状态查询：

```sh
pf818-nfc-read
pf818-modem-status
pf818-qmi-status
```

NFC 工具只完成寻卡、选卡与 UID 读取；结束时关闭射频场。QMI 工具查询服务版本，不建立数据连接。要使用标准 QMI 工具，可自行安装发行版 `libqmi-utils`。

## 5. R5：从现有 R4 镜像加入扫码器与三路灯

这是已有 R4 成品时的直接构建入口。接受 R4 TF 或 eMMC 的 `.img` / `.img.gz`，无需 R4 的 JSON 清单，也无需重新准备屏幕、BlueZ 和 NFC 库；这些文件从输入镜像保留。构建依赖为 Python 3.11+、`debugfs` / `e2fsck` / `tune2fs`（e2fsprogs）、`dtc` / `fdtoverlay` / `fdtget`（device-tree-compiler）。可在具备这些工具的 Linux 或 macOS 主机运行。

先在 ARM64 Linux 上编译扫码命令：

```sh
make -C adaptation/round5
```

也可以在其他主机使用 ARM64 Linux 交叉编译器：

```sh
make -C adaptation/round5 CC=aarch64-linux-gnu-gcc
```

macOS 可使用 Zig 0.13.0 交叉编译静态 ELF，本次成品采用此方法：

```sh
mkdir -p build/round5
zig cc -target aarch64-linux-musl -static -O2 -s \
  -Wall -Wextra -Werror -std=c11 \
  adaptation/round5/pf818-scan.c -o build/round5/pf818-scan
```

随后构建两个存储版本：

```sh
python3 adaptation/build_round5.py \
  --source /absolute/path/PF818_R4_EMMC_Armbian_trixie_6.18.57_TIMESTAMP.img.gz \
  --target both --gzip-only --cleanup
```

`--target tf` / `--target emmc` 可只构建一种。`--binary` 可指定编译好的 ARM64 命令；也可用 `PF818_R4_IMAGE` 提供输入路径。输出在 `output/`。推荐上述节省空间的参数：每个版本只保留 `.img.gz`、压缩包及解压后镜像的 SHA-256、JSON 清单；压缩读回验证后删除成品 `.img`，整轮成功后清理临时镜像。原厂备份和外部输入 R4 包不删除。需要保留 `.img` 时，使用 `--gzip` 替代 `--gzip-only`。推荐为构建过程预留至少约 15GB 临时空间；两份压缩成品合计约 1.6GiB。

脚本验证输入 GPT、固定 R4 分区布局、R4 标识、内核的 `xr_serial` 模块/USB ID 及内建 LED/timer 支持。它将 GPIO1_C7 扫码器供电覆盖和三路灯覆盖合并到 R4 DTB，生成 `rk3399-pf818-r5.dtb`，不依赖 R1 提取的 DTS。灯覆盖使用输入 DTB 保留的 `gpio0` / `gpio1` / `gpio2` 符号，逐项校验 GPIO 控制器、偏移、有效电平、节点名及默认关闭状态。保留内核、initramfs、屏幕模块、NFC 库和其他原有系统文件；每个输出生成独立的文件系统 UUID、GPT 磁盘及分区 GUID。TF 版本关闭 eMMC 扩容服务；eMMC 版本更新并启用原有扩容服务。构建只处理普通文件，禁止把块设备用作输入，不烧录任何物理设备。

验证包括：文件系统检查、主备 GPT CRC、启动配置及 fstab、载荷逐文件读回、内核/initramfs/屏幕/NFC 保留检查、引导程序区域和分区写回哈希。它们不等同于 PF818 上的 R5 冷启动或 eMMC 独立启动实测。

在构建主机上测试读取程序的串口逻辑：

```sh
make -C adaptation/round5 OUT=../../build/round5/pf818-scan-host
python3 adaptation/round5/test_reader.py build/round5/pf818-scan-host
python3 adaptation/round5/test_lights.py
```

注意：本机编译的测试程序与 ARM64 镜像载荷使用不同输出文件名。

## 6. 旧版 R4 eMMC 派生镜像

R4 `.img` 和旁边的 `.json` 清单都需保留。

```sh
export PF818_R4_IMAGE=/absolute/path/output/PF818_R4_Armbian_trixie_6.18.57_TIMESTAMP.img
python3 adaptation/build_emmc.py
```

默认生成 eMMC 镜像：重新生成文件系统 UUID，同步启动配置及 fstab，启用 `pf818-emmc-grow.service`。扩容服务按根设备的 MMC 类型识别 eMMC，依次迁移 GPT 备用表、延长第二分区、更新内核分区视图及在线扩展 ext4。成功标记为 `/var/lib/pf818/emmc-expanded`，TF 启动时跳过。

也可执行 `python3 adaptation/build_emmc.py --target tf` 生成具有独立 UUID 的固定分区 TF 镜像。打包全程不挂载文件系统，不写入物理磁盘。每轮会执行文件系统检查，并校验分区、启动区域及内核/initramfs 的复用结果。
