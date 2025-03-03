# CUPS云打印页面
![cacf2c2400862bb5ba0024df92ffc81](https://github.com/user-attachments/assets/64792046-3593-4f7c-aaaa-0bb54eac7fa6)


## 测试平台
刷了Armbian当作CUPS打印服务器的N1盒子。
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
## 安装依赖
```bash
sudo apt install python3-flask cups python3-cups qpdf
```
## 设置权限（确保Web服务可以访问CUPS）
```bash
sudo usermod -a -G lpadmin $(whoami)
sudo systemctl restart cups
```
## 测试运行
```bash
python3 app.py
```
## 安装为系统服务
创建服务文件 `/etc/systemd/system/cupscloud.service`：
```bash
[Unit]
Description=Cloud Print Service
After=network.target

[Service]
User=你的用户名
WorkingDirectory=/home/你的用户名/cupscloud
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```
然后启用并启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable cupscloud
sudo systemctl start cupscloud
```
## 特性
1. 可以选择CUPS服务器中配置好的任意打印机(不能是RAW)；
2. 可以正确识别CUPS中预设的纸张尺寸，默认尺寸与CUPS默认值保持一致；
3. 可以正确识别CUPS中预设的打印质量;
4. 可以直观看到实际调用的lp打印命令；
5. 移动端适配。
# 已知局限
1. 仅支持打印PDF。PostScript应该也是支持的，不过没测试;
2. 测试EPSON M1128打印机，选择不同打印质量没有效果。
