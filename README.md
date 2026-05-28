# RemoteControl

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
