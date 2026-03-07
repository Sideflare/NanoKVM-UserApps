#!/usr/bin/env python3
"""
Screensaver daemon for NanoKVM Pro.
Monitors input idle time and cycles through enabled apps on the screen.

Usage:
  python3 daemon.py           # foreground (debug)
  python3 daemon.py --daemon  # daemonize
  python3 daemon.py --stop    # stop running daemon
  python3 daemon.py --status  # print status
"""
import os, sys, time, json, signal, struct, select, subprocess, random, mmap

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = "/etc/kvm/screensaver.json"
DAEMON_PID  = "/tmp/screensaver_daemon.pid"
PLAYING_PID = "/tmp/screensaver_playing.pid"
STATUS_FILE = "/tmp/screensaver_status.json"
LOG_FILE    = "/tmp/screensaver.log"
USERAPP_DIR = "/userapp"
INPUT_DEVS  = ['/dev/input/event0', '/dev/input/event1', '/dev/input/event2']

EV_FMT = 'llHHi'
EV_SZ  = struct.calcsize(EV_FMT)

SKIP_APPS = {'screensaver', 'readme.md'}


def default_cfg():
    return {
        "enabled": True,
        "idle_timeout": 300,
        "cycle_interval": 60,
        "order": "cycle",
        "blackout": False,
        "apps": {}
    }


def load_cfg():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in default_cfg().items():
            cfg.setdefault(k, v)
        return cfg
    except:
        return default_cfg()


def all_apps():
    apps = []
    try:
        for name in sorted(os.listdir(USERAPP_DIR)):
            path = os.path.join(USERAPP_DIR, name)
            if (os.path.isdir(path)
                    and os.path.exists(os.path.join(path, 'main.py'))
                    and name not in SKIP_APPS):
                apps.append(name)
    except:
        pass
    return apps


def enabled_apps(cfg):
    app_cfg = cfg.get("apps", {})
    return [a for a in all_apps() if app_cfg.get(a, False)]


def any_userapp_running():
    """Return True if a non-screensaver userapp main.py is running."""
    try:
        out = subprocess.check_output(
            ['pgrep', '-f', r'userapp/.*/main\.py'], text=True
        ).strip()
        # Exclude our own screensaver playing process
        pids = [int(p) for p in out.split() if p]
        playing = _read_pid(PLAYING_PID)
        return any(p != playing for p in pids)
    except:
        return False


def _read_pid(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except:
        return None


def kill_playing():
    pid = _read_pid(PLAYING_PID)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except:
            pass
        try:
            os.remove(PLAYING_PID)
        except:
            pass
    # Also kill any orphaned screensaver python3 processes
    try:
        subprocess.run(['pkill', '-f', r'screensaver.*blackout'], capture_output=True)
    except:
        pass


def launch_app(name):
    kill_playing()
    app_dir = os.path.join(USERAPP_DIR, name)
    try:
        proc = subprocess.Popen(
            ['python3', 'main.py'],
            cwd=app_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        with open(PLAYING_PID, 'w') as f:
            f.write(str(proc.pid))
        return proc
    except Exception as e:
        log(f"Failed to launch {name}: {e}")
        return None


def launch_blackout():
    kill_playing()
    script = (
        'import mmap,os,numpy as np;'
        'fd=os.open("/dev/fb0",os.O_RDWR);'
        'sz=172*320*2;mm=mmap.mmap(fd,sz,mmap.MAP_SHARED,mmap.PROT_WRITE);'
        'arr=np.frombuffer(mm,dtype="uint16").reshape(320,172);'
        'arr[:,:]=0;mm.close();os.close(fd);'
        'import time;time.sleep(86400)'
    )
    try:
        proc = subprocess.Popen(
            ['python3', '-c', script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        with open(PLAYING_PID, 'w') as f:
            f.write(str(proc.pid))
        return proc
    except:
        return None


def write_status(state, current=None, idle=0, next_switch=None):
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump({
                "state": state,
                "current": current,
                "idle_seconds": int(idle),
                "next_switch_in": int(next_switch) if next_switch else None,
                "timestamp": time.time()
            }, f)
    except:
        pass


def log(msg):
    try:
        print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)
    except:
        pass


def open_inputs():
    fds = []
    for path in INPUT_DEVS:
        try:
            fds.append(os.open(path, os.O_RDONLY | os.O_NONBLOCK))
        except:
            pass
    return fds


def drain_input(fds, timeout=0.15):
    """Returns True if any input event was seen."""
    if not fds:
        time.sleep(timeout)
        return False
    ready, _, _ = select.select(fds, [], [], timeout)
    for fd in ready:
        try:
            os.read(fd, EV_SZ * 16)
        except:
            pass
    return bool(ready)


def run():
    with open(DAEMON_PID, 'w') as f:
        f.write(str(os.getpid()))

    log(f"Screensaver daemon started (PID {os.getpid()})")
    fds = open_inputs()

    last_activity  = time.time()
    last_cfg_mtime = 0
    cfg            = load_cfg()
    app_index      = 0
    current_proc   = None
    current_name   = None
    started_at     = None

    def on_activity():
        nonlocal last_activity, current_proc, current_name, started_at
        last_activity = time.time()
        if current_proc is not None:
            log(f"Input detected — stopping screensaver ({current_name})")
            kill_playing()
            current_proc = None
            current_name = None
            started_at   = None

    try:
        while True:
            # Reload config if changed
            try:
                mt = os.path.getmtime(CONFIG_FILE)
                if mt != last_cfg_mtime:
                    cfg = load_cfg()
                    last_cfg_mtime = mt
                    log("Config reloaded")
            except:
                pass

            # Check input
            if drain_input(fds):
                on_activity()
                continue

            now  = time.time()
            idle = now - last_activity

            # If a user is actively in an app, stay idle
            if any_userapp_running():
                last_activity = now
                write_status("user_active", idle=0)
                continue

            if not cfg.get("enabled", True):
                write_status("disabled", idle=idle)
                continue

            # Check if current proc died naturally
            if current_proc is not None and current_proc.poll() is not None:
                log(f"Screensaver {current_name} exited naturally")
                current_proc = None
                current_name = None
                started_at   = None

            # Cycle to next app if interval elapsed
            if current_proc is not None:
                elapsed = now - started_at
                remaining = cfg.get("cycle_interval", 60) - elapsed
                write_status("playing", current_name, idle, remaining)
                if elapsed >= cfg.get("cycle_interval", 60):
                    log(f"Cycle interval elapsed — switching from {current_name}")
                    kill_playing()
                    current_proc = None
                    current_name = None
                    started_at   = None
                continue

            # Start screensaver if idle threshold reached
            if idle >= cfg.get("idle_timeout", 300):
                apps   = enabled_apps(cfg)
                pool   = apps + (["__blackout__"] if cfg.get("blackout") else [])

                if not pool:
                    write_status("idle_no_apps", idle=idle)
                    time.sleep(2)
                    continue

                if cfg.get("order", "cycle") == "random":
                    choice = random.choice(pool)
                else:
                    app_index = app_index % len(pool)
                    choice    = pool[app_index]
                    app_index += 1

                log(f"Idle {int(idle)}s — launching: {choice}")
                current_proc = launch_blackout() if choice == "__blackout__" else launch_app(choice)
                current_name = choice
                started_at   = time.time()
            else:
                remaining_idle = cfg.get("idle_timeout", 300) - idle
                write_status("waiting", idle=idle, next_switch=remaining_idle)

    except KeyboardInterrupt:
        pass
    finally:
        kill_playing()
        for fd in fds:
            try:
                os.close(fd)
            except:
                pass
        for f in [DAEMON_PID, STATUS_FILE]:
            try:
                os.remove(f)
            except:
                pass
        log("Screensaver daemon stopped")


def daemonize():
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    sys.stdin  = open('/dev/null', 'r')
    sys.stdout = open(LOG_FILE, 'a')
    sys.stderr = sys.stdout


if __name__ == '__main__':
    args = sys.argv[1:]

    if '--stop' in args:
        pid = _read_pid(DAEMON_PID)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"Stopped daemon (PID {pid})")
            except:
                print("Daemon not running")
        else:
            print("No daemon PID found")
        kill_playing()
        sys.exit(0)

    if '--status' in args:
        try:
            with open(STATUS_FILE) as f:
                print(json.dumps(json.load(f), indent=2))
        except:
            print("Daemon not running")
        sys.exit(0)

    if '--daemon' in args:
        daemonize()

    run()
