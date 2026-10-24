# PF818 large-card Live login environment and bilingual help.
export PF818_LIVE=1
export PF818_INSTALLER=/usr/local/sbin/pf818-install
export PF818_INSTALL_BUNDLE=/opt/pf818-installer

case "$-" in
    *i*)
        printf '\n%s\n' \
            '=== PF818 Live / 大卡安装与恢复版 ===' \
            '安装 Linux 或恢复 Android：运行 sudo pf818-install' \
            'Install Linux or restore Android: run sudo pf818-install' \
            '安装器首先提供简体中文 / English 语言选择。' \
            'Choose Simplified Chinese or English when the installer opens.' \
            '登录账号 root，初始密码 1234；可运行 passwd 自行修改密码。' \
            'Account: root. Initial password: 1234. Run passwd to change it.' \
            '有线网络自动 DHCP，设备名 pf818-live；也可通过 SSH 操作。' \
            'Wired networking uses DHCP; hostname: pf818-live. SSH is available.'
        ;;
esac
