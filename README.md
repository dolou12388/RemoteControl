# RemoteControl

自托管的手机控制电脑工具。把手机变成 Windows 电脑的触控板、滚轮、快捷键面板和远程输入法。

> 这是一个 C/S 架构的手机控制电脑鼠标项目。服务器负责账号、设备在线状态和 WebSocket 消息中转；手机端使用浏览器访问网页；Windows 电脑端双击 exe 登录上线。

## 为什么做这个项目

- **手机端不需要安装原生 App**：打开网页即可使用，也可以添加到手机桌面。
- **电脑端简单**：Windows 端是 C# WinForms 程序，用户双击 exe 即可打开。
- **自己部署，自己掌控**：服务端部署在你自己的 VPS 上，不依赖第三方远控平台。
- **账号隔离设备**：手机端和电脑端使用同一个账号登录，手机只能看到该账号下的在线电脑。
- **更贴近日常操作**：支持鼠标移动、点击、双击、拖动、滚动、缩放、快捷键和远程文字输入。

## 功能特性

- 手机触控板控制 Windows 鼠标移动
- 支持左键 / 中键 / 右键选择
- 支持单击、双击、长按拖动
- 支持双指滚动
- 支持放大 / 缩小按钮
- 常用快捷键：复制、粘贴、撤销、保存、回车、Esc
- 手机网页端支持注册 / 登录
- 手机端显示当前账号下的在线电脑
- 电脑输入框获得焦点时，手机端显示远程输入栏
- Linux 服务器一键部署，支持 systemd 和 Nginx 反向代理

## 架构说明

```text
手机浏览器
  |
  | HTTPS / WSS
  v
自托管服务器
  - 登录 / 注册
  - 电脑在线状态
  - WebSocket 消息中转
  |
  | WSS
  v
Windows 电脑端
  - 接收鼠标 / 键盘命令
  - 上报当前是否聚焦输入框
```

服务端只负责在已登录的手机端和电脑端之间转发命令，不提供屏幕画面传输。

## 项目目录

```text
server/
  cloud_server.py              Python 云端中转服务
  cs_web/                      手机网页端
  deploy.sh                    Linux 一键部署脚本
  control-mouse.service        systemd 服务模板
  nginx-control-mouse.conf     Nginx 反向代理模板
  requirements.txt             Python 依赖

desktop-windows/
  Program.cs                   Windows C# 电脑端源码
  build.bat                    生成 ControlMouseDesktop.exe
```

## 快速部署服务器

在一台全新的 Ubuntu/Debian 服务器上执行：

```bash
git clone https://github.com/dolou12388/RemoteControl.git
cd RemoteControl/server
DOMAIN=your-domain.com ADMIN_USER=admin ADMIN_PASS='use-a-long-random-password' bash deploy.sh
```

脚本会自动安装依赖、创建 `/opt/control-mouse`、配置 systemd、启动服务，并在提供 `DOMAIN` 时自动配置 Nginx 反向代理。

默认端口：

- HTTP：`2345`
- WebSocket：`2346`

部署完成后访问：

```text
http://your-domain.com
```

## 开启 HTTPS

公网部署强烈建议开启 HTTPS。

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

开启后使用：

```text
https://your-domain.com
```

## 构建 Windows 电脑端

在 Windows 上进入：

```bat
cd desktop-windows
build.bat
```

会生成：

```text
ControlMouseDesktop.exe
```

双击 exe，填写服务器地址、账号、密码和电脑名称，然后点击“登录并上线”。

服务器地址示例：

```text
https://your-domain.com
http://SERVER_IP:2345
```

## 手机端使用

手机浏览器打开服务器地址，登录账号，选择在线电脑即可开始控制。

也可以通过浏览器菜单把网页“添加到主屏幕”，像轻量 App 一样使用。

## 安全部署清单

在把服务暴露到公网之前，请至少确认：

- 使用足够长的随机密码。
- 开启 HTTPS。
- 不要把 `server/.env` 和 `server/data/` 上传到 Git。
- 不要复用其他网站或服务的密码。
- 优先使用独立的低权限 VPS。
- 保持服务器系统和依赖更新。
- 使用 Nginx + HTTPS 时，公网只开放 `80`、`443`、`22` 等必要端口。
- 不要在自己的账号下运行来源不可信的电脑端客户端。

更多说明见 [SECURITY.md](SECURITY.md)。

## 当前限制

- 这不是屏幕共享工具，只发送鼠标、键盘和文字输入命令。
- 手机浏览器可能会限制网页自动弹出输入法；如果输入栏出现但键盘没弹出，手动点一下输入栏即可。
- 当前电脑端主要面向 Windows。

## 后续计划

- 发布预编译 Windows exe
- 配对码或邀请链接
- 设备管理页面
- 登录频率限制和锁定
- Docker 部署
- Windows 托盘图标和开机自启

## Star 支持

如果这个项目帮到了你，欢迎点一个 star。它能帮助更多人发现这个轻量、自托管的手机控制电脑方案。

## 许可证

MIT

---

## English Version

Self-hosted phone-to-PC remote mouse control. Use your phone as a touchpad, scroll wheel, shortcut panel, and remote text input for your Windows computer.

> 手机控制电脑鼠标的 C/S 工具。服务器负责账号和消息中转，手机打开网页，Windows 电脑端双击 exe 登录上线。

## Why This Project

- **No app store required**: the phone client is a mobile web app.
- **Simple desktop client**: the Windows side is a C# WinForms app that users can open by double-clicking an exe.
- **Self-hosted relay**: deploy the server on your own VPS instead of relying on a third-party control service.
- **Account based pairing**: phone and desktop log in with the same account, and the phone sees only that account's online computers.
- **Designed for practical control**: mouse movement, click, double click, drag, scroll, zoom, shortcuts, and remote text input.

## Features

- Phone touchpad controls Windows mouse movement
- Left / middle / right mouse button selection
- Tap, double tap, long-press drag
- Two-finger scrolling
- Zoom in / zoom out buttons
- Common shortcuts: copy, paste, undo, save, Enter, Esc
- Mobile web login and registration
- Online desktop list on the phone
- Remote text input: when a text field is focused on the PC, the phone shows an input bar
- One-command Linux deployment with systemd and optional Nginx reverse proxy

## Architecture

```text
Phone browser
  |
  | HTTPS / WSS
  v
Self-hosted server
  - login / register
  - device presence
  - WebSocket relay
  |
  | WSS
  v
Windows desktop client
  - receives mouse / keyboard commands
  - sends text-input focus status
```

The server relays commands between authenticated phone and desktop clients. It does not provide screen streaming.

## Repository Layout

```text
server/
  cloud_server.py              Python relay server
  cs_web/                      Mobile web client
  deploy.sh                    One-command Linux deploy script
  control-mouse.service        systemd service template
  nginx-control-mouse.conf     Nginx reverse proxy template
  requirements.txt             Python dependencies

desktop-windows/
  Program.cs                   Windows C# desktop client
  build.bat                    Builds ControlMouseDesktop.exe
```

## Quick Deploy

On a fresh Ubuntu/Debian server:

```bash
git clone https://github.com/dolou12388/RemoteControl.git
cd RemoteControl/server
DOMAIN=your-domain.com ADMIN_USER=admin ADMIN_PASS='use-a-long-random-password' bash deploy.sh
```

The script installs dependencies, creates `/opt/control-mouse`, configures systemd, starts the service, and configures Nginx when `DOMAIN` is provided.

Default ports:

- HTTP: `2345`
- WebSocket: `2346`

Open:

```text
http://your-domain.com
```

## Enable HTTPS

HTTPS is strongly recommended for public deployment.

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d your-domain.com
```

Then use:

```text
https://your-domain.com
```

## Build the Windows Desktop Client

On Windows:

```bat
cd desktop-windows
build.bat
```

This creates:

```text
ControlMouseDesktop.exe
```

Open the exe, enter your server URL, username, password, and computer name, then click **Login and Online**.

Server URL examples:

```text
https://your-domain.com
http://SERVER_IP:2345
```

## Use on Phone

Open the server URL in your phone browser, log in, select an online computer, and start controlling it.

You can add the page to your home screen from the browser menu to use it like a lightweight app.

## Safe Deployment Checklist

Before exposing the service to the public internet:

- Use a long random admin password.
- Enable HTTPS.
- Keep `server/.env` and `server/data/` out of Git.
- Do not reuse passwords from other services.
- Prefer a dedicated low-privilege VPS.
- Keep the server updated.
- Restrict inbound ports to `80`, `443`, and `22` when using Nginx + HTTPS.
- Avoid running untrusted desktop clients under your account.

See [SECURITY.md](SECURITY.md) for more notes.

## Limitations

- This is not a screen-sharing tool. It sends mouse, keyboard, and text commands only.
- Browser rules may block automatic mobile keyboard popup. If the input bar appears but the keyboard does not open, tap the input bar once.
- The desktop client currently targets Windows.

## Roadmap Ideas

- Release prebuilt Windows binaries
- Pairing codes or invite links
- Device management page
- Optional rate limiting and lockout
- Docker deployment
- Tray icon and auto-start for the Windows client

## Star The Project

If this project helps you, please consider giving it a star. It helps others discover a small self-hosted alternative for phone-to-PC control.

## License

MIT
