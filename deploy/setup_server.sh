#!/bin/bash
# ArthaOS — Oracle Cloud ARM Ubuntu 22.04 server setup
# Run once as the opc (or ubuntu) user after first login
# Usage: bash setup_server.sh

set -e

ARTHAOS_DIR="$HOME/arthaos"
ARTHAOS_DATA="$ARTHAOS_DIR/data/statements"

echo "=== [1/8] System packages ==="
sudo apt-get update -y
sudo apt-get install -y \
  python3.11 python3.11-venv python3.11-dev \
  python3-pip build-essential curl git \
  libssl-dev libffi-dev libsqlite3-dev \
  chromium-browser nginx ufw \
  # For WhatsApp web (puppeteer/chromium)
  libnss3 libatk1.0-0 libatk-bridge2.0-0 \
  libcups2 libxkbcommon0 libxcomposite1 \
  libxdamage1 libxfixes3 libxrandr2 \
  libgbm1 libasound2

echo "=== [2/8] Node.js 20 ==="
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g pm2

echo "=== [3/8] Python venv ==="
python3.11 -m venv "$ARTHAOS_DIR/.venv"
source "$ARTHAOS_DIR/.venv/bin/activate"

echo "=== [4/8] Python dependencies ==="
pip install --upgrade pip
pip install -r "$ARTHAOS_DIR/requirements.txt"

echo "=== [5/8] Node dependencies (frontend) ==="
cd "$ARTHAOS_DIR/frontend"
npm install
npm run build   # build production bundle

echo "=== [6/8] Node dependencies (REA) ==="
cd "$ARTHAOS_DIR/REA"
npm install

echo "=== [7/8] Firewall rules ==="
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "=== [8/8] PM2 startup ==="
pm2 startup systemd -u "$USER" --hp "$HOME"
# NOTE: copy the 'sudo env PATH=...' command that pm2 prints and run it manually

echo ""
echo "Setup complete. Next:"
echo "  1. Run the pm2 startup sudo command printed above"
echo "  2. Copy your .env, gmail_token.json, Teller certs, and SQLite DB using deploy/sync.ps1"
echo "  3. Start services: pm2 start $ARTHAOS_DIR/deploy/ecosystem.linux.config.js"
echo "  4. Save: pm2 save"
echo "  5. Point nginx at the server's public IP (see deploy/nginx.conf)"
