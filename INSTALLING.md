# TF 启动与 eMMC 安装

安装已发布镜像时，从当前仓库的 **Releases 附件**下载文件即可，不需要克隆源码或在电脑上存在 `output/`。完整命令统一维护在 [README 的烧录与恢复流程](README.md#烧录与恢复完整操作步骤)，涵盖 Windows/macOS/Linux 电脑准备文件，以及 PF818 上的 Linux Bash 操作。

## 选择同一个 Release 的附件

| 附件 | 用途 |
| --- | --- |
| `PF818_R5_TF_*.img.gz` | 解压后用 Etcher 写入至少 4GB TF 卡，作为启动与安装/恢复环境 |
| `PF818_R5_EMMC_*.img.gz` | 从 TF 系统写入机内 eMMC，首次从 eMMC 启动后扩容 |
| 同名 `.img.gz.sha256` | 校验压缩包 |
| 同名 `.img.sha256` | 校验解压后的镜像或写入内容 |
| 同名前缀 `.json` | 来源、镜像大小、UUID 和构建验证清单 |

文件名中的星号对应实际 Release 版本、内核和时间戳。eMMC 安装需要同时下载压缩镜像与两种 `.sha256`，放在同一目录；不要混用不同构建的文件。GitHub 的 Source code 压缩包只有源码，不是启动镜像。

## 安装路线

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

TF 版的根分区固定约 2.4GiB，剩余空间不足以放下另一份完整镜像。可以将安装包放在 U 盘上或通过网络提供；若要预先放入 TF 根分区，需使用更大的卡并先扩展分区。

## 恢复安卓

若未改写 eMMC，关机拔 TF 即可回到安卓。已经覆盖过 eMMC 时，重新从 TF 启动，再按 README“四、恢复安卓”将样机恢复附件或自备的安卓整盘原始备份写回。恢复附件需单独下载或自行保存，详见 [RESTORING_ANDROID.md](RESTORING_ANDROID.md)。

R5 的 TF 冷启动、Armbian 中的扫码/灯控、eMMC 独立启动及安卓回刷启动仍待实机验收；已完成的硬件调查和离线验证范围见 README。
