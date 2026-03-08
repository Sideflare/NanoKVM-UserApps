#!/bin/bash

# ==============================================================================
# NanoKVM UserApp Suite - Transparent Installer (v1.1.0)
# This script organizes the NanoKVM Pro app suite and configures services.
# ==============================================================================

set -e

echo "----------------------------------------------------------------"
echo "Starting NanoKVM UserApp Suite Installation..."
echo "----------------------------------------------------------------"

# Step 1: Define paths and check for root access
echo "[Step 1/5] Verifying environment..."
if [[ $EUID -ne 0 ]]; then
   echo "Error: This script must be run as root (use sudo)." 
   exit 1
fi

APP_DIR="/userapp"
SERVICE_PATH="/etc/systemd/system/screensaver.service"
PYTHON_BIN="/usr/local/bin/python3"

echo "  - Target directory: $APP_DIR"
echo "  - Python path: $PYTHON_BIN"

# Step 2: Install Python dependencies
echo "[Step 2/5] Installing Python dependencies from requirements.txt..."
if [ -f "requirements.txt" ]; then
    $PYTHON_BIN -m pip install --upgrade pip
    $PYTHON_BIN -m pip install -r requirements.txt
    echo "  - Dependencies installed successfully."
else
    echo "  - Skip: requirements.txt not found."
fi

# Step 3: Organize application folders
echo "[Step 3/5] Syncing application files..."
mkdir -p "$APP_DIR"
cp -rv apps/* "$APP_DIR/"
echo "  - Apps synchronized to $APP_DIR"

# Step 4: Configure the Screensaver/Dashboard Daemon
echo "[Step 4/5] Configuring the Screensaver (STAT Dashboard) service..."
cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=NanoKVM Screensaver Daemon
After=network.target

[Service]
Type=simple
ExecStart=$PYTHON_BIN $APP_DIR/SCRNSVR/daemon.py
Restart=always
RestartSec=10
User=root
WorkingDirectory=$APP_DIR/SCRNSVR

[Install]
WantedBy=multi-user.target
EOF

echo "  - Systemd service created at $SERVICE_PATH"
systemctl daemon-reload
systemctl enable screensaver.service
systemctl restart screensaver.service
echo "  - Screensaver service enabled and started."

# Step 5: Final system health check
echo "[Step 5/5] Performing final verification..."
if pgrep -f "daemon.py" > /dev/null; then
    echo "  - SUCCESS: Screensaver daemon is running."
else
    echo "  - WARNING: Screensaver daemon failed to start. Check 'journalctl -u screensaver'."
fi

echo "----------------------------------------------------------------"
echo "Installation Complete!"
echo "Your custom apps are ready in the OLED menu."
echo "----------------------------------------------------------------"
