# Linux 程序调用

## 独立扫码器（R5）

NFC 下方的扫码窗口是带解码功能的独立扫码模块。已确认的接口返回解码结果；本次没有发现可供它输出图像的 V4L2 接口。它不占用已适配的两路 USB 摄像头。

| 项目 | 值 |
| --- | --- |
| 安卓节点 | `/dev/ttyXRUSB2` |
| USB 芯片及端口 | Exar XR22804 UART C |
| USB ID | `04e2:1402` |
| Linux 驱动 | `xr_serial`（R4 内核已有模块） |
| Linux 固定节点 | `/dev/pf818-scanner`，实际指向一个 `/dev/ttyUSB*` |
| 串口参数 | 115200，8 数据位，无校验，1 停止位，无流控 |
| 电源 | GPIO55，即 GPIO1_C7，输出高 |
| 测试结果 | 已知二维码返回 25 字节文本，后跟 CR LF |

R5 启动后先确认节点和驱动：

```sh
ls -l /dev/pf818-scanner
udevadm info --query=property --name=/dev/pf818-scanner
sudo pf818-scan --once --timeout 30
```

将二维码对准扫码窗口即可；工具不发送配置或触发命令。持续读取：

```sh
pf818-scan
pf818-scan --json
```

普通用户加入 `dialout` 组后重新登录即可访问：

```sh
sudo usermod -aG dialout YOUR_LINUX_USER
```

文本模式每次扫码输出一行并立即刷新。`--once` 在收到一条后退出；`--timeout 30` 限制整个命令最长运行 30 秒。退出码：0 成功，1 错误，2 超时，128+信号表示中断。持续模式下不带 `--timeout` 可一直等待。

JSON 模式示例：

```json
{"text":"PF818-LINUX-SCAN-20261024","hex":"50463831382d4c494e55582d5343414e2d3230323631303234","bytes":25}
```

`hex` 始终保留有效载荷字节；非 UTF-8 数据的 `text` 为 `null`。默认用 CR / LF 分帧，并以 500ms 空闲作为没有后缀时的兜底。带换行或二进制内容的二维码可使用 `pf818-scan --json --framing gap`，此时换行保留在载荷里；两次扫码之间必须有至少 500ms 空闲，也可按实际设备设置 `--gap-ms`。扫码模块的 CR/LF 后缀在 gap 模式下也会保留。

程序启动时丢弃串口旧缓冲，避免把先前波特率下的数据或上次扫码残留作为新结果；每条上限 65536 字节，超限报错，不返回截断数据。已观察到的 `00 00 ff fc` 四字节状态帧被忽略；其他二进制内容保留。不要同时运行多个串口读取程序；它们会竞争数据。命令之间有读取锁，直接打开串口的第三方程序也需要自行遵守单读取者约定。

Python 业务程序可以直接消费 JSON Lines：

```python
import json
import subprocess

process = subprocess.Popen(
    ["pf818-scan", "--json"],
    stdout=subprocess.PIPE, text=True, encoding="utf-8",
)
try:
    for line in process.stdout:
        result = json.loads(line)
        if result["text"] is not None:
            print("扫码内容:", result["text"])
        else:
            print("二进制码:", bytes.fromhex(result["hex"]))
    if process.wait() != 0:
        raise RuntimeError("扫码器读取程序退出")
finally:
    if process.poll() is None:
        process.terminate()
        process.wait()
```

C/C++、Go、Rust、Node.js 也可以启动此命令并读取 stdout；长期运行的程序建议复用一个进程。也可直接打开固定设备节点，按表中参数配置 termios，再按 CR/LF 组装数据。`pf818-scan.c` 是完整示例。这里提供的是程序可读取的文本流，不会自动向桌面中有焦点的输入框模拟键盘打字。

如果没有固定节点，检查：

```sh
lsusb -d 04e2:1402
sudo modprobe xr_serial
dmesg | tail -80
grep fdtfile /boot/armbianEnv.txt
```

应使用 `rockchip/rk3399-pf818-r5.dtb`。`/sys/kernel/debug/gpio` 中应有 `pf818-scanner-power` 且输出为高；debugfs 未挂载时可先 `sudo mount -t debugfs debugfs /sys/kernel/debug`。不要按安卓的全局 GPIO 编号在新内核里盲目导出 GPIO55，R5 由设备树管理这根引脚。

## 红绿指示灯与摄像头补光（R5）

三路实际位置、GPIO 和完整命令见 [README](README.md#r5-的扫码器指示灯与补光调用)。红灯、绿灯为设备顶部左上角相邻的两颗独立状态灯；白色补光位于主摄像头两侧，与原厂注释“二维码灯”不同。

```sh
pf818-led status
sudo pf818-led green on
sudo pf818-led green off
sudo pf818-led red blink --on-ms 200 --off-ms 800
sudo pf818-led red off
sudo pf818-led fill on
sudo pf818-led fill off
```

`pf818-led status` 或 `pf818-led green status` 返回 JSON。标准 sysfs 路径分别为 `/sys/class/leds/green:status`、`/sys/class/leds/red:status`、`/sys/class/leds/white:flash`。写入 `brightness` 的 0/1 控制开关，写 `trigger=none` 清除旧触发器；红绿灯可使用 `timer` 和 `delay_on` / `delay_off` 闪烁。控制工具默认以 root 权限运行，应用可通过子进程或直接写 sysfs 调用。

所有灯默认关闭，不自动根据扫码、NFC、联网结果变色；这些状态由应用决定。白色补光只提供开关，采集完成后由应用关闭。三路 GPIO 的物理点灯与位置已在安卓真机确认，R5 的 Armbian 运行时仍待验收。

## NFC 读卡器

```sh
sudo pf818-nfc-read
```

命令输出多行 JSON：第一条是芯片版本，随后是若干次寻卡/选卡尝试。程序应选取 `status == 0` 且有非空 `uid` 的记录；`uid` 为大写十六进制字符串。最多尝试五次，读取结束会关闭射频场，找到卡退出 0，未找到退出 1。

```python
import json
import subprocess

p = subprocess.run(["pf818-nfc-read"], capture_output=True, text=True)
for line in p.stdout.splitlines():
    item = json.loads(line)
    if item.get("status") == 0 and item.get("uid"):
        print(item["uid"])
```

现有 NFC 适配只提供 ISO14443-A 寻卡、选卡和 UID。读卡片数据区、写卡、充值或认证协议不在已实现范围内。NFC 仍依赖 R4 中的原厂读卡库及适配库；扫码器不依赖这些库。

## 其余外设

| 外设 | Linux 程序入口 |
| --- | --- |
| 两路 USB 摄像头 | V4L2；用 `v4l2-ctl --list-devices` 查看映射，优先 `/dev/v4l/by-id/` / `by-path/` 固定路径。可供 OpenCV、GStreamer、FFmpeg 使用，不要硬编码 `/dev/video0` 的相机身份 |
| 触摸、六个按钮 | `/dev/input/event*`，按设备名称选择；可用 `evtest` 检查，Python 可使用 `evdev`。图形桌面另配旋转和触摸坐标映射 |
| 屏幕、GPU | DRM/KMS、Mesa/Panfrost，按所用 Qt / GTK / SDL / Wayland 框架调用。现有横屏配置针对 fbterm 文本登录 |
| 有线网络、Wi-Fi | NetworkManager 管理连接，程序用普通 socket / HTTP。Wi-Fi 为 2.4GHz，沿用 R4 的信道建议 |
| 蓝牙 | BlueZ，命令行 `bluetoothctl` 或 D-Bus API；文件接收服务需应用自行配置 |
| EC20F | `pf818-modem-status` 查询 AT/SIM 状态，`pf818-qmi-status` 查询 QMI 服务版本；二者都不建立数据连接。拨号联网仍待验证 |

`v4l2-ctl`、`evtest`、Python `evdev`、OpenCV 等属于按需安装的开发工具，并非本次新加入镜像的软件。串口扫码器和 EC20 都可能出现 `/dev/ttyUSB*`，应通过固定扫码器别名或 USB 身份识别，不能按枚举顺序猜用途。
