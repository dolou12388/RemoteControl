#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/control-mouse}"
DOMAIN="${DOMAIN:-}"
HTTP_PORT="${HTTP_PORT:-2345}"
WS_PORT="${WS_PORT:-2346}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-change-this-password}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run as root."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

apt-get update
apt-get install -y python3 python3-venv python3-pip nginx rsync

if [[ -d "$APP_DIR" && -n "$(find "$APP_DIR" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
  BACKUP_DIR="$APP_DIR.backup.$(date +%Y%m%d%H%M%S)"
  cp -a "$APP_DIR" "$BACKUP_DIR"
  echo "Backup created: $BACKUP_DIR"
fi

mkdir -p "$APP_DIR"
rsync -a --delete \
  --exclude "data" \
  --exclude "venv" \
  --exclude ".env" \
  "$SCRIPT_DIR/" "$APP_DIR/"

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

cat > "$APP_DIR/.env" <<EOF_ENV
CS_HTTP_PORT=$HTTP_PORT
CS_WS_PORT=$WS_PORT
CS_PUBLIC_WS=same-origin
CS_ADMIN_USER=$ADMIN_USER
CS_ADMIN_PASS=$ADMIN_PASS
EOF_ENV
chmod 600 "$APP_DIR/.env"

cp "$APP_DIR/control-mouse.service" /etc/systemd/system/control-mouse.service
systemctl daemon-reload
systemctl enable control-mouse
systemctl restart control-mouse

if [[ -n "$DOMAIN" ]]; then
  DOMAIN_PATTERN="${DOMAIN//./\\.}"
  EXISTING_ENABLED_SITE="$(grep -Rsl "server_name .*${DOMAIN_PATTERN}" /etc/nginx/sites-enabled 2>/dev/null | head -n 1 || true)"
  if [[ -n "$EXISTING_ENABLED_SITE" ]]; then
    echo "Existing enabled Nginx site found for $DOMAIN: $EXISTING_ENABLED_SITE"
    echo "Leaving existing Nginx site in place."
  else
    sed \
      -e "s/server_name example.com;/server_name $DOMAIN;/" \
      -e "s/127.0.0.1:2345/127.0.0.1:$HTTP_PORT/g" \
      -e "s/127.0.0.1:2346/127.0.0.1:$WS_PORT/g" \
      "$APP_DIR/nginx-control-mouse.conf" > /etc/nginx/sites-available/control-mouse
    ln -sf /etc/nginx/sites-available/control-mouse /etc/nginx/sites-enabled/control-mouse
  fi
  nginx -t
  systemctl reload nginx
fi

systemctl --no-pager --full status control-mouse
echo "Deploy finished."
if [[ -n "$DOMAIN" ]]; then
  echo "Open: http://$DOMAIN"
else
  echo "Open: http://SERVER_IP:$HTTP_PORT"
fi
