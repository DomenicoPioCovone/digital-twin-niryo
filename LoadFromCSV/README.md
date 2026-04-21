# Digital Twin – Data Collector per Niryo NED2

Raccoglie dati dal robot Niryo NED2 a frequenza configurabile (default **50 ms / 20 Hz**)
e li salva in CSV con timestamp ISO a microsecondi.

## Specifiche del robot (rilevate via SSH)

Queste informazioni sono statiche e utili per la riproducibilità degli esperimenti.

### Hardware

| Parametro | Valore |
|-----------|--------|
| Modello | **Niryo NED2** |
| Hostname | `ned2-46-98c-521` |
| Compute unit | Raspberry Pi 4 Model B Rev 1.5 (BCM2835) |
| Architettura | `aarch64` |
| RAM | 3.8 GB |
| Storage | 24 GB (microSD), 9 GB usati al momento dell'acquisizione |
| Interfacce di rete | `wlan0` (192.168.0.102), `eth0` (169.254.200.200), `apwlan0` (10.10.10.10) |

### Software di sistema

| Parametro | Valore |
|-----------|--------|
| OS | Ubuntu 20.04.6 LTS (Focal Fossa) |
| Kernel | Linux 5.4.0-1078-raspi (aarch64, PREEMPT) |
| Python | 3.8.10 |
| ROS | Noetic Ninjemys |
| Stack software Niryo | v5.0.0 (`niryo_robot_*` packages) |
| Dynamixel SDK (ROS) | 3.7.51 |

### Librerie Python sul robot (venv `/home/niryo/catkin_ws_venv`)

| Libreria | Versione | Uso |
|----------|----------|-----|
| `pyniryo` | 1.2.1 | API ufficiale robot (TCP su `127.0.0.1:40001`) |
| `numpy` | 1.24.4 | Calcolo numerico |
| `opencv-python` | 4.11.0.86 | Computer vision |
| `pymodbus` | 3.6.9 | Modbus TCP (usato internamente dal robot) |
| `requests` | 2.32.4 | HTTP client |
| `psutil` | 5.9.8 | Metriche di sistema |
| `PyYAML` | 6.0.3 | Configurazione ROS |
| `RPi.GPIO` | 0.6.5 | GPIO Raspberry Pi |

### Limiti cinematici (da `robot_command_validation.yaml`)

**Spazio cartesiano (end-effector):**

| Asse | Min | Max |
|------|-----|-----|
| x | −0.50 m | +0.50 m |
| y | −0.50 m | +0.50 m |
| z | −0.15 m | +0.60 m |
| roll | −π rad | +π rad |
| pitch | −π rad | +π rad |
| yaw | −π rad | +π rad |

### Architettura di comunicazione

```
[Niryo NED2]
  ROS Noetic (catkin_ws)
    └─ niryo_robot_hardware_interface  →  TCP :40001  ←  pyniryo
    └─ niryo_robot_modbus              →  TCP :5020   (Modbus, solo locale)
    └─ daemon _dc_daemon.py            →  TCP :9876   ←  data_collector.py (questo progetto)
  SSH :22  ←  metriche OS (CPU, RAM, load, disk)
```

## Architettura

Il sistema usa più thread per migliorare le prestazioni.

### Thread A – Sampler
- Frequenza: 50 ms
- Legge dati dal robot via TCP
- Inserisce dati in una queue

### Thread B – Writer
- Scrive su CSV
- Batch ogni 0.5 secondi

### Thread C – SysMetrics
- Frequenza: 1 s
- Usa SSH
- Legge CPU, RAM, disco

### Thread D – DittoSender
- Invia dati a Ditto
- Usa HTTP REST
# DittoSender
Funge da legante tra il data_collector e Ditto.Prende una riga dati generata ,suddivide le features e fa una PUT tramite richieste HTTP verso Ditto
Thread A (Sampler)
        ↓
build_row()
        ↓
queue Ditto
        ↓
Thread D (DittoWriter)
        ↓
DittoSender.publish_row()
        ↓
HTTP REST API
        ↓
Eclipse Ditto (Digital Twin)
---

##  Comunicazione tra thread
Sampler-->Queue-->Weiter-->Queue-->DittoSander
- thread indipendenti
- nessun blocco
- alta efficienza

## Integrazione con Eclipse Ditto

Eclipse Ditto rappresenta il robot come **Digital Twin**.

### Feature inviate

| Feature | Descrizione |
|--------|------------|
| pose | posizione |
| joints | giunti |
| temperatures | temperature |
| system | metriche |
| acquisition | timestamp |

---

## Esempio API
PUT http://localhost:8080/api/2/things/{thingId}/features/pose/properties

## Installazione

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configurazione

Copia `.env.example` in `.env` e inserisci le credenziali del robot:

```bash
cp .env.example .env
# edita .env con il tuo editor preferito
```

Variabili disponibili:

| Variabile         | Default              | Descrizione                   |
|-------------------|----------------------|-------------------------------|
| `ROBOT_IP`        | _(da .env)_          | Indirizzo IP del robot        |
| `ROBOT_USER`      | _(da .env)_          | Username SSH                  |
| `ROBOT_PASSWORD`  | _(da .env)_          | Password SSH                  |
| `ROBOT_SSH_KEY`   | _(da .env)_          | Percorso chiave privata SSH   |
| `SAMPLE_INTERVAL` | `0.05`               | Intervallo in secondi         |
| `OUTPUT_FILE`     | `data/robot_data.csv`| File CSV di output            |
| `DAEMON_PORT`     | `9876`               | Porta TCP daemon sul robot    |

## Utilizzo

```bash
# Acquisizione continua (usa valori da .env)
python3 data_collector.py

# Durata fissa: 10 s a 50 ms (200 campioni)
python3 data_collector.py --count 200 --interval 0.05

# Intervallo personalizzato e file di output
python3 data_collector.py --interval 0.1 --output data/sessione1.csv

# Override credenziali da CLI (sconsigliato: usa .env)
python3 data_collector.py --ip <ROBOT_IP> --user <USER> --password <PASSWORD>
```

## Output CSV

Ogni campione è una riga con **30 colonne**:

### Timestamp

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `timestamp` | stringa ISO 8601 | Data e ora di acquisizione con fuso orario e precisione al microsecondo (es. `2026-02-24T12:33:21.601234+01:00`) |

### Pose end-effector (sistema di riferimento del robot)

| Campo | Unità | Descrizione |
|-------|-------|-------------|
| `x_m` | m | Posizione dell'end-effector lungo l'asse X |
| `y_m` | m | Posizione dell'end-effector lungo l'asse Y |
| `z_m` | m | Posizione dell'end-effector lungo l'asse Z |
| `roll_rad` | rad | Rotazione attorno all'asse X (roll) |
| `pitch_rad` | rad | Rotazione attorno all'asse Y (pitch) |
| `yaw_rad` | rad | Rotazione attorno all'asse Z (yaw) |

### Giunti (angoli in radianti)

| Campo | Descrizione |
|-------|-------------|
| `j1_rad` | Giunto 1 – base (rotazione orizzontale) |
| `j2_rad` | Giunto 2 – spalla |
| `j3_rad` | Giunto 3 – gomito |
| `j4_rad` | Giunto 4 – polso rotazione |
| `j5_rad` | Giunto 5 – polso inclinazione |
| `j6_rad` | Giunto 6 – flangia (rotazione utensile) |

### Temperature motori

| Campo | Unità | Descrizione |
|-------|-------|-------------|
| `temp_m1_C` … `temp_m6_C` | °C | Temperatura dei 6 motori dei giunti |
| `temp_m7_C`, `temp_m8_C` | °C | Temperatura dei motori dell'utensile/conveyor (se presenti) |
| `rpi_temp_C` | °C | Temperatura della CPU Raspberry Pi del robot |

### Metriche di sistema (Raspberry Pi)

| Campo | Unità | Descrizione |
|-------|-------|-------------|
| `cpu_percent` | % | Utilizzo CPU (media su ~300 ms, tutti i core) |
| `mem_total_B` | byte | RAM totale installata |
| `mem_used_B` | byte | RAM attualmente utilizzata |
| `mem_free_B` | byte | RAM libera |
| `load1` | – | Load average ultimo minuto |
| `load5` | – | Load average ultimi 5 minuti |
| `load15` | – | Load average ultimi 15 minuti |
| `disk_total_B` | byte | Spazio totale partizione root |
| `disk_used_B` | byte | Spazio utilizzato partizione root |

---

## Dataset acquisiti

I file CSV nella cartella `data/` corrispondono a tre scenari distinti, acquisiti a **50 ms (20 Hz)** per circa 200 secondi ciascuno. Sono pensati per addestrare o validare modelli di anomaly detection / Digital Twin.

### `fermo_robot_data.csv` – Robot fermo (baseline)

Il robot è in posizione di home, tutti i giunti fermi. Nessuna traiettoria in esecuzione.

- **Pose**: costante per tutta la sessione
- **Giunti**: costanti, vicini a zero
- **Temperature motori**: stabili, vicine alla temperatura ambiente
- **CPU**: bassa (ROS in idle, ~30–50%)
- **Uso tipico**: baseline di riferimento, classe *normale/fermo*

---

### `error_loop_robot_data.csv` – Robot bloccato in un loop (anomalia software)

Il robot ha eseguito un ciclo operativo che è andato in errore a causa di un bug nel codice di controllo (es. condizione di uscita mancante, eccezione non gestita che causa retry continui). Il robot rimane fisicamente fermo o oscilla ripetutamente sulla stessa micro-traiettoria.

- **Pose / Giunti**: invariati o oscillanti in un range minimo (nessun avanzamento reale del task)
- **CPU**: elevata e sostenuta (ROS + codice Python in loop stretto)
- **Load average**: in salita progressiva
- **Temperature motori**: possibile lieve aumento per tentativi di movimento ripetuti
- **Uso tipico**: rilevamento anomalia software, classe *errore/loop*

---

### `operational_robot_data.csv` – Robot operativo (ciclo produttivo)

Il robot esegue il ciclo produttivo completo in loop:

1. **Vai in posizione di osservazione** – end-effector si posiziona sopra l'area di lavoro
2. **Visiona con AI** – pausa breve per acquisizione immagine e inferenza (vision system)
3. **Prendi il mattoncino** – discesa, attivazione gripper, presa
4. **Vai in posizione di rilascio** – traiettoria verso l'area di destinazione
5. **Rilascia** – apertura gripper, deposito mattoncino
6. **Avvia il conveyor** – attivazione nastro trasportatore
7. **Ritorna in posizione di home** – ritorno alla posizione iniziale
8. **Ricomincia**

- **Pose / Giunti**: variazione continua e ciclica, con pattern ripetitivi visibili
- **CPU**: alta e variabile (picchi durante visioning e movimenti complessi)
- **Temperature motori**: più alte rispetto al fermo, stabili dopo il warm-up
- **Uso tipico**: modellazione del comportamento nominale, classe *operativo*

---

## Struttura del progetto

```
.
├── data_collector.py   # script principale
├── requirements.txt    # dipendenze Python
├── .env                # credenziali (NON versionato)
├── .env.example        # template da committare
├── .gitignore
├── data/               # CSV acquisiti (NON versionati)
│   ├── fermo_robot_data.csv
│   ├── error_loop_robot_data.csv
│   └── operational_robot_data.csv
└── README.md
```
