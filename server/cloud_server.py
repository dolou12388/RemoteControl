import asyncio
import hashlib
import json
import logging
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
SESSION_TIMEOUT = int(os.environ.get("CS_SESSION_TIMEOUT", str(7 * 24 * 3600)))
LOGIN_RATE_LIMIT = int(os.environ.get("CS_LOGIN_RATE_LIMIT", "5"))
LOGIN_RATE_WINDOW = int(os.environ.get("CS_LOGIN_RATE_WINDOW", "300"))
LOGIN_LOCK_SECONDS = int(os.environ.get("CS_LOGIN_LOCK_SECONDS", "900"))
DEVICE_TIMEOUT = int(os.environ.get("CS_DEVICE_TIMEOUT", "60"))
START_TIME = time.time()

logging.basicConfig(
    level=os.environ.get("CS_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("control-mouse")

sessions = {}
devices = {}
mobile_clients = {}
login_attempts = {}
login_lockouts = {}
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
    logger.info("Created default account: %s", username)
    logger.info("Set CS_ADMIN_USER and CS_ADMIN_PASS before first production deploy.")
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


def client_ip(handler):
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return handler.client_address[0]


def validate_password(password):
    if len(password) < 8:
        return False, "weak_password"
    if not any(char.isupper() for char in password):
        return False, "weak_password"
    if not any(char.isdigit() for char in password):
        return False, "weak_password"
    return True, None


def cleanup_login_attempts(now=None):
    now = now or time.time()
    cutoff = now - LOGIN_RATE_WINDOW
    for ip, attempts in list(login_attempts.items()):
        kept = [timestamp for timestamp in attempts if timestamp >= cutoff]
        if kept:
            login_attempts[ip] = kept
        else:
            del login_attempts[ip]
    for key, locked_until in list(login_lockouts.items()):
        if locked_until <= now:
            del login_lockouts[key]


def login_key(username, ip):
    return f"{username.lower()}|{ip}"


def login_lock_remaining(username, ip):
    now = time.time()
    with state_lock:
        cleanup_login_attempts(now)
        locked_until = login_lockouts.get(login_key(username, ip), 0)
        return max(0, int(locked_until - now))


def check_login_rate_limit(ip):
    now = time.time()
    with state_lock:
        cleanup_login_attempts(now)
        return len(login_attempts.get(ip, [])) < LOGIN_RATE_LIMIT


def record_login_failure(ip):
    with state_lock:
        cleanup_login_attempts()
        login_attempts.setdefault(ip, []).append(time.time())


def record_account_login_failure(username, ip):
    now = time.time()
    key = login_key(username, ip)
    with state_lock:
        cleanup_login_attempts(now)
        attempts = login_attempts.setdefault(key, [])
        attempts.append(now)
        if len(attempts) >= LOGIN_RATE_LIMIT:
            login_lockouts[key] = now + LOGIN_LOCK_SECONDS
            login_attempts[key] = []


def clear_account_login_failures(username, ip):
    key = login_key(username, ip)
    with state_lock:
        login_attempts.pop(key, None)
        login_lockouts.pop(key, None)


def cleanup_sessions(now=None):
    now = now or time.time()
    expired = []
    with state_lock:
        for token, session in list(sessions.items()):
            if now - session["last_seen"] > SESSION_TIMEOUT:
                expired.append(token)
                del sessions[token]
    if expired:
        logger.info("Cleaned up %s expired sessions", len(expired))


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
        except Exception as exc:
            logger.warning("Failed to notify mobile client for %s: %s", username, exc)


def validate_token(token):
    now = time.time()
    with state_lock:
        session = sessions.get(token)
        if not session:
            return None
        if now - session["last_seen"] > SESSION_TIMEOUT:
            del sessions[token]
            return None
        session["last_seen"] = now
        return session["username"]


def validate_desktop_message(data):
    if not isinstance(data, dict):
        return False, "invalid_format"
    if data.get("type") == "heartbeat":
        return True, None
    if data.get("type") != "inputFocus":
        return False, "unknown_type"
    if not isinstance(data.get("active"), bool):
        return False, "invalid_active"
    return True, None


def validate_mobile_message(data):
    if not isinstance(data, dict):
        return False, "invalid_format"
    if data.get("type") != "command":
        return False, "unknown_type"
    if not isinstance(data.get("deviceId"), str) or not data["deviceId"]:
        return False, "invalid_device"
    command = data.get("command")
    if not isinstance(command, dict):
        return False, "invalid_command"

    command_type = command.get("type")
    allowed = {"move", "click", "doubleClick", "mouseDown", "mouseUp", "scroll", "zoom", "hotkey", "key", "text"}
    if command_type not in allowed:
        return False, "invalid_command_type"
    if command_type == "text" and len(str(command.get("value", ""))) > 2000:
        return False, "text_too_long"
    return True, None


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
        except Exception as exc:
            logger.warning("Bad JSON request from %s: %s", client_ip(self), exc)
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "bad_json"})
            return

        if not username or len(username) < 3:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_input"})
            return

        if path == "/api/register":
            is_valid_password, error = validate_password(password)
            if not is_valid_password:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": error})
                return
            with state_lock:
                if username in USERS:
                    json_response(self, HTTPStatus.CONFLICT, {"error": "user_exists"})
                    return
                salt, digest = hash_password(password)
                USERS[username] = {"salt": salt, "hash": digest}
                save_users()
            json_response(self, HTTPStatus.CREATED, {"username": username})
            return

        ip = client_ip(self)
        if not check_login_rate_limit(ip):
            logger.warning("Login rate limited for %s", ip)
            json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"})
            return
        locked_for = login_lock_remaining(username, ip)
        if locked_for > 0:
            logger.warning("Login locked for %s from %s", username, ip)
            json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"error": "account_locked", "retryAfter": locked_for})
            return

        stored = USERS.get(username)
        if not stored or not verify_password(password, stored):
            record_login_failure(ip)
            record_account_login_failure(username, ip)
            logger.warning("Failed login for user %s from %s", username, ip)
            json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_credentials"})
            return

        token = secrets.token_urlsafe(32)
        with state_lock:
            sessions[token] = {"username": username, "last_seen": time.time()}
        clear_account_login_failures(username, ip)
        json_response(self, HTTPStatus.OK, {"token": token, "username": username})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            with state_lock:
                payload = {
                    "status": "ok",
                    "devices": len(devices),
                    "onlineDevices": sum(1 for device in devices.values() if device["online"]),
                    "sessions": len(sessions),
                    "uptime": round(time.time() - START_TIME, 3),
                }
            json_response(self, HTTPStatus.OK, payload)
            return

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

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/devices":
            json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        query = parse_qs(parsed.query)
        token = query.get("token", [""])[0]
        device_id = query.get("id", [""])[0]
        username = validate_token(token)
        if not username:
            json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_token"})
            return
        if not device_id:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "missing_device"})
            return

        with state_lock:
            device = devices.get(device_id)
            if not device or device["username"] != username:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": "device_not_found"})
                return
            if device["online"]:
                json_response(self, HTTPStatus.CONFLICT, {"error": "device_online"})
                return
            del devices[device_id]

        json_response(self, HTTPStatus.OK, {"devices": user_devices(username)})

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
        logger.info("Desktop online: %s (%s)", device_name, device_id)
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
                except json.JSONDecodeError as exc:
                    logger.warning("Invalid JSON from desktop %s: %s", device_id, exc)
                    continue
                is_valid, error = validate_desktop_message(data)
                if not is_valid:
                    logger.warning("Invalid desktop message from %s: %s", device_id, error)
                    continue
                if data.get("type") == "heartbeat":
                    continue
                payload = json.dumps(
                    {"type": "inputFocus", "deviceId": device_id, "active": data["active"]},
                    ensure_ascii=False,
                )
                clients = list(mobile_clients.get(username, set()))
                for client in clients:
                    try:
                        await client.send(payload)
                    except Exception as exc:
                        logger.warning("Failed to forward input focus for %s: %s", device_id, exc)
        finally:
            with state_lock:
                if device_id in devices:
                    devices[device_id]["online"] = False
                    devices[device_id]["last_seen"] = time.time()
                    devices[device_id]["ws"] = None
            logger.info("Desktop offline: %s (%s)", device_name, device_id)
            await notify_devices(username)
        return

    if role == "mobile":
        logger.info("Mobile client connected for %s", username)
        with state_lock:
            mobile_clients.setdefault(username, set()).add(websocket)
        await websocket.send(json.dumps({"type": "devices", "devices": user_devices(username)}, ensure_ascii=False))
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError as exc:
                    logger.warning("Invalid JSON from mobile user %s: %s", username, exc)
                    continue
                is_valid, error = validate_mobile_message(data)
                if not is_valid:
                    logger.warning("Invalid mobile message from %s: %s", username, error)
                    continue

                device_id = data.get("deviceId")
                with state_lock:
                    device = devices.get(device_id)
                    target = device.get("ws") if device and device["username"] == username and device["online"] else None
                if target:
                    try:
                        await target.send(json.dumps({"type": "command", "command": data.get("command", {})}, ensure_ascii=False))
                    except Exception as exc:
                        logger.warning("Failed to forward command to %s: %s", device_id, exc)
        finally:
            with state_lock:
                mobile_clients.get(username, set()).discard(websocket)
            logger.info("Mobile client disconnected for %s", username)
        return

    await websocket.close(code=4002, reason="invalid role")


def serve_http():
    httpd = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    logger.info("HTTP server: http://0.0.0.0:%s", HTTP_PORT)
    httpd.serve_forever()


async def cleanup_stale_state():
    while True:
        await asyncio.sleep(30)
        cleanup_sessions()
        notify_users = set()
        now = time.time()
        with state_lock:
            for device_id, device in list(devices.items()):
                if device["online"] and now - device["last_seen"] > DEVICE_TIMEOUT:
                    logger.warning("Device timed out: %s", device_id)
                    device["online"] = False
                    device["ws"] = None
                    device["last_seen"] = now
                    notify_users.add(device["username"])
        for user in notify_users:
            await notify_devices(user)


async def main():
    threading.Thread(target=serve_http, daemon=True).start()
    logger.info("WebSocket server: ws://0.0.0.0:%s/ws", WS_PORT)
    asyncio.create_task(cleanup_stale_state())
    async with websockets.serve(websocket_handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
