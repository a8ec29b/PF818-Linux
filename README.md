# PF818 Linux 适配

PF818 收银终端的 Linux 外设适配源码，硬件采用 Rockchip RK3399 / SW799 核心板，**底板为 SW7990D Ver1.3**。以已实机验证的 R4 配置为基线。

基础系统来自 [ophub/amlogic-s9xxx-armbian](https://github.com/ophub/amlogic-s9xxx-armbian)：

| 项目 | 使用版本 |
| --- | --- |
| 原始镜像 | `Armbian_26.11.0_rockchip_sw799_trixie_6.18.57_server_2026.10.17.img` |
| 系统 | Armbian 26.11.0 / Debian trixie / ARM64 |
| 内核 | **6.18.57-ophub** |
| 上游设备树 | `rockchip/rk3399-bozz-sw799.dtb` |

内核镜像、initramfs、引导程序及现有模块直接复用 ophub 成品。适配主要修改底板设备树，另编译一个小型 `panel_pf818` 屏幕模块，加入横屏登录配置、NFC 工具和 EC20 查询工具。没有重编整个内核或重新打包系统 deb。

## 外设状态

| 外设 | R4 实测情况 |
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
| 独立扫码器 | 原厂按串口扫码器使用，未推进适配 |
| 指示灯 | 未推进适配 |

内屏保留默认背光设置。实机观察到屏幕附近持续发热，关闭背光后等待约十分钟明显降温；尚未确认具体发热元件。横屏配置用于文本登录，图形桌面的旋转及触摸坐标映射需要另行配置。

## 源码与打包

- `adaptation/round1/`：TF、USB 供电、有线网络及启动日志。
- `adaptation/round2/`：屏幕模块、初始化序列、触摸、按键和横屏登录。
- `adaptation/round3/`：蓝牙与 modem 供电设备树。
- `adaptation/round4/`：最终 R4 设备树、NFC 绑定及用户态适配、QMI / AT 查询工具。
- `adaptation/emmc/`：eMMC 首次启动扩容脚本和服务。
- `adaptation/build_*.py`：离线镜像打包脚本，使用 `debugfs` 编辑文件系统。

完整准备步骤见 [BUILDING.md](BUILDING.md)。仓库仅保存适配源码与配置；上游镜像、内核、deb、模块成品和原厂 NFC 共享库需自行取得。

TF 镜像为未压缩 `.img`，约 **2577 MiB**，BOOT 128 MiB、ROOTFS 2432 MiB，可用 balenaEtcher 写入 4GB TF 卡，首次启动保持固定分区。eMMC 镜像从同一 R4 派生，仅在识别到根文件系统来自 eMMC 时扩容第二分区及 ext4。文件名带打包时间，精确到分钟，同时生成 SHA-256 和 JSON 清单。

镜像继承基础系统登录账户 `root` / `1234`，有线 DHCP，首次使用应修改密码。Wi-Fi 由使用者配置。

R4 已在 TF 实机验证。此 R4 eMMC 派生镜像完成了离线启动文件复用、文件系统、GPT 及扩容模拟校验；该具体内核与配置组合尚未进行 eMMC 独立启动实测。写入 eMMC 会覆盖原系统，需要自行保存完整原厂备份并确认恢复入口。仓库脚本只生成本地镜像，不自动写设备。

## 上游与来源

感谢 [ophub](https://github.com/ophub) 提供 SW799 的 Armbian 镜像与 [内核成品](https://github.com/ophub/kernel)。设备树以其 SW799 设备树为基础，结合原厂 Android 运行时设备树核对底板连接。屏幕初始化序列来自原厂运行时面板节点；NFC 用户态适配需使用本机原厂应用中的读卡库。来源与许可范围见 [NOTICE.md](NOTICE.md)。
