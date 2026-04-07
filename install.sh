#!/usr/bin/env bash
# install.sh — Install Claude LED Matrix Status Bar on Raspberry Pi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="claude-status-bar"

echo "=== Claude LED Matrix Status Bar Installer ==="
echo "Install dir: $SCRIPT_DIR"
echo ""

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (sudo ./install.sh)"
    exit 1
fi

# Install system dependencies
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-dev python3-venv build-essential cython3 git

# Build rpi-rgb-led-matrix if not present
RPI_RGB_DIR="$(dirname "$SCRIPT_DIR")/rpi-rgb-led-matrix"
if [[ ! -d "$RPI_RGB_DIR" ]]; then
    echo "[2/7] Cloning and building rpi-rgb-led-matrix..."
    cd "$(dirname "$SCRIPT_DIR")"
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd rpi-rgb-led-matrix
    make -C lib
else
    echo "[2/7] rpi-rgb-led-matrix already present, skipping clone."
fi

# Set up Python venv
echo "[3/7] Setting up Python virtual environment..."
cd "$SCRIPT_DIR"
if [[ ! -d venv ]]; then
    python3 -m venv venv
fi
venv/bin/pip install -q pyyaml requests
venv/bin/pip install -q "$RPI_RGB_DIR"

# Symlink fonts
echo "[4/7] Linking fonts..."
ln -sfn "$RPI_RGB_DIR/fonts" "$SCRIPT_DIR/fonts"

# Set up config
echo "[5/7] Setting up config..."
if [[ ! -f "$SCRIPT_DIR/config.yaml" ]]; then
    cp "$SCRIPT_DIR/config.example.yaml" "$SCRIPT_DIR/config.yaml"
    echo "  Created config.yaml — edit it with your settings."
else
    echo "  config.yaml already exists, skipping."
fi

# Disable audio (conflicts with LED GPIO driver)
echo "[6/7] Disabling audio module..."
if ! grep -q 'dtparam=audio=off' /boot/firmware/config.txt 2>/dev/null; then
    echo 'dtparam=audio=off' >> /boot/firmware/config.txt
    echo "  Audio disabled in config.txt (reboot needed)."
fi
echo 'blacklist snd_bcm2835' > /etc/modprobe.d/alsa-blacklist.conf

# Install systemd service
echo "[7/7] Installing systemd service..."
cat > /etc/systemd/system/claude-status-bar.service << EOF
[Unit]
Description=Claude LED Matrix Status Bar
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/venv/bin/python3 -m src.main -c config.yaml
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $SCRIPT_DIR/config.yaml"
echo "     - Set rows/cols_per_panel to match your panels"
echo "     - Set gpio_mapping to match your wiring"
echo "     - Set a receiver token"
echo "     - Add your API projects (optional)"
echo "  2. Reboot (to disable audio module):"
echo "     sudo reboot"
echo "  3. Start the service:"
echo "     sudo systemctl start $SERVICE_NAME"
echo "  4. On your personal machine, set up the push client:"
echo "     python client/push_usage.py --host PI_IP --token YOUR_TOKEN"
echo "  5. Check status:"
echo "     sudo systemctl status $SERVICE_NAME"
echo "     sudo journalctl -u $SERVICE_NAME -f"
