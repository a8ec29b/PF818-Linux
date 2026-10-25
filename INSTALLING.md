# TF 启动与 eMMC 安装

安装已发布镜像时，标准小卡版从 **Releases 附件**下载，大卡 Live 版通过 [README 中的 OneDrive 链接](README.md#下载镜像与获取源码)单独下载，不作为 Release 附件分发。安装者不需要克隆源码或在电脑上存在 `output/`。16GB 及以上卡推荐大卡版：已内置两个系统包，无需 U 盘。完整手动命令见 [README 的烧录与恢复流程](README.md#烧录与恢复完整操作步骤)，同时支持小卡版和大卡版。

## 大卡 Live 快速安装

1. 从 OneDrive 下载完整的 `PF818_R5_LIVE_16GB_*.img.gz`，解压后用 Etcher 写入至少 16GB 的 TF 卡。
2. 从 TF 启动 PF818，可接网线后通过 SSH 操作，DHCP 设备名为 `pf818-live`。
3. 直接使用 `root` / `1234` 登录，跳过 Armbian 首次用户创建及强制改密；终端显示中英双语安装和 `passwd` 提醒。
4. 运行 `sudo pf818-install`，先选简体中文或 English，再选安装 Linux 或恢复安卓。
5. 核对程序识别的目标 eMMC，按显示的完整文字确认。程序校验、写入、读回校验后提示关机。
6. 关机后拔 TF，再开机进入机内系统。

完整菜单流程和验证范围见 [README](README.md#大卡-live-安装与恢复16gb-及以上)。若选择手动刷写，大卡版使用内置包及清单，不需要 U 盘；按 README「二、公共准备」选择大卡版镜像目录，再执行安装或恢复命令。

## 选择同一个 Release 的附件

| 附件 | 用途 |
| --- | --- |
| `PF818_R5_TF_*.img.gz` | 解压后用 Etcher 写入至少 4GB TF 卡，作为启动与安装/恢复环境 |
| `PF818_R5_EMMC_*.img.gz` | 从 TF 系统写入机内 eMMC，首次从 eMMC 启动后扩容 |
| 同名 `.img.gz.sha256` | 校验压缩包 |
| 同名 `.img.sha256` | 校验解压后的镜像或写入内容 |
| 同名前缀 `.json` | 来源、镜像大小、UUID 和构建验证清单 |

文件名中的星号对应实际 Release 版本、内核和时间戳。eMMC 安装需要同时下载压缩镜像与两种 `.sha256`，放在同一目录；不要混用不同构建的文件。GitHub 的 Source code 压缩包只有源码，不是启动镜像。

## 标准小卡版安装路线

1. 解压 TF 版，用 Etcher 写入 TF 卡并等待验证完成。
2. 将 eMMC 压缩镜像和校验文件复制到 U 盘根目录的 `pf818` 文件夹，U 盘无需固定卷标。电脑上的下载目录和 U 盘路径由使用者选择。
3. 设备关机后插入 TF 和 U 盘，再开机进入 Armbian；基础账户为 `root` / `1234`，登录后修改密码。
4. 在 PF818 的终端或 SSH 会话中执行 README“二、公共准备”的命令，确认根系统在 TF，并识别、卸载目标 eMMC，挂载实际 U 盘。
5. 执行 README“三、安装 R5”的命令，按实际附件名选择唯一的 eMMC 镜像，校验、写入整盘并读回校验。
6. 关机后拔出 TF 卡及 U 盘，再开机验证 eMMC 启动和首次扩容。

只想在 TF 中使用 Linux，在 TF 启动后即可使用，不需要写 eMMC。首次使用可检查：

```sh
cat /etc/pf818-release
findmnt -no SOURCE /
pf818-scan --once --timeout 30
pf818-led status
```

标准小卡 TF 版的根分区固定约 2.4GiB，剩余空间不足以放下另一份完整镜像。可以将安装包放在 U 盘上或通过网络提供；若要预先放入 TF 根分区，需使用更大的卡并先扩展分区。大卡 Live 已扩为 8GiB 根分区并内置两个包。

## 恢复安卓

若未改写 eMMC，关机拔 TF 即可回到安卓。已经覆盖过 eMMC 时，重新从 TF 启动，再按 README“四、恢复安卓”将样机恢复附件或自备的安卓整盘原始备份写回。标准小卡版需单独下载或自行保存恢复附件；大卡 Live 可直接使用内置备份，详见 [RESTORING_ANDROID.md](RESTORING_ANDROID.md)。

R5 大卡 Live 已在 32GB TF 卡启动并通过 SSH 登录；Armbian 中的扫码/灯控、eMMC 独立启动及安卓回刷启动仍待实机验收。已完成的硬件调查和离线验证范围见 README。
