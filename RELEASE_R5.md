# PF818 R5：扫码器、红绿指示灯及摄像头补光

在 R4 的 6.18.57-ophub / Armbian trixie 基础上加入 NFC 下方独立扫码器的原生串口支持，以及红绿指示灯和摄像头白色补光控制。扫码程序可直接获取解码内容，不依赖安卓应用或原厂扫码库；灯光采用标准 Linux LED 接口，三路默认关闭。

## 新功能

- 固定设备名 `/dev/pf818-scanner`，115200 / 8N1。
- GPIO1_C7 供电配置，复用镜像已有 `xr_serial` 驱动。
- `pf818-scan` 输出文本，`pf818-scan --json` 输出 JSON Lines，`--once --timeout 30` 可读取一次。
- `pf818-led` 控制顶部左上角绿灯、其右侧红灯和主摄像头两侧白色补光；红绿灯支持内核定时闪烁，补光按需开关。
- TF/eMMC 两种镜像，各自使用独立 UUID/GUID；保留 R4 的内核、屏幕、NFC 和其他适配。
- 默认分发两份约 797MiB 的压缩镜像，不保留重复的未压缩成品与临时镜像。
- 新增大卡 Live 版：推荐 **16GB 及以上 TF 卡**，包含 Linux 安装包与安卓恢复包，直接 root/1234 登录；终端显示双语提示，运行 `sudo pf818-install` 先选语言再安装/恢复。标准小卡版继续提供。

## 大卡 Live 版：OneDrive 分发

2026-10-26 更新：修复安装器在第 4 步因 `swapon --json` 不受支持而退出的问题，并同步大卡版使用内置包的手动安装/恢复教程。

大卡包 `PF818_R5_LIVE_16GB_*.img.gz` 是一个约 2.7GiB 的完整文件，不分片。下载入口见 [README 的大卡完整版说明](README.md#下载镜像与获取源码)，通过 **OneDrive** 单独分发，不作为 GitHub Release 的镜像附件上传。

解压后约 8.14GiB，用 Etcher 写入至少 16GB TF 卡。从 TF 启动后，可通过有线 DHCP/SSH 登录，设备名为 `pf818-live`，账号 root、密码 1234。Live 跳过首次账号设置和强制改密，登录后以中英双语提示使用 `pf818-install` 和 `passwd`。

安装器先选择简体中文或 English，再选择安装 R5 Linux 或恢复样机 Android。两个包均已内置，无需 U 盘；程序校验、显示并确认目标 eMMC、写入、读回验证后提示关机拔卡。完整操作见 [README](README.md#大卡-live-安装与恢复16gb-及以上)。

## 选择附件

以下是标准小卡版，从本条 Release 的附件下载；安装者不需要克隆源码，也不需要电脑上存在构建者的 `output/`。不要将 GitHub 自动生成的 Source code 压缩包当作系统镜像。

- `PF818_R5_TF_*.img.gz`：解压后用 Etcher 写 TF，至少 4GB 卡；首次启动不自动扩容。
- `PF818_R5_EMMC_*.img.gz`：在 TF 启动的 Linux 中写入 eMMC，首次从 eMMC 启动时扩容。
- `.sha256`：校验对应的压缩包或未压缩镜像。
- `.json`：来源、UUID、构建信息和离线验证结果。
- `PF818_Stock_Android_*.img.gz`（若附带）：可用于刷回安卓的样机整盘原始备份。也可选用自备的同类备份。

eMMC 安装请同时下载同一个版本的镜像、`.img.gz.sha256` 和 `.img.sha256`，不要混用不同构建的文件。下载目录和 U 盘路径自行选择；README 的命令会匹配实际附件名，不依赖开发者的电脑目录。

烧录流程与 R4 相同：**Etcher 写 TF → 关机插卡 → 从 TF 启动 → 在 TF 的 Linux 中把 eMMC 版镜像写入机内存储 → 关机拔卡 → 从 eMMC 启动**。原先通过 `chroot` 预先放置安装镜像的准备方式仍可沿用。

TF 固定根分区的剩余空间装不下另一个完整镜像；需要将安装镜像存入 TF 系统时，先在更大的 TF 卡上扩展分区，或把文件放在 U 盘/通过网络提供。写入前按实际 `SD` / `MMC` 类型和根挂载识别介质，不要硬编码设备编号。完整安装及安卓恢复命令见 [README](README.md#烧录与恢复完整操作步骤)，附件说明见 [INSTALLING.md](INSTALLING.md)。

## 使用

```sh
pf818-scan --once --timeout 30
pf818-scan --json
pf818-nfc-read
pf818-led status
sudo pf818-led green on
sudo pf818-led green off
sudo pf818-led fill on
sudo pf818-led fill off
```

普通用户可加入 `dialout` 组并重新登录后使用扫码器；其他设备及 Python 调用示例见 [USAGE.md](USAGE.md)。基础账户沿用 `root` / `1234`，首次登录后修改密码。

## 已验证与待验证

已在原厂安卓真机上运行静态 ARM64 Linux 程序，正确接收已知二维码 `PF818-LINUX-SCAN-20261024`。三路灯逐路点亮并由使用者确认实际位置和颜色。八项串口检查、四项 LED 工具检查及两种镜像的离线文件系统/GPT/载荷/LED 映射/默认关闭/引导区域/压缩读回检查通过。

**R5 大卡 Live 已从 32GB TF 卡启动并通过有线 SSH 登录；Armbian 下的读码、LED 控制、eMMC 安装和独立启动尚未实测，建议先作为预发布版本验收。** 本次没有改写设备内的安卓系统。扫码图像输出和桌面键盘模拟不在本版实现范围内。

修复后的安装器已在 Live 真机通过 14 项临时文件/模拟设备测试及实际设备的写入前准备检查；另有 1 项 GPT 测试和镜像的 26 项离线检查。真实 eMMC 安装/恢复仍待设备验收。
