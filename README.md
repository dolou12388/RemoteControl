# Cloud Phone Mouse Control

一个 C/S 架构的手机控制电脑工具：

- 服务器端负责账号、电脑在线状态和 WebSocket 消息中转。
- 手机端使用浏览器打开网页，登录后选择在线电脑进行控制。
- Windows 电脑端使用 C# WinForms 客户端登录上线，双击 exe 即可使用。

## 功能

- 手机触控板控制电脑鼠标移动
- 左键 / 中键 / 右键选择
- 单击、双击、长按拖动
- 双指滚动
- 放大 / 缩小按钮
- 复制、粘贴、撤销、保存、回车、Esc
- 手机网页注册 / 登录
- 手机显示电脑在线状态
- 电脑输入框获得焦点时，手机端显示远程输入栏

## 目录

```text
server/
  cloud_server.py              云端服务
  cs_web/                      手机网页端
  deploy.sh                    Linux 一键部署脚本
  control-mouse.service        systemd 服务模板
  nginx-control-mouse.conf     Nginx 反向代理模板
  requirements.txt             Python 依赖

desktop-windows/
  Program.cs                   Windows C# 客户端源码
  build.bat                    生成 Windows exe
```

## 一键部署服务器

把仓库上传到 Linux 服务器后执行：

```bash
cd server
DOMAIN=your-domain.com ADMIN_USER=admin ADMIN_PASS='your-password' bash deploy.sh
```

脚本会自动：

- 安装 Python、Nginx、rsync
- 创建 `/opt/control-mouse`
- 创建 Python 虚拟环境
- 安装依赖
- 写入 `.env`
- 创建并启动 `control-mouse.service`
- 如果设置了 `DOMAIN`，自动配置 Nginx 反向代理

默认端口：

- HTTP：`2345`
- WebSocket：`2346`

部署完成后访问：

```text
http://your-domain.com
```

需要 HTTPS 时，可以在服务器上安装 Certbot 后执行：

```bash
certbot --nginx -d your-domain.com
```

## 构建 Windows 电脑端 exe

在 Windows 上进入：

```bat
desktop-windows
```

双击 `build.bat`，会生成：

```text
ControlMouseDesktop.exe
```

用户只需要双击这个 exe，填写服务器地址、账号、密码，然后点“登录并上线”。

服务器地址示例：

```text
https://your-domain.com
```

如果没有 HTTPS，也可以用：

```text
http://服务器IP:2345
```

## 手机端使用

手机浏览器打开服务器地址，注册或登录账号，选择在线电脑即可控制。

手机浏览器可以通过“添加到主屏幕”把网页作为 App 使用。

## 生产注意

- 首次部署后请使用强密码。
- 推荐开启 HTTPS，否则部分浏览器功能会受限。
- 手机网页自动弹出输入法受浏览器限制；如果没有自动弹出，点一下远程输入栏即可。
