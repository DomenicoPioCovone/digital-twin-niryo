import csv
import time

import requests

# ---------------------------------------------------------------------------
# Defaults (usati sia come libreria sia dallo script standalone)
# ---------------------------------------------------------------------------
DEFAULT_THING_ID  = "io.eclipseprojects.ditto:robot-niryo-ned2"
DEFAULT_DITTO_URL = "http://localhost:8080/api/2/things"
DEFAULT_AUTH      = ("ditto", "ditto")

# Alias per compatibilità con codice che li importava direttamente
THING_ID  = DEFAULT_THING_ID
DITTO_URL = DEFAULT_DITTO_URL
AUTH      = DEFAULT_AUTH

CSV_FILE = "operational_robot_data.csv"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    value = str(value).strip()
    if value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _put(feature: str, props: dict,
         ditto_url: str, thing_id: str, auth: tuple,
         timeout: float = 2.0):
    """Esegue PUT delle proprietà di una feature su Ditto. Silenzioso sugli errori."""
    import logging
    url = f"{ditto_url}/{thing_id}/features/{feature}/properties"
    try:
        resp = requests.put(url, json=props, auth=auth, timeout=timeout)
        if resp.status_code not in (200, 201, 204):
            logging.getLogger("DittoSender").warning(
                "Ditto [%s] HTTP %s", feature, resp.status_code
            )
    except Exception as e:
        logging.getLogger("DittoSender").debug("Ditto [%s] errore: %s", feature, e)


# ---------------------------------------------------------------------------
# API di libreria – funzioni send_* parametrizzate
# ---------------------------------------------------------------------------

def send_pose(row: dict,
              ditto_url: str = DEFAULT_DITTO_URL,
              thing_id: str  = DEFAULT_THING_ID,
              auth: tuple    = DEFAULT_AUTH):
    _put("pose", {
        "x_m":       safe_float(row.get("x_m")),
        "y_m":       safe_float(row.get("y_m")),
        "z_m":       safe_float(row.get("z_m")),
        "roll_rad":  safe_float(row.get("roll_rad")),
        "pitch_rad": safe_float(row.get("pitch_rad")),
        "yaw_rad":   safe_float(row.get("yaw_rad")),
    }, ditto_url, thing_id, auth)


def send_joints(row: dict,
                ditto_url: str = DEFAULT_DITTO_URL,
                thing_id: str  = DEFAULT_THING_ID,
                auth: tuple    = DEFAULT_AUTH):
    _put("joints", {
        "j1_rad": safe_float(row.get("j1_rad")),
        "j2_rad": safe_float(row.get("j2_rad")),
        "j3_rad": safe_float(row.get("j3_rad")),
        "j4_rad": safe_float(row.get("j4_rad")),
        "j5_rad": safe_float(row.get("j5_rad")),
        "j6_rad": safe_float(row.get("j6_rad")),
    }, ditto_url, thing_id, auth)


def send_temperatures(row: dict,
                      ditto_url: str = DEFAULT_DITTO_URL,
                      thing_id: str  = DEFAULT_THING_ID,
                      auth: tuple    = DEFAULT_AUTH):
    _put("temperatures", {
        "temp_m1_C":  safe_float(row.get("temp_m1_C")),
        "temp_m2_C":  safe_float(row.get("temp_m2_C")),
        "temp_m3_C":  safe_float(row.get("temp_m3_C")),
        "temp_m4_C":  safe_float(row.get("temp_m4_C")),
        "temp_m5_C":  safe_float(row.get("temp_m5_C")),
        "temp_m6_C":  safe_float(row.get("temp_m6_C")),
        "temp_m7_C":  safe_float(row.get("temp_m7_C")),
        "temp_m8_C":  safe_float(row.get("temp_m8_C")),
        "rpi_temp_C": safe_float(row.get("rpi_temp_C")),
    }, ditto_url, thing_id, auth)


def send_system(row: dict,
                ditto_url: str = DEFAULT_DITTO_URL,
                thing_id: str  = DEFAULT_THING_ID,
                auth: tuple    = DEFAULT_AUTH):
    _put("system", {
        "cpu_percent":  safe_float(row.get("cpu_percent")),
        "mem_total_B":  safe_float(row.get("mem_total_B")),
        "mem_used_B":   safe_float(row.get("mem_used_B")),
        "mem_free_B":   safe_float(row.get("mem_free_B")),
        "load1":        safe_float(row.get("load1")),
        "load5":        safe_float(row.get("load5")),
        "load15":       safe_float(row.get("load15")),
        "disk_total_B": safe_float(row.get("disk_total_B")),
        "disk_used_B":  safe_float(row.get("disk_used_B")),
    }, ditto_url, thing_id, auth)


def send_acquisition(row: dict,
                     ditto_url: str = DEFAULT_DITTO_URL,
                     thing_id: str  = DEFAULT_THING_ID,
                     auth: tuple    = DEFAULT_AUTH):
    _put("acquisition", {
        "timestamp": row.get("timestamp", ""),
    }, ditto_url, thing_id, auth)


def publish_row(row: dict,
                ditto_url: str = DEFAULT_DITTO_URL,
                thing_id: str  = DEFAULT_THING_ID,
                auth: tuple    = DEFAULT_AUTH):
    """Pubblica tutte le feature di un campione (dict) su Ditto in un'unica chiamata."""
    send_pose(row,         ditto_url, thing_id, auth)
    send_joints(row,       ditto_url, thing_id, auth)
    send_temperatures(row, ditto_url, thing_id, auth)
    send_system(row,       ditto_url, thing_id, auth)
    send_acquisition(row,  ditto_url, thing_id, auth)


# ---------------------------------------------------------------------------
# Script standalone: legge da CSV e invia a Ditto
# ---------------------------------------------------------------------------

def stream_csv(csv_file: str = CSV_FILE,
               ditto_url: str = DEFAULT_DITTO_URL,
               thing_id: str  = DEFAULT_THING_ID,
               auth: tuple    = DEFAULT_AUTH):
    with open(csv_file, newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            publish_row(row, ditto_url, thing_id, auth)
            print(f"inviato campione {i}")
            time.sleep(0.05)   # 20 Hz


if __name__ == "__main__":
    stream_csv()
