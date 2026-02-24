#!/usr/bin/env python3
"""
data_collector.py  -  Digital Twin data logger per robot Niryo NED2

Architettura a tre thread per campionamento ad alta frequenza (≥ 50 ms):

  Thread A – Sampler (priorità alta)
    • Si connette al daemon pyniryo in esecuzione sul robot via TCP socket
    • Legge dati robot + timestamp monotonic ogni <interval> secondi
    • Mette ogni campione in una queue.Queue in RAM (zero I/O disco)

  Thread B – Writer (priorità normale)
    • Drena la queue ogni ~0.5 s (batch write)
    • Scrive su CSV con flush periodico (non continuo)

  Thread C – SysMetrics (asincrono, ogni ~1 s)
    • Legge metriche OS del robot via SSH (CPU, RAM, load, disk)
    • Aggiorna un dizionario condiviso thread-safe

  Daemon sul robot (ROBOT_DAEMON_SCRIPT):
    • Uploadato su /tmp/_dc_daemon.py all'avvio, poi lanciato in background
    • Apre connessione pyniryo una sola volta, poi serve richieste TCP sulla
      porta DAEMON_PORT (default 9876)
    • Protocollo: invia "GET\\n" → risponde con una riga JSON

Uso rapido:
    python3 data_collector.py --interval 0.05 --output robot_data.csv

Argomenti completi:
    python3 data_collector.py --help
"""

import argparse
import csv
import datetime
import json
import logging
import os
import queue
import socket
import sys
import threading
import time
from typing import Dict, Optional

try:
    import paramiko
except ImportError:
    paramiko = None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGER = logging.getLogger("data_collector")
LOGGER.setLevel(logging.INFO)
_h = logging.StreamHandler()
_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
LOGGER.addHandler(_h)

# ---------------------------------------------------------------------------
# Porta TCP del daemon pyniryo sul robot
# ---------------------------------------------------------------------------

DAEMON_PORT = 9876
DAEMON_PATH = "/tmp/_dc_daemon.py"

# ---------------------------------------------------------------------------
# Script daemon da uploadare e avviare sul robot (una volta sola).
# Resta in esecuzione, apre pyniryo una volta, poi serve ogni "GET\n"
# con una riga JSON di dati freschissimi.
# ---------------------------------------------------------------------------

ROBOT_DAEMON_SCRIPT = r"""
import sys, json, socket, threading, time
sys.path.insert(0, '/home/niryo/catkin_ws_venv/lib/python3.8/site-packages')

PORT = 9876
HW_REFRESH_S = 2.0   # get_hardware_status() è lento: aggiornato ogni 2 s
PUSH_HZ = 50         # frequenza di push verso i client (50 Hz = 20 ms)

from pyniryo import NiryoRobot

# ---- cache condivisa ----
cache_lock = threading.Lock()
cache = {'ok': False, 'error': 'starting'}
cache_event = threading.Event()   # segnala ogni nuovo campione

def connect():
    while True:
        try:
            r = NiryoRobot('127.0.0.1')
            print('[daemon] pyniryo connesso', flush=True)
            return r
        except Exception as e:
            print(f'[daemon] connect error: {e}, retry in 2s', flush=True)
            time.sleep(2)

robot = connect()

# ---- Thread poller: legge pose+joints il più veloce possibile,
#      hardware_status ogni HW_REFRESH_S ----
def poller():
    last_hw = {'motors_temp': [], 'rpi_temp': None}
    last_hw_time = 0.0
    while True:
        t0 = time.monotonic()
        try:
            pose   = robot.get_pose()
            joints = robot.get_joints()
            if t0 - last_hw_time >= HW_REFRESH_S:
                hw = robot.get_hardware_status()
                last_hw = {
                    'motors_temp': list(hw.motors_temperature) if hasattr(hw, 'motors_temperature') else [],
                    'rpi_temp':    hw.rpi_temperature if hasattr(hw, 'rpi_temperature') else None,
                }
                last_hw_time = t0
            snap = {
                'ok': True,
                'x': pose.x, 'y': pose.y, 'z': pose.z,
                'roll': pose.roll, 'pitch': pose.pitch, 'yaw': pose.yaw,
                'joints': list(joints),
                'motors_temp': last_hw['motors_temp'],
                'rpi_temp':    last_hw['rpi_temp'],
            }
        except Exception as e:
            snap = {'ok': False, 'error': str(e)}
        with cache_lock:
            cache.update(snap)
        cache_event.set()
        cache_event.clear()
        elapsed = time.monotonic() - t0
        sleep_t = (1.0 / PUSH_HZ) - elapsed
        if sleep_t > 0:
            time.sleep(sleep_t)

threading.Thread(target=poller, daemon=True).start()

# ---- attendi il primo dato valido (max 15 s) ----
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    with cache_lock:
        ready = cache.get('ok', False)
    if ready:
        break
    time.sleep(0.1)
print('[daemon] in ascolto su :' + str(PORT), flush=True)

# ---- registry dei client in modalità STREAM ----
clients_lock = threading.Lock()
stream_clients = set()   # set di socket

def push_loop():
    # Invia la cache a tutti i client in stream ogni 1/PUSH_HZ secondi.
    interval = 1.0 / PUSH_HZ
    while True:
        t0 = time.monotonic()
        with cache_lock:
            line = (json.dumps(cache) + '\n').encode()
        dead = set()
        with clients_lock:
            clients = list(stream_clients)
        for c in clients:
            try:
                c.sendall(line)
            except Exception:
                dead.add(c)
        if dead:
            with clients_lock:
                stream_clients.difference_update(dead)
            for c in dead:
                try: c.close()
                except: pass
        elapsed = time.monotonic() - t0
        rem = interval - elapsed
        if rem > 0:
            time.sleep(rem)

threading.Thread(target=push_loop, daemon=True).start()

# ---- Server TCP ----
def handle(conn):
    # Protocollo:
    #   client invia "STREAM" -> il server pushera JSON a ~PUSH_HZ Hz
    #   client invia "GET"    -> risposta singola (compatibilita)
    #   client invia "QUIT"   -> chiude
    try:
        f = conn.makefile('r')
        for line in f:
            cmd = line.strip()
            if cmd == 'STREAM':
                with clients_lock:
                    stream_clients.add(conn)
                # resta in attesa di QUIT senza leggere altro
                for line2 in f:
                    if line2.strip() == 'QUIT':
                        break
                with clients_lock:
                    stream_clients.discard(conn)
                break
            elif cmd in ('GET', ''):
                with cache_lock:
                    snap = dict(cache)
                conn.sendall((json.dumps(snap) + '\n').encode())
            elif cmd == 'QUIT':
                break
    except Exception:
        pass
    finally:
        with clients_lock:
            stream_clients.discard(conn)
        try: conn.close()
        except: pass

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', PORT))
srv.listen(20)
while True:
    try:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()
    except Exception:
        pass
"""

# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------

def open_ssh(ip: str, username: str, password: str,
             key_filename: Optional[str], timeout: float = 10.0):
    if paramiko is None:
        LOGGER.error("paramiko non installato. Esegui: pip install paramiko")
        return None
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, username=username, password=password,
                       key_filename=key_filename, timeout=timeout)
        LOGGER.info("SSH connesso a %s@%s", username, ip)
        return client
    except Exception as e:
        LOGGER.error("SSH connect fallito: %s", e)
        return None


def ssh_exec(client, cmd: str, timeout: float = 20.0) -> str:
    try:
        _, stdout, _ = client.exec_command(cmd, timeout=timeout)
        return stdout.read().decode("utf-8", errors="ignore").strip()
    except Exception as e:
        LOGGER.debug("ssh_exec error: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Daemon management
# ---------------------------------------------------------------------------

def upload_daemon(client) -> bool:
    """Carica lo script daemon sul robot."""
    # usa printf per evitare problemi con heredoc e caratteri speciali
    script_b64 = __import__('base64').b64encode(
        ROBOT_DAEMON_SCRIPT.encode()).decode()
    cmd = f"python3 -c \"import base64; open('{DAEMON_PATH}','wb').write(base64.b64decode('{script_b64}'))\""
    ssh_exec(client, cmd, timeout=10.0)
    check = ssh_exec(client, f"test -f {DAEMON_PATH} && echo ok", timeout=5.0)
    return check.strip() == "ok"


def start_daemon(client, port: int = DAEMON_PORT):
    """Uccide eventuali istanze precedenti e avvia il daemon in background."""
    ssh_exec(client, f"pkill -f '{DAEMON_PATH}' 2>/dev/null || true", timeout=5.0)
    time.sleep(0.5)
    client.exec_command(
        f"nohup python3 {DAEMON_PATH} > /tmp/_dc_daemon.log 2>&1 &",
    )
    # Aspetta che il daemon sia pronto (max 10 s)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        time.sleep(0.5)
        log = ssh_exec(client, "tail -3 /tmp/_dc_daemon.log 2>/dev/null", timeout=5.0)
        if f"in ascolto su :{port}" in log or "pyniryo connesso" in log:
            LOGGER.info("Daemon avviato sul robot (porta %d)", port)
            return True
    LOGGER.warning("Daemon avviato (in attesa timeout), log: %s",
                   ssh_exec(client, "cat /tmp/_dc_daemon.log", timeout=5.0)[-300:])
    return True  # procedi comunque


# ---------------------------------------------------------------------------
# TCP socket al daemon – modalità STREAM (push da robot → client)
# ---------------------------------------------------------------------------

class DaemonClient:
    """
    Si connette al daemon, invia STREAM e riceve righe JSON in push.
    Un thread interno legge lo stream e aggiorna una cache locale.
    Thread A chiama get() che ritorna istantaneamente dalla cache (zero RTT).
    """

    def __init__(self, ip: str, port: int = DAEMON_PORT, timeout: float = 5.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._cache: dict = {"ok": False, "error": "not connected"}
        self._cache_lock = threading.Lock()
        self._reader: Optional[threading.Thread] = None
        self._running = False

    def connect(self, retries: int = 10, delay: float = 1.0) -> bool:
        for attempt in range(retries):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                s.connect((self.ip, self.port))
                s.settimeout(None)          # modalità bloccante per readline
                self._sock = s
                # Attiva modalità STREAM
                s.sendall(b"STREAM\n")
                self._running = True
                self._reader = threading.Thread(
                    target=self._read_loop, name="DaemonReader", daemon=True)
                self._reader.start()
                LOGGER.info("Connesso al daemon robot %s:%d (modalità STREAM)", self.ip, self.port)
                return True
            except Exception as e:
                LOGGER.debug("DaemonClient connect attempt %d: %s", attempt + 1, e)
                time.sleep(delay)
        LOGGER.error("Impossibile connettersi al daemon dopo %d tentativi", retries)
        return False

    def _read_loop(self):
        """Thread interno: legge righe JSON dallo stream e aggiorna la cache."""
        try:
            f = self._sock.makefile('r')
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    with self._cache_lock:
                        self._cache = data
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            self._running = False

    def get(self) -> dict:
        """Ritorna l'ultimo dato ricevuto dal daemon (non-bloccante)."""
        with self._cache_lock:
            return dict(self._cache)

    def close(self):
        self._running = False
        try:
            if self._sock:
                self._sock.sendall(b"QUIT\n")
                self._sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Thread C – Metriche di sistema (SSH, ogni ~sys_interval secondi)
# ---------------------------------------------------------------------------

class SysMetricsThread(threading.Thread):
    """Legge metriche OS del robot via SSH in background.
    Aggiorna self.latest (dict) in modo thread-safe.
    """

    def __init__(self, ssh_client, interval: float = 1.0):
        super().__init__(name="SysMetrics", daemon=True)
        self._client = ssh_client
        self._interval = interval
        self.latest: Dict = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def get(self) -> Dict:
        with self._lock:
            return dict(self.latest)

    def _read(self) -> Dict:
        res = {}
        client = self._client

        # Load average
        la = ssh_exec(client, "cat /proc/loadavg").split()
        if len(la) >= 3:
            res["load1"]  = float(la[0])
            res["load5"]  = float(la[1])
            res["load15"] = float(la[2])

        # Memoria
        for line in ssh_exec(client, "free -b").splitlines():
            parts = line.split()
            if parts and parts[0].lower().startswith("mem"):
                try:
                    res["mem_total_B"] = int(parts[1])
                    res["mem_used_B"]  = int(parts[2])
                    res["mem_free_B"]  = int(parts[3])
                except (IndexError, ValueError):
                    pass
                break

        # CPU (due letture /proc/stat a ~300 ms)
        def _stat():
            line = ssh_exec(client, "head -1 /proc/stat")
            parts = line.split()
            return [int(p) for p in parts[1:]] if len(parts) > 1 else []

        s1 = _stat()
        time.sleep(0.3)
        s2 = _stat()
        if s1 and s2 and len(s1) == len(s2):
            dtotal = sum(s2) - sum(s1)
            didle  = s2[3] - s1[3]
            if dtotal > 0:
                res["cpu_percent"] = round(100.0 * (dtotal - didle) / dtotal, 2)

        # Disco
        df = ssh_exec(client, "df -B1 / | tail -n1").split()
        if len(df) >= 4:
            try:
                res["disk_total_B"] = int(df[1])
                res["disk_used_B"]  = int(df[2])
            except ValueError:
                pass

        return res

    def run(self):
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                data = self._read()
                with self._lock:
                    self.latest = data
            except Exception as e:
                LOGGER.debug("SysMetrics error: %s", e)
            elapsed = time.monotonic() - t0
            remaining = self._interval - elapsed
            if remaining > 0:
                self._stop.wait(remaining)


# ---------------------------------------------------------------------------
# Thread B – Writer (drena la queue, scrive su disco a batch ogni ~0.5 s)
# ---------------------------------------------------------------------------

class WriterThread(threading.Thread):
    """Legge campioni dalla queue e li scrive su CSV in batch."""

    FLUSH_INTERVAL = 0.5  # secondi tra uno svuotamento e l'altro

    def __init__(self, out_csv: str, sample_queue: "queue.Queue[Optional[dict]]"):
        super().__init__(name="Writer", daemon=True)
        self._path = out_csv
        self._q = sample_queue
        self._stop = threading.Event()
        self.written = 0

    def stop(self):
        self._stop.set()

    def run(self):
        with open(self._path, "a", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
            last_flush = time.monotonic()
            while not self._stop.is_set():
                batch = []
                # Raccoglie tutto ciò che c'è in queue, max 0.5 s di attesa
                deadline = time.monotonic() + self.FLUSH_INTERVAL
                while time.monotonic() < deadline:
                    try:
                        item = self._q.get(timeout=max(0.001, deadline - time.monotonic()))
                        if item is None:          # sentinel di stop
                            self._stop.set()
                            break
                        batch.append(item)
                        self._q.task_done()
                    except queue.Empty:
                        break

                if batch:
                    writer.writerows(batch)
                    self.written += len(batch)

                # flush su disco ogni FLUSH_INTERVAL
                now = time.monotonic()
                if now - last_flush >= self.FLUSH_INTERVAL:
                    fh.flush()
                    os.fsync(fh.fileno())
                    last_flush = now

            # Flush finale di eventuali residui
            try:
                while True:
                    item = self._q.get_nowait()
                    if item is not None:
                        writer.writerow(item)
                        self.written += 1
            except queue.Empty:
                pass
            fh.flush()


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------

def iso_ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(
        timespec="microseconds")


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "timestamp",
    "x_m", "y_m", "z_m", "roll_rad", "pitch_rad", "yaw_rad",
    "j1_rad", "j2_rad", "j3_rad", "j4_rad", "j5_rad", "j6_rad",
    "temp_m1_C", "temp_m2_C", "temp_m3_C", "temp_m4_C",
    "temp_m5_C", "temp_m6_C", "temp_m7_C", "temp_m8_C",
    "rpi_temp_C",
    "cpu_percent", "mem_total_B", "mem_used_B", "mem_free_B",
    "load1", "load5", "load15", "disk_total_B", "disk_used_B",
]


def ensure_header(path: str):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


# ---------------------------------------------------------------------------
# Costruzione riga da dati robot + metriche sistema
# ---------------------------------------------------------------------------

def build_row(robot: dict, sys_m: dict) -> dict:
    row: dict = {k: "" for k in FIELDNAMES}
    row["timestamp"] = iso_ts()

    if robot.get("ok"):
        row["x_m"]       = robot.get("x",     "")
        row["y_m"]       = robot.get("y",     "")
        row["z_m"]       = robot.get("z",     "")
        row["roll_rad"]  = robot.get("roll",  "")
        row["pitch_rad"] = robot.get("pitch", "")
        row["yaw_rad"]   = robot.get("yaw",   "")
        joints = robot.get("joints") or []
        for i, k in enumerate(["j1_rad", "j2_rad", "j3_rad",
                                "j4_rad", "j5_rad", "j6_rad"]):
            if i < len(joints):
                row[k] = joints[i]
        temps = robot.get("motors_temp") or []
        for i, k in enumerate(["temp_m1_C", "temp_m2_C", "temp_m3_C", "temp_m4_C",
                                "temp_m5_C", "temp_m6_C", "temp_m7_C", "temp_m8_C"]):
            if i < len(temps):
                row[k] = temps[i]
        row["rpi_temp_C"] = robot.get("rpi_temp", "")

    row["cpu_percent"]  = sys_m.get("cpu_percent",  "")
    row["mem_total_B"]  = sys_m.get("mem_total_B",  "")
    row["mem_used_B"]   = sys_m.get("mem_used_B",   "")
    row["mem_free_B"]   = sys_m.get("mem_free_B",   "")
    row["load1"]        = sys_m.get("load1",  "")
    row["load5"]        = sys_m.get("load5",  "")
    row["load15"]       = sys_m.get("load15", "")
    row["disk_total_B"] = sys_m.get("disk_total_B", "")
    row["disk_used_B"]  = sys_m.get("disk_used_B",  "")
    return row


# ---------------------------------------------------------------------------
# Loop principale (orchestratore Thread A + B + C)
# ---------------------------------------------------------------------------

def collect_loop(ip: str, username: str, password: str, key_filename: Optional[str],
                 interval: float, out_csv: str, count: Optional[int],
                 daemon_port: int = DAEMON_PORT):

    ensure_header(out_csv)

    # --- SSH per gestione daemon e metriche sistema ---
    ssh = open_ssh(ip, username, password, key_filename)
    if ssh is None:
        LOGGER.error("Connessione SSH fallita. Uscita.")
        sys.exit(1)

    # --- Upload + avvio daemon pyniryo sul robot ---
    LOGGER.info("Caricamento daemon pyniryo sul robot…")
    if not upload_daemon(ssh):
        LOGGER.error("Upload daemon fallito.")
        sys.exit(1)
    start_daemon(ssh, daemon_port)

    # --- Thread C: metriche sistema (SSH, ogni 1 s) ---
    sys_thread = SysMetricsThread(ssh, interval=1.0)
    sys_thread.start()
    LOGGER.info("Thread C (SysMetrics) avviato")

    # --- Queue condivisa tra Thread A e Thread B ---
    sample_q: "queue.Queue[Optional[dict]]" = queue.Queue(maxsize=10_000)

    # --- Thread B: Writer ---
    writer = WriterThread(out_csv, sample_q)
    writer.start()
    LOGGER.info("Thread B (Writer) avviato → %s", out_csv)

    # --- Thread A: Sampler (gira nel main thread) ---
    daemon_cli = DaemonClient(ip, daemon_port)
    if not daemon_cli.connect():
        LOGGER.error("Connessione al daemon fallita.")
        sys_thread.stop()
        sample_q.put(None)
        writer.join(timeout=5)
        ssh.close()
        sys.exit(1)

    # Attendi il primo dato valido dallo stream (max 5 s)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if daemon_cli.get().get("ok"):
            break
        time.sleep(0.05)

    LOGGER.info(
        "Thread A (Sampler) avviato | intervallo=%.0f ms | CTRL+C per fermare",
        interval * 1000,
    )

    sampled = 0
    log_every = max(1, int(1.0 / interval))   # stampa ~1 riga/s in log
    try:
        while True:
            t_start = time.monotonic()

            robot = daemon_cli.get()
            sys_m = sys_thread.get()          # lettura non-bloccante dal Thread C
            row   = build_row(robot, sys_m)
            sample_q.put_nowait(row)           # RAM only, mai blocca

            sampled += 1
            if sampled % log_every == 0:
                LOGGER.info(
                    "Camp. %5d | x=%+.4f  y=%+.4f  z=%+.4f | "
                    "cpu=%s%%  rpi=%s°C  queue=%d",
                    sampled,
                    float(row["x_m"])       if row["x_m"]       != "" else 0.0,
                    float(row["y_m"])       if row["y_m"]       != "" else 0.0,
                    float(row["z_m"])       if row["z_m"]       != "" else 0.0,
                    row["cpu_percent"] if row["cpu_percent"] != "" else "?",
                    row["rpi_temp_C"]  if row["rpi_temp_C"]  != "" else "?",
                    sample_q.qsize(),
                )

            if count is not None and sampled >= count:
                break

            # Sleep preciso: compensa il tempo già speso
            elapsed = time.monotonic() - t_start
            sleep_t = interval - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    except KeyboardInterrupt:
        LOGGER.info("Interruzione richiesta dall'utente")
    except queue.Full:
        LOGGER.error("Buffer pieno! Il writer non riesce a stare al passo.")
    finally:
        daemon_cli.close()
        sys_thread.stop()
        sample_q.put(None)          # sentinel per Writer
        writer.join(timeout=10)
        ssh.close()
        LOGGER.info(
            "Raccolta terminata. Campioni acquisiti: %d  |  scritti su disco: %d  →  %s",
            sampled, writer.written, out_csv,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Raccoglie dati da un robot Niryo NED2 e li salva in CSV",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--ip",       "-i", default="192.168.0.102",  help="IP del robot")
    p.add_argument("--user",     "-u", default="niryo",          help="username SSH")
    p.add_argument("--password", "-p", default="robotics",       help="password SSH")
    p.add_argument("--key",            default=None,             help="chiave privata SSH")
    p.add_argument("--interval", "-t", type=float, default=0.05, help="intervallo campionamento (s)")
    p.add_argument("--output",   "-o", default="robot_data.csv", help="file CSV di output")
    p.add_argument("--count",          type=int,   default=None,  help="numero campioni (default: infinito)")
    p.add_argument("--daemon-port",    type=int,   default=DAEMON_PORT, help="porta TCP daemon sul robot")
    p.add_argument("--debug",          action="store_true",       help="abilita logging debug")
    return p.parse_args()


def main():
    args = parse_args()
    if args.debug:
        LOGGER.setLevel(logging.DEBUG)
    LOGGER.info(
        "Avvio raccolta dati → %s  (intervallo %.0f ms)",
        args.output, args.interval * 1000,
    )
    collect_loop(
        ip=args.ip,
        username=args.user,
        password=args.password,
        key_filename=args.key,
        interval=args.interval,
        out_csv=args.output,
        count=args.count,
        daemon_port=args.daemon_port,
    )


if __name__ == "__main__":
    main()
