# NanoKVM UserApp Suite

This repository contains a collection of high-quality touchscreen applications for the Sipeed NanoKVM Pro.

## 🚀 Quick Start (Installation)

To use these apps on your NanoKVM Pro:

1. **Copy the App Folders:** Transfer the desired app folder (e.g., `CLUCK`, `picoclaw`) to the `/userapp/` directory on your NanoKVM via SCP or SFTP.
   ```bash
   scp -r ./apps/CLUCK root@<your-kvm-ip>:/userapp/
   ```
2. **Install Dependencies:** Most apps require additional Python libraries. SSH into your NanoKVM and run:
   ```bash
   apt-get update && apt-get install -y libportaudio2 python3-pyaudio
   pip3 install yfinance vosk qrcode flask psutil
   ```
3. **Launch:** The apps will automatically appear in your NanoKVM touchscreen menu under the "UserApp" section.

---

## 📱 Applications

### 🐔 CLUCK (Farm Clock)
A quirky, interactive clock featuring animated farm life.
- **Features:** High-readability clock, interactive pecking, and unique "goofy zoom" jump-scares for all characters (Cow, Pig, Squirrel, Farmer, etc.).
- **Controls:** Rotate knob to move clock; Press to open settings; Long-press (2s) to exit.

### 🤖 PicoClaw (AI Agent)
A consolidated AI assistant interface with voice and chat capabilities.
- **Features:** Modern chat bubble UI, offline voice recognition (Vosk), and a QR Login server (port 8080) for easy API key setup.
- **Setup:** Scan the QR code in the "Login" tab to configure your AI provider on your phone.

### 📈 EQTY (Stock Tickers)
Real-time financial monitoring with high-speed rendering.
- **Features:** Live price updates for symbols like PSLV, CL=F, and CRF. High-performance sparklines.
- **Controls:** Rotate knob to switch symbols.

### 🛡️ SCRNSVR (Screensaver Manager)
A background daemon and UI to manage device idle states.
- **Features:** Automatically cycles through enabled apps when idle. Includes a live status dashboard.
- **System Service:** Can be run as a systemd service for persistence.

### 🔗 Tailcode (Tailscale Status)
Quick access to network connectivity information.
- **Features:** Optimized numpy rendering. Displays your Tailscale IP and a login QR code.

---

## 🎮 Global Controls
- **Knob Rotate:** Scroll menus or change values.
- **Knob Press:** Select, confirm, or toggle.
- **Knob Long-Press (2s):** Exit the current app and return to the main system menu.
