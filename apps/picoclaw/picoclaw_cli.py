#!/usr/bin/env python3
"""PicoClaw CLI wrapper for NanoKVM screen app."""
import subprocess
import os
import json

BIN = "/usr/bin/picoclaw"
PROFILES_DIR = "/dev/shm/kvmapp/cua/profiles"


def _run(args, timeout=30):
    try:
        r = subprocess.run(
            [BIN] + args,
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", -1
    except Exception as e:
        return "", str(e), -1


def get_version():
    out, _, _ = _run(["version"])
    for part in out.split():
        if part and part[0].isdigit():
            return part
    return out or "?"


def get_status():
    out, err, code = _run(["status"])
    return out if out else err


def auth_status():
    out, err, code = _run(["auth", "status"])
    return out if code == 0 else (err or "Unknown")


def auth_login():
    out, err, code = _run(["auth", "login"], timeout=60)
    return code == 0, (out or err or "Done")


def auth_logout():
    out, err, code = _run(["auth", "logout"])
    return code == 0, (out or err or "Done")


def list_skills():
    out, err, code = _run(["skills"])
    if code != 0:
        return []
    lines = []
    for line in out.split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('=') and not line.startswith('NAME'):
            lines.append(line)
    return lines


def agent_message(message, model=None):
    args = ["agent", "-m", message]
    if model:
        args += ["--model", model]
    out, err, code = _run(args, timeout=90)
    return (out or err), code == 0


def run_onboard():
    out, err, code = _run(["onboard"], timeout=120)
    return code == 0, (out or err or "Done")


def start_gateway():
    try:
        subprocess.Popen(
            [BIN, "gateway"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True, "Gateway started"
    except Exception as e:
        return False, str(e)


def list_profiles():
    try:
        return [f.replace('.json', '') for f in os.listdir(PROFILES_DIR) if f.endswith('.json')]
    except:
        return ["claude", "gemini"]


def get_profile_model(profile):
    try:
        path = os.path.join(PROFILES_DIR, f"{profile}.json")
        with open(path) as f:
            return json.load(f).get("model_name", "")
    except:
        return ""
