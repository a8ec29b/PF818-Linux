# PF818 Linux 适配

PF818 收银终端的 Linux 外设适配源码，硬件采用 Rockchip RK3399 / SW799 核心板，**底板为 SW7990D Ver1.3**。R5 在已实机验证的 R4 配置上加入独立扫码器、红绿指示灯和摄像头白色补光支持。扫码器已在原厂安卓系统下用静态 ARM64 Linux 程序读出已知二维码，三路灯已逐路点亮并核对实际位置；大卡 Live 版已从 32GB TF 卡启动并通过有线 SSH 登录，Linux 下的扫码、灯控及 eMMC 安装/恢复仍待验收。

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
| TF 启动 | R4 在 4GB TF 卡启动成功；R5 大卡 Live 在 32GB TF 卡启动并通过 SSH 登录 |
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

## 下载镜像与获取源码

**Git 源码仓库不包含大镜像文件。标准小卡版通过 Releases 附件分发，适合 4GB / 8GB TF 卡；另有大卡完整版，见下方单独说明。** 安装已发布的系统无需克隆仓库，也不需要自行构建。

Releases 中的标准版文件如下：

| 附件 | 用途 |
| --- | --- |
| `PF818_R5_TF_*.img.gz` | 写入 TF 卡，用来启动 Linux 和安装/恢复机内系统 |
| `PF818_R5_EMMC_*.img.gz` | 在 TF 启动的 Linux 中写入 eMMC |
| 与镜像同名的 `.img.gz.sha256` | 校验下载的压缩包 |
| 与镜像同名的 `.img.sha256` | 校验解压后的镜像或写入内容 |
| 与镜像同名前缀的 `.json` | 查看来源、大小、UUID 和构建验证结果 |

星号代表实际版本、内核和时间戳。小卡版手动安装 eMMC 时，请同时下载其 `.img.gz`、`.img.gz.sha256` 和 `.img.sha256`，放在同一目录，并通过 U 盘或网络将系统包提供给 PF818。每个目录只放同一个版本的一套附件。GitHub 自动生成的 **Source code** 压缩包是源码，不是可烧录镜像。

标准小卡镜像解压后约 **2577 MiB**，BOOT 128 MiB、ROOTFS 2432 MiB，可写入至少 4GB 的 TF 卡。TF 版首次启动保持固定分区；eMMC 安装版首次从 eMMC 启动时扩容。实际大小和校验值以下载文件的清单为准。

镜像继承基础系统登录账户 `root` / `1234`，有线 DHCP，首次使用应修改密码。Wi-Fi 由使用者配置。

### 另：大卡完整版（16GB 及以上）

另有一个更完整的大卡 Live 版本，推荐给使用 **16GB 或更大 TF 卡（包括 32GB）** 的用户。卡内已经放好 **R5 Linux 安装包和样机 Android 7.1.2 恢复包**，可以直接在设备上选择安装 Linux 或恢复安卓，无需另备 U 盘，也不用再单独下载、搬运这两个系统包。原有小卡版继续保留。

**[大卡完整版下载文件夹（OneDrive，镜像约 2.7GiB）](https://1drv.ms/f/c/186e2631aeb25aa5/IgC3XRdvnzqtTa9NNZnPOoe0ATY4-Ukp5VOf0kAp7Uel23Y?e=9RNoSk)**。请选择文件名带 **`2026-10-26_0233`** 的修复版，已修复安装器第 4 步报错的问题。此包单独通过 OneDrive 分发，不放在 GitHub Releases 中；镜像是一个完整 `.img.gz`，不分片。

简单使用方法：

1. 下载并解压得到 `.img`，用 balenaEtcher 写入 **16GB 及以上 TF 卡**。
2. PF818 关机，插入 TF 卡，连接路由器网线后开机。从终端登录，或在同一局域网通过 `ssh root@设备实际IP` 连接，账号 **`root`**、密码 **`1234`**。无需创建账号或完成 Armbian 首次初始化，可登录后用 `passwd` 自行改密。
3. 运行 **`pf818-install`**，先选择 **简体中文 / English**，再选择 **安装 Linux** 或 **恢复安卓**，按提示核对目标并确认写入。此操作会覆盖机内 eMMC 的系统和数据。
4. 等待写入及校验完成，关机、拔出 TF 卡，再开机即可进入刚安装的机内系统。

镜像解压后约 **8.14GiB**，电脑需留出约 **9GiB** 解压空间；卡内 ROOTFS 为 **8GiB**，已足够容纳两个内置包，32GB 卡的剩余空间不会自动全部分配。详细流程见下文「大卡 Live 安装与恢复」。

### 自行构建

需要修改适配或重新打包时，再获取本仓库源码并阅读 [BUILDING.md](BUILDING.md)。源码目录如下：

- `adaptation/round1/`：TF、USB 供电、有线网络及启动日志。
- `adaptation/round2/`：屏幕模块、初始化序列、触摸、按键和横屏登录。
- `adaptation/round3/`：蓝牙与 modem 供电设备树。
- `adaptation/round4/`：最终 R4 设备树、NFC 绑定及用户态适配、QMI / AT 查询工具。
- `adaptation/round5/`：扫码器供电覆盖、udev 规则、原生读取命令、三路 LED 覆盖和控制工具及相关测试。
- `adaptation/live/`：中英双语安装器、Live 登录环境/提示及模拟测试。
- `adaptation/emmc/`：eMMC 首次启动扩容脚本和服务。
- `adaptation/build_*.py`：离线镜像打包脚本，使用 `debugfs` 编辑文件系统。

`build/` 和 `output/` 都是构建者本地生成、被 Git 忽略的目录，克隆源码后不会自带这些内容。构建者可用 `--gzip-only --cleanup` 只保留验证后的压缩成品和元数据，再将标准版成品上传至 Release、大卡完整版上传至 OneDrive；安装者使用对应下载入口即可。

R5 可直接从已有 R4 TF / eMMC 镜像派生，不需要重走 R1–R4。上游镜像、内核、deb、模块成品和原厂 NFC 共享库需自行取得。程序调用见 [USAGE.md](USAGE.md)，变化见 [CHANGELOG.md](CHANGELOG.md)。

R4 已在 TF 实机验证。此 R4 eMMC 派生镜像完成了离线启动文件复用、文件系统、GPT 及扩容模拟校验；该具体内核与配置组合尚未进行 eMMC 独立启动实测。写入 eMMC 会覆盖原系统，操作前应准备可用的样机安卓恢复附件或自备整盘备份，并确认恢复入口。仓库脚本只生成本地镜像，不自动写设备。

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

## 大卡 Live 安装与恢复（16GB 及以上）

这是新增的便利版，保留原有小卡版及其手动流程。Live 系统本身基于 R5，继承屏幕、网络、扫码器、NFC 和灯控配置；卡内已放好两份压缩镜像：

| 内置文件 | 用途 |
| --- | --- |
| `/opt/pf818-installer/images/linux-emmc.img.gz` | 将 R5 Linux 安装到机内 eMMC |
| `/opt/pf818-installer/images/android-stock.img.gz` | 将机内 eMMC 恢复为样机 Android 7.1.2 |

### 1. 写卡并启动

1. 打开 [OneDrive 下载文件夹](https://1drv.ms/f/c/186e2631aeb25aa5/IgC3XRdvnzqtTa9NNZnPOoe0ATY4-Ukp5VOf0kAp7Uel23Y?e=9RNoSk)，下载文件名带 **`2026-10-26_0233`** 的 `PF818_R5_LIVE_16GB_*.img.gz` 修复版（约 2.7GiB）。此包单独通过 OneDrive 分发，无需到 GitHub Releases 查找。
2. 解压得到 `.img`；电脑需有约 9GiB 的解压空间。用 balenaEtcher 把该镜像写入 **16GB 或更大的 TF 卡**，等待写入验证完成。
3. PF818 关机，插入 TF 卡，连接网线，再开机。安装/恢复不需要外接 U 盘。
4. 直接使用 **`root` / `1234`** 登录。Live 版跳过 Armbian 的首次用户创建流程，也不强制首次改密；登录提示会提醒可用 `passwd` 自行修改。

没有键盘时，可让 PF818 和电脑处在同一局域网：网线接有 DHCP 的路由器/交换机，电脑使用同一网络的有线或 Wi-Fi。在路由器设备列表中查找 **`pf818-live`** 的 IP，再从电脑终端连接，例如：

```sh
ssh root@192.168.1.123
```

将示例地址换成设备实际 IP。SSH 使用 22 端口；网线直接接电脑时需另行配置 IP 或网络共享。

### 2. 登录后的中英双语提示

每次交互式登录会显示简体中文和英文提示，包括安装命令、联网方式及 `passwd` 改密说明。运行：

```sh
sudo pf818-install
```

已经是 root 时可直接运行 `pf818-install`。如需修改登录密码，运行 `passwd`。

### 3. 选择语言及系统，按提示完成写入

安装器首先提供 **1. 简体中文 / 2. English** 语言选择，然后提供：

- **1. 安装 R5 Linux 到机内 eMMC**。
- **2. 恢复样机 Android 到机内 eMMC**。
- **0. 退出**。

选定操作后，程序按五步执行：

1. 检查当前根系统来自 TF，识别唯一的内部 eMMC，并显示源 TF、目标 eMMC、容量与操作。
2. 流式解压校验所选镜像的长度和 SHA-256；安卓恢复要求目标容量与完整备份一致。
3. 显示覆盖范围，要求输入包含实际目标设备名的完整确认文字，例如 `INSTALL /dev/mmcblk1` 或 `RESTORE /dev/mmcblk1`。以程序当时显示的文字为准，其他输入取消。
4. 关闭目标上的交换，卸载目标分区，再以独占方式打开 eMMC 写入，显示进度。
5. 同步写入并读回 SHA-256 校验；通过后提示关机、拔 TF，再从机内系统启动。

确认后将覆盖 eMMC 原系统和数据。写入期间保持供电；若中断或校验失败，保留 TF 卡启动环境，检查日志并重试。程序不写 TF，不修改 eMMC 的硬件 `boot0` / `boot1` 区。日志保存在 `/var/log/pf818-install.log`。

完成后可在菜单中选择关机，也可返回菜单。**关机后拔出 TF 卡再开机**，才能验证机内 Linux 或安卓；Linux 首次从 eMMC 启动会使用原有扩容服务。

安装器已用临时普通文件模拟写入、损坏镜像、取消操作、目标检查和读回校验；Live 镜像也已完成离线文件系统、GPT、内置包、账号及启动配置检查。大卡 Live 已从 32GB TF 卡实机启动并通过 SSH 登录；修复后的安装器已在该系统通过测试及实际设备的写入前准备检查。**尚未通过安装器写入真实 eMMC 并验收 Linux/安卓启动。**

## 烧录与恢复：完整操作步骤

以下是手动安装方法。标准小卡版通过 U 盘提供系统包；大卡 Live 版也可使用这套流程，直接读取卡内已有的包，无需 U 盘。使用大卡版时通常优先选择上一节的 `pf818-install` 菜单。

两种操作都从 **TF 卡上的 Linux** 中完成：

| 要做的事 | 从哪里启动 | 写入哪个文件 | 写到哪里 |
| --- | --- | --- | --- |
| 把 R5 Linux 安装到机内 | R5 TF 版或大卡 Live 版 | `PF818_R5_EMMC_*.img.gz`，或 Live 内置的 `linux-emmc.img.gz` | eMMC 整盘 |
| 将机内系统恢复为安卓 | Linux TF 卡 | 样机安卓整盘备份、自备整盘原始备份 `.img.gz`，或 Live 内置的 `android-stock.img.gz` | eMMC 整盘 |

若始终只从 TF 卡运行 Linux，未写过 eMMC，**关机、拔卡、重新开机就能回到原来的安卓**，不需要执行恢复写入。

以下步骤适用于使用 Windows、macOS 或 Linux 电脑下载附件的读者。准备文件可用文件管理器完成；进入 TF 后的刷写命令统一在 **PF818 的 Linux Bash** 中执行。**路径占位符需换成你自己的实际路径；不要求与开发者相同的电脑目录。eMMC 编号和镜像长度从实际设备及文件读取，样机备份的已知校验值只用于对应的恢复附件。**

### 一、准备 TF 卡和系统包

**大卡 Live 版：** 按上文写卡并启动即可，两份系统包已内置。跳过本节 U 盘准备，从「二、公共准备」开始执行；其中第 4 步选择大卡版的镜像目录。

**标准小卡版：** 按以下步骤准备 TF 卡及 U 盘。

1. 从所选 Release 下载 TF 版、eMMC 版及对应校验文件。
2. 准备至少 4GB TF 卡，用于启动 Linux；另准备容量足够的 U 盘，用于存放 eMMC 安装包或安卓恢复备份。R5 安装包可使用至少 4GB 的 U 盘，安卓备份按其实际大小准备空间。U 盘使用 Linux 可读取的 FAT32 或 exFAT；单文件超过 4GiB 时使用 exFAT。更改格式会清空 U 盘，先保存其中的数据。
3. 解压 TF 版 `.img.gz` 得到 `.img`，用 balenaEtcher 选择该 `.img` 和 TF 卡，完成写入及验证。
4. 在 U 盘根目录新建 `pf818` 文件夹，将 eMMC 版 `.img.gz`、同名 `.img.gz.sha256`、`.img.sha256`（以及可选 `.json`）复制进去。U 盘无需特定卷标。
5. 若要恢复安卓，从 Release 下载发布者提供的样机安卓整盘备份 `PF818_Stock_Android_*.img.gz`，放入同一个文件夹；若附件提供了校验文件，也一起复制。也可以使用自行保存的完整备份，不要求每位使用者都先制作自己的备份。恢复文件仍需单独下载，源码压缩包和 R5 Linux 镜像都不包含安卓恢复数据；厂商升级包不等同于整盘原始备份。

上面的复制步骤在所有电脑上都可使用文件管理器完成。若使用 Linux/macOS 终端，下面是等价示例；两个 `/path/to/...` 都是需要替换的路径，不要求任何固定的用户名、下载目录或仓库位置：

```bash
DOWNLOAD_DIR="/path/to/release-downloads"  # 所选 Release 附件的本地下载目录
USB_DIR="/path/to/usb-mountpoint"         # 电脑上 U 盘的实际挂载目录

test -d "$DOWNLOAD_DIR"
test -d "$USB_DIR"
mkdir -p "$USB_DIR/pf818"
cp "$DOWNLOAD_DIR"/PF818_R5_EMMC_*.img.gz \
   "$DOWNLOAD_DIR"/PF818_R5_EMMC_*.img.gz.sha256 \
   "$DOWNLOAD_DIR"/PF818_R5_EMMC_*.img.sha256 \
   "$USB_DIR/pf818/"
sync
```

只进行其中一种操作时，可以只复制对应的镜像。压缩包无需预先解压到 U 盘，下面会边解压边写入。TF 镜像的根分区固定约 2.4GiB，剩余空间放不下这些安装包；若沿用“预先把镜像放进 TF 根分区”的方法，需要先在更大的 TF 卡上扩展分区。

### 二、公共准备：从 TF 启动，识别 eMMC 并选择镜像目录

#### 1. 从 TF 启动，进入 root Bash

PF818 关机，插入已写好的 TF 卡；标准小卡版再插入存有系统包的 U 盘。开机进入 Armbian。以下命令全部在 **PF818 的 TF Linux 终端或它的 SSH 会话中** 执行，不是在用于下载附件的电脑上执行。

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

容量以你的设备实际输出为准。核对输出，确认根系统所在 TF 与目标 eMMC 是不同设备。后续代码使用上面设置的 `EMMC_DEV`；若换了终端或重新登录，需重新执行公共准备。

#### 3. 卸载 eMMC 上正在使用的分区

先检查是否有交换分区或交换文件位于 eMMC 上：

```bash
swapon --show
```

若有，先用 `swapoff` 关闭该条目。例如输出中的路径为 `/dev/mmcblk1p3`，则执行 `swapoff /dev/mmcblk1p3`；若为交换文件，则执行 `swapoff /实际路径/交换文件`。TF 上的交换和 `/dev/zram*` 无需关闭。

这里使用的 `swapon --show` 已在 Live 真机验证；不要添加 `--json`，镜像自带的 `swapon` 不支持该参数。也可用 `cat /proc/swaps` 查看交换区。

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

#### 4. 选择镜像目录（两种方式选一种）

**大卡 Live 版：** 使用内置包，执行下面的代码后直接进入「三、安装 R5」或「四、恢复安卓」，不需要执行后面的 U 盘命令：

```bash
IMAGE_DIR=/opt/pf818-installer/images
test -d "$IMAGE_DIR"
test -f "$IMAGE_DIR/../manifest.json"
ls -lh "$IMAGE_DIR"
```

**标准小卡版：** 挂载存放镜像的 U 盘：

用 `lsblk` 查看刚插入的 USB 存储分区，按容量、文件系统和 `TRAN` 列区分 U 盘与两种 MMC 介质。将下面的 `/dev/sdX1` 替换为**实际 U 盘分区**，不要求它固定为 `/dev/sda1`，也不要求特定卷标：

```bash
lsblk -o NAME,SIZE,TYPE,TRAN,FSTYPE,LABEL,MOUNTPOINTS
USB_PART="/dev/sdX1"  # 按上面的输出替换
USB_PART="$(readlink -f "$USB_PART")"
test -b "$USB_PART" || { echo "没有找到指定的 U 盘分区"; exit 1; }
case "$USB_PART" in
    "$EMMC_DEV"|"$EMMC_DEV"p[0-9]*)
        echo "镜像不能存放在即将覆盖的 eMMC 上。"
        exit 1
        ;;
esac

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
cd "$IMAGE_DIR"
if [ -f linux-emmc.img.gz ] && [ -f ../manifest.json ]; then
    # 大卡 Live：从内置清单取得原始镜像校验值。
    LINUX_IMAGE=linux-emmc.img.gz
    EXPECTED_LINUX_SHA="$(python3 -c \
        'import json; print(json.load(open("../manifest.json"))["images"]["linux"]["sha256"])')"
else
    # 标准小卡：使用下载的 eMMC 镜像及校验附件。
    LINUX_FILES=(PF818_R5_EMMC_*.img.gz)
    if [ "${#LINUX_FILES[@]}" -ne 1 ] || [ ! -f "${LINUX_FILES[0]}" ]; then
        echo "请在此目录只保留所选 Release 的一份 R5 eMMC 压缩镜像。"
        exit 1
    fi
    LINUX_IMAGE="${LINUX_FILES[0]}"
    sha256sum -c "$LINUX_IMAGE.sha256"
    LINUX_RAW_SUM="${LINUX_IMAGE%.gz}.sha256"
    test -f "$LINUX_RAW_SUM"
    EXPECTED_LINUX_SHA="$(awk 'NR == 1 {print $1}' "$LINUX_RAW_SUM")"
fi

LINUX_BYTES="$(gzip -dc "$LINUX_IMAGE" | wc -c | tr -d '[:space:]')"
test "$LINUX_BYTES" -gt 0
test "$EMMC_BYTES" -ge "$LINUX_BYTES"
ARCHIVE_LINUX_SHA="$(gzip -dc "$LINUX_IMAGE" | sha256sum | awk '{print $1}')"
test "$ARCHIVE_LINUX_SHA" = "$EXPECTED_LINUX_SHA"
printf '安装镜像：%s\n解压后长度：%s 字节\n' "$LINUX_IMAGE" "$LINUX_BYTES"
echo "R5 安装包校验通过。"
```

应看到 `R5 安装包校验通过。`，标准小卡版还会显示压缩包校验结果 `OK`。使用的是 **EMMC 安装包**，TF 版继续留在卡上作为启动与恢复环境。

#### 2. 写入 eMMC 整盘

**此步骤会覆盖机内原来的安卓或 Linux。** 确认目标为上面识别的 eMMC，并保持供电：

```bash
printf '即将把 R5 写入：%s\n' "$EMMC_DEV"
gzip -dc "$IMAGE_DIR/$LINUX_IMAGE" | \
    dd of="$EMMC_DEV" bs=4M iflag=fullblock conv=fsync status=progress
sync
```

等待整个命令成功退出，写入字节数应等于上一步统计的 `LINUX_BYTES`。统计及写入均采用流式解压，不会把完整 `.img` 保存到 TF 根分区。`EMMC_DEV` 指整盘，不是末尾带 `p1`、`p2` 的分区。

#### 3. 校验写入内容

R5 镜像比 eMMC 容量小，所以只校验刚写入的镜像长度：

```bash
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

此处适用于 **Linux 已经写入 eMMC** 的情况。设备关机，重新插入 Linux TF 卡；标准小卡版还需插入存有备份的 U 盘，大卡 Live 版直接使用内置备份。开机后先完整执行“二、公共准备”。不要从当前 eMMC 内的系统覆盖它自己。

#### 1. 检查原厂备份和目标容量

可以使用 Release 提供的样机安卓 eMMC 用户区整盘原始备份、大卡 Live 内置备份，也可以使用自备的同类 `.img.gz` 文件。下面会自动选择 Live 内置包；标准小卡版默认使用项目的样机备份文件名，若选用其他文件，只修改 `ANDROID_IMAGE`。厂商升级包不适用这些整盘写入命令。

项目样机备份 `PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz` 已核对：解压后 **15,634,268,160 字节**，原始镜像 SHA-256 为 `08bc74ae677abdfc928faaab123dee939b6704a0dbc40fe81283c4dda595bb0b`。这些值对应这一份发布附件，不是电脑路径或所有备份的通用参数。

先校验备份（若附有原先保存的同名 `.sha256` 文件），再流式读取解压后的长度及 SHA-256。此过程不将完整原始镜像保存到 TF 卡：

```bash
ANDROID_IMAGE="PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz"
# 若使用其他整盘原始备份，将上面的值改成实际文件名。
cd "$IMAGE_DIR"
if [ -f android-stock.img.gz ] && [ -f ../manifest.json ]; then
    ANDROID_IMAGE=android-stock.img.gz
fi
test -f "$ANDROID_IMAGE"
if [ -f "$ANDROID_IMAGE.sha256" ]; then
    sha256sum -c "$ANDROID_IMAGE.sha256"
fi

python3 - "$ANDROID_IMAGE" > /tmp/pf818-android-restore-meta.txt <<'PY'
import gzip
import hashlib
import json
import sys
from pathlib import Path

size = 0
digest = hashlib.sha256()
with gzip.open(sys.argv[1], "rb") as backup:
    while chunk := backup.read(16 * 1024 * 1024):
        size += len(chunk)
        digest.update(chunk)
if sys.argv[1] == "android-stock.img.gz":
    entry = json.loads(Path("../manifest.json").read_text())["images"]["android"]
    if size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
        raise SystemExit("Live 内置安卓包与清单不符，停止恢复。")
print(size, digest.hexdigest())
PY

read -r ANDROID_BYTES EXPECTED_ANDROID_SHA < /tmp/pf818-android-restore-meta.txt
printf '备份解压后长度：%s 字节\n备份 SHA-256：%s\n' \
    "$ANDROID_BYTES" "$EXPECTED_ANDROID_SHA"

# 使用项目样机附件时，与已核对的发布数据比较。
if [ "$ANDROID_IMAGE" = "PF818_Stock_Android_7.1.2_EMMC_2026-10-21_1159.img.gz" ]; then
    test "$ANDROID_BYTES" -eq 15634268160
    test "$EXPECTED_ANDROID_SHA" = "08bc74ae677abdfc928faaab123dee939b6704a0dbc40fe81283c4dda595bb0b"
fi

if [ "$EMMC_BYTES" -ne "$ANDROID_BYTES" ]; then
    echo "目标容量与整盘备份不一致，停止恢复。"
    exit 1
fi
echo "备份读取完整，容量匹配。"
```

`EXPECTED_ANDROID_SHA` 用于下一步与写入后的整块 eMMC 比较；它表示当前选定备份的内容，不是对任意备份来源或适用机型的保证。

#### 2. 将安卓整盘备份完整写回 eMMC

**此步骤会覆盖 eMMC 中的 Linux 和后续数据，并恢复到备份时的安卓内容。**

```bash
printf '即将将安卓整盘备份写回：%s\n' "$EMMC_DEV"
gzip -dc "$IMAGE_DIR/$ANDROID_IMAGE" | \
    dd of="$EMMC_DEV" bs=4M iflag=fullblock conv=fsync status=progress
sync
```

等待整个命令成功退出，写入量应等于上一步统计的 **`ANDROID_BYTES`**。由于是完整写回同一容量的 eMMC，原有 Linux 分区信息也会被覆盖。

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

eMMC 的 `boot0`、`boot1` 是独立硬件启动区，不是安卓名为 `boot` 的系统分区；后者包含在主备份中。本文的 R5 安装只写 eMMC 用户区，未修改硬件启动区或启动配置，**若你也没有另行改动它们，按本文路线恢复时无需写 boot0、boot1**。仍应保存自己设备的这些额外备份；其他设备或曾改动过硬件启动区的情况，需按其实际备份和启动配置处理，不能假定它们全为零。

### 五、当前验证范围与恢复入口

项目当前已完成开发样机上的扫码器安卓接口验证、三路灯点亮及位置确认、R5 镜像离线检查、大卡 Live 的 32GB TF 启动与 SSH 登录，以及样机安卓恢复附件的完整性/容量/关键引导区域核对。**灯控与扫码的 Armbian 启动后验证、eMMC 安装/独立启动、实际安卓回刷启动尚未执行验收。** 下载后仍按上面的命令检查附件和写入内容。

如果 TF 卡也无法启动，需要转用 Rockchip Loader / MaskROM USB 恢复。PF818 的具体恢复入口及匹配的 DDR/USB Loader 目前尚未验证；该路径不在上面的 TF 恢复命令中。相关文件说明见 [RESTORING_ANDROID.md](RESTORING_ANDROID.md)，驱动和工具来源见 [NOTICE.md](NOTICE.md)。

## 上游与来源

感谢 [ophub](https://github.com/ophub) 提供 SW799 的 Armbian 镜像与 [内核成品](https://github.com/ophub/kernel)。设备树以其 SW799 设备树为基础，结合原厂 Android 运行时设备树核对底板连接。屏幕初始化序列来自原厂运行时面板节点；NFC 用户态适配需使用本机原厂应用中的读卡库。来源与许可范围见 [NOTICE.md](NOTICE.md)。
