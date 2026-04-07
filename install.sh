#!/usr/bin/env bash
# install.sh — Install Claude LED Matrix Status Bar on Raspberry Pi
set -euo pipefail

INSTALL_DIR="/opt/claude-ledmatrix-status-bar"
RPI_RGB_DIR="/opt/rpi-rgb-led-matrix"
SERVICE_NAME="claude-status-bar"

echo "=== Claude LED Matrix Status Bar Installer ==="
echo ""

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root (sudo ./install.sh)"
    exit 1
fi

# Install system dependencies
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-dev git

# Build rpi-rgb-led-matrix if not present
if [[ ! -d "$RPI_RGB_DIR" ]]; then
    echo "[2/6] Building rpi-rgb-led-matrix..."
    cd /opt
    git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
    cd rpi-rgb-led-matrix
    make build-python PYTHON=$(which python3)
    make install-python PYTHON=$(which python3)
else
    echo "[2/6] rpi-rgb-led-matrix already installed, skipping."
fi

# Copy project files
echo "[3/6] Installing project files..."
mkdir -p "$INSTALL_DIR"
cp -r src/ "$INSTALL_DIR/"
cp requirements.txt config.example.yaml "$INSTALL_DIR/"

# Symlink fonts
echo "[4/6] Linking fonts..."
ln -sfn "$RPI_RGB_DIR/fonts" "$INSTALL_DIR/fonts"

# Install Python dependencies
echo "[5/6] Installing Python dependencies..."
pip3 install -r "$INSTALL_DIR/requirements.txt"

# Set up config
if [[ ! -f "$INSTALL_DIR/config.yaml" ]]; then
    cp "$INSTALL_DIR/config.example.yaml" "$INSTALL_DIR/config.yaml"
    echo "  Edit $INSTALL_DIR/config.yaml with your API project details."
else
    echo "  Config already exists, skipping."
fi

# Set up environment file
if [[ ! -f /etc/claude-status-bar.env ]]; then
    cp claude-status-bar.env.example /etc/claude-status-bar.env
    chmod 600 /etc/claude-status-bar.env
    echo ""
    echo "  IMPORTANT: Edit /etc/claude-status-bar.env with your keys."
    echo ""
fi

# Install and enable systemd service
echo "[6/6] Installing systemd service..."
cp claude-status-bar.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /opt/claude-ledmatrix-status-bar/config.yaml"
echo "     - Set gpio_mapping to match your wiring"
echo "     - Add your API projects with api_key_ids"
echo "  2. Edit /etc/claude-status-bar.env"
echo "     - Set ANTHROPIC_ADMIN_KEY to your admin API key"
echo "     - Set RECEIVER_TOKEN to a shared secret"
echo "  3. Start the service:"
echo "     - sudo systemctl start $SERVICE_NAME"
echo "  4. On your personal machine, set up the push client:"
echo "     - python client/push_usage.py --host PI_IP --token YOUR_TOKEN --loop"
echo "  5. Check status:"
echo "     - sudo systemctl status $SERVICE_NAME"
echo "     - sudo journalctl -u $SERVICE_NAME -f"
