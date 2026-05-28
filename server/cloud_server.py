import asyncio
import hashlib
import json
import os
import secrets
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import websockets


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "cs_web"
DATA_DIR = ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"
HTTP_PORT = int(os.environ.get("CS_HTTP_PORT", "8000"))
WS_PORT = int(os.environ.get("CS_WS_PORT", "8765"))
PUBLIC_WS = os.environ.get("CS_PUBLIC_WS", str(WS_PORT))

sessions = {}
devices = {}
mobile_clients = {}
state_lock = threading.Lock()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return salt, digest.hex()


def verify_password(password, stored):
    salt = stored["salt"]
    _, digest = hash_password(password, salt)
    return secrets.compare_digest(digest, stored["hash"])


def load_users():
    DATA_DIR.mkdir(exist_ok=True)
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))

    username = os.environ.get("CS_ADMIN_USER", "admin")
    password = os.environ.get("CS_ADMIN_PASS", "admin123")
    salt, digest = hash_password(password)
    users = {username: {"salt": salt, "hash": digest}}
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已创建默认账号: {username} / {password}")
    print("正式部署请设置环境变量 CS_ADMIN_USER 和 CS_ADMIN_PASS 后重新创建 users.json。")
    return users


USERS = load_users()


def save_users():
    USERS_FILE.write_text(json.dumps(USERS, ensure_ascii=False, indent=2), encoding="utf-8")


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def public_device(device):
    return {
        "id": device["id"],
        "name": device["name"],
        "online": device["online"],
        "lastSeen": device["last_seen"],
    }


def user_devices(username):
    with state_lock:
        return [
            public_device(device)
            for device in devices.values()
            if device["username"] == username
        ]


async def notify_devices(username):
    payload = json.dumps({"type": "devices", "devices": user_devices(username)}, ensure_ascii=False)
    clients = list(mobile_clients.get(username, set()))
    for websocket in clients:
        try:
            await websocket.send(payload)
        except Exception:
            pass


def validate_token(token):
    with state_lock:
        session = sessions.get(token)
        if not session:
            return None
        session["last_seen"] = time.time()
        return session["username"]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/login", "/api/register"):
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        try:
            data = read_json(self)
            username = data.get("username", "").strip()
            password = data.get("password", "")
        except Exception:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "bad_json"})
            return

        if not username or len(username) < 3 or len(password) < 6:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_input"})
            return

        if path == "/api/register":
            with state_lock:
                if username in USERS:
                    json_response(self, HTTPStatus.CONFLICT, {"error": "user_exists"})
                    return
                salt, digest = hash_password(password)
                USERS[username] = {"salt": salt, "hash": digest}
                save_users()
            json_response(self, HTTPStatus.CREATED, {"username": username})
            return

        stored = USERS.get(username)
        if not stored or not verify_password(password, stored):
            json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_credentials"})
            return

        token = secrets.token_urlsafe(32)
        with state_lock:
            sessions[token] = {"username": username, "last_seen": time.time()}
        json_response(self, HTTPStatus.OK, {"token": token, "username": username})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/devices":
            token = parse_qs(parsed.query).get("token", [""])[0]
            username = validate_token(token)
            if not username:
                json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_token"})
                return
            json_response(self, HTTPStatus.OK, {"devices": user_devices(username)})
            return

        if parsed.path == "/config.js":
            payload = f"window.CS_WS_PORT = {json.dumps(PUBLIC_WS)};\n"
            body = payload.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


async def websocket_handler(websocket):
    parsed = urlparse(websocket.request.path)
    query = parse_qs(parsed.query)
    role = query.get("role", [""])[0]
    token = query.get("token", [""])[0]
    username = validate_token(token)
    if not username:
        await websocket.close(code=4001, reason="invalid token")
        return

    if role == "desktop":
        device_id = query.get("device_id", [""])[0] or secrets.token_hex(8)
        device_name = query.get("device_name", ["电脑端"])[0]
        with state_lock:
            devices[device_id] = {
                "id": device_id,
                "name": device_name,
                "username": username,
                "online": True,
                "last_seen": time.time(),
                "ws": websocket,
            }
        await notify_devices(username)
        try:
            async for message in websocket:
                with state_lock:
                    if device_id in devices:
                        devices[device_id]["last_seen"] = time.time()
                try:
                    data = json.loads(message)
                except Exception:
                    continue
                if data.get("type") == "inputFocus":
                    payload = json.dumps(
                        {"type": "inputFocus", "deviceId": device_id, "active": bool(data.get("active"))},
                        ensure_ascii=False,
                    )
                    clients = list(mobile_clients.get(username, set()))
                    for client in clients:
                        try:
                            await client.send(payload)
                        except Exception:
                            pass
        finally:
            with state_lock:
                if device_id in devices:
                    devices[device_id]["online"] = False
                    devices[device_id]["last_seen"] = time.time()
                    devices[device_id]["ws"] = None
            await notify_devices(username)
        return

    if role == "mobile":
        with state_lock:
            mobile_clients.setdefault(username, set()).add(websocket)
        await websocket.send(json.dumps({"type": "devices", "devices": user_devices(username)}, ensure_ascii=False))
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("type") != "command":
                    continue
                device_id = data.get("deviceId")
                with state_lock:
                    device = devices.get(device_id)
                    target = device.get("ws") if device and device["username"] == username and device["online"] else None
                if target:
                    await target.send(json.dumps({"type": "command", "command": data.get("command", {})}, ensure_ascii=False))
        finally:
            with state_lock:
                mobile_clients.get(username, set()).discard(websocket)
        return

    await websocket.close(code=4002, reason="invalid role")


def serve_http():
    httpd = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    print(f"HTTP 服务: http://0.0.0.0:{HTTP_PORT}")
    httpd.serve_forever()


async def main():
    threading.Thread(target=serve_http, daemon=True).start()
    print(f"WebSocket 服务: ws://0.0.0.0:{WS_PORT}/ws")
    async with websockets.serve(websocket_handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
