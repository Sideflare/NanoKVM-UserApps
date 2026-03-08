# NanoKVM Pro — Project Reference (Final State 2026-03-07)

## Device Overview
- **Hardware:** Sipeed NanoKVM Pro (SG2002)
- **OS:** Ubuntu 22.04 LTS (Jammy) | Channel: Bleeding Edge
- **Storage:** 64GB eMMC (System) + 60GB microSD (Data)
  - **Swap:** 8 GB Partition on microSD (/dev/mmcblk1p1)
  - **Mounts:** /mnt/storage (Data), /mnt/storage/repos (Git), /mnt/storage/docs (Docs)

## Custom UserApp Suite (v1.1.0)
All apps support **Long-Press (2s)** on the knob to exit.

| App | Version | Description |
|-----|---------|-------------|
| **CLUCK** | 1.1.0 | Farm Clock with interactive "goofy zoom" jump-scares for all animals (Chickens, Cows, Pigs, Squirrels, Farmer, Farmer's Daughter). |
| **PicoClaw** | 1.1.0 | AI Agent with consolidated Chat/Voice. Features offline Vosk ASR, QR Login server (port 8080), and scrollable Setup. |
| **EQTY** | 1.1.0 | Stock Ticker (PSLV, CL=F, CRF, LEAV, INES). High-speed rendering with sparklines. |
| **SCRNSVR** | 1.1.0 | Screensaver Manager. Cycles enabled apps on idle. Includes fixed STAT dashboard. |
| **Tailcode** | 1.1.0 | Tailscale connectivity status and login QR code. |

## Connectivity & Services
- **Cloudflare:** Persistent tunnel running via systemd (`cloudflared.service`).
- **Tailscale:** Active on 100.126.2.79.
- **Login Server:** PicoClaw background login helper on port 8080.
- **Screensaver:** Background daemon running via systemd (`screensaver.service`).

## Maintenance Commands
- **Check Storage:** `df -h /mnt/storage`
- **Check Swap:** `swapon --show`
- **Restart Suite:** `pkill -f main.py`
