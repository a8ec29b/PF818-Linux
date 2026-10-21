# 来源与许可

- 基础系统来自 ophub/amlogic-s9xxx-armbian，使用 Linux 6.18.57-ophub。内核与用户空间二进制由使用者从对应上游获取，并遵守各上游许可。
- `rk3399-pf818*.dts` 是以 ophub SW799 设备树为基础的派生设备树，保留 RK3399 通用节点并修改底板连接；原有内容的权利归相应上游作者。
- `adaptation/round2/panel/panel_pf818.c` 标明 `GPL-2.0`，加载模块使用该文件声明的 GPL 许可。
- 面板初始化字节来自原厂 Android 运行时设备树的 `/dsi@ff960000/panel@0/mipi0_lcd_07`，538 字节、108 条命令，SHA-256 为 `b1e82f59c0758ccee8d6334961611ab0c8af7c697f4eb71067e0a1477c4687c8`。
- NFC 适配脚本和辅助源码用于配合设备原厂 `libicreader-lib.so`；原厂库需由使用者从自己的设备取得，其权利与许可归原权利人。

本仓库没有为上游内容及原厂材料重新授予许可；各文件已有的许可标识继续有效。
