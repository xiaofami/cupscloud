###### CUPS云打印页面

# 测试平台
刷了Armbian当作CUPS打印服务器的N1盒子。为了方便手机远程打印（安卓手机貌似还不支持添加IPv6打印机），用**deepseek**做了一个打印页面，目前仅支持打印PDF。
```bash
pico@armbian:~/cloud5$ cat /etc/os-release 
PRETTY_NAME="Armbian 25.2.2 bullseye"
NAME="Debian GNU/Linux"
VERSION_ID="11"
VERSION="11 (bullseye)"
VERSION_CODENAME=bullseye
ID=debian
HOME_URL="https://www.armbian.com/"
SUPPORT_URL="https://forum.armbian.com"
BUG_REPORT_URL="https://www.armbian.com/bugs"
ARMBIAN_PRETTY_NAME="Armbian 25.2.2 bullseye"
```
# 安装依赖
```bash
sudo apt install python3-flask cups python3-cups qpdf
```
# 特性
1. 可以选择CUPS服务器中配置好的任意打印机；
2. 可以正确识别CUPS中预设的纸张尺寸，默认尺寸与CUPS默认值保持一致；
3. 可以正确识别CUPS中预设的打印质量。
# 已知局限
仅支持打印PDF。
