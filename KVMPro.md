# NanoKVM Pro — Project Reference (Restored 2026-03-08)

## Device Overview
- **Hardware:** Sipeed NanoKVM Pro (SG2002)
- **OS:** Ubuntu 22.04 LTS (Jammy) | Image v1.4.0 (2025-02-17)
- **Storage:** 64GB eMMC (System) + 64GB microSD (Data)
  - **Swap:** 8 GB Partition (Recommended on microSD)

## Current Project Structure (Cleaned & Git-Ready)
All custom user apps are consolidated into `NanoKVM-UserApps/apps/`.

| App | Version | Description |
|-----|---------|-------------|
| **CLUCK** | 1.1.0 | Farm Clock with "goofy zoom" jump-scares. |
| **picoclaw**| 1.1.0 | AI Agent (Chat/Voice/Vosk). Includes newer `main.py` (v1.3.0 logic). |
| **EQTY** | 1.1.0 | Fast-rendering Stock Ticker with sparklines. |
| **SCRNSVR** | 1.1.0 | Screensaver Manager & STAT dashboard daemon. |
| **tailcode**| 1.1.0 | Tailscale status and QR login. |

## Initial Device Setup (v1.4.0)
1. **Boot:** Insert the flashed microSD and power on. The OLED screen should display the IP address.
2. **Access:** 
   - **Web UI:** Navigate to `http://<device-ip>` (Default: `admin` / `admin`).
   - **SSH:** `ssh root@<device-ip>` (Default: `root` / `root`).
3. **Enable SSH:** In v1.4.0, SSH might be disabled by default. Enable it via the Web UI (Settings > Security) if needed.

## Post-Flash Installation Steps
To reinstall your custom apps to the fresh OS:
1. **Sync Apps:** 
   ```bash
   scp -r NanoKVM-UserApps/apps/* root@<device-ip>:/userapp/
   ```
2. **Setup Services:**
   - **Screensaver:** Re-enable `screensaver.service` in systemd.
   - **Cloudflare:** Re-install and link `cloudflared.service`.
   - **Tailscale:** Re-authenticate using the **Tailcode** app.

## Maintenance & Backups
- **Project Root:** `/Users/CL/.../Sipeed KVMPro/NanoKVM-UserApps/`
- **Backups:** Located in `backups/` (Git-ignored). Contains the raw `v1.4.0` OS image and history logs.
- **Git:** Use `git status` within `NanoKVM-UserApps` to track changes.
