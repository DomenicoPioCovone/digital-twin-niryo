# Data collector per robot Niryo

Questo piccolo progetto raccoglie periodicamente dati di posizione (pose) e metriche di sistema
da un robot Niryo e li salva in un file CSV con timestamp preciso (ISO con microsecondi).

Funzionalità principali
- Richiesta HTTP per ottenere la pose (endpoint configurabile, default `/api/pose`).
- Connessione SSH per leggere CPU, memoria, load e disco.
- Salvataggio in CSV con intestazione e campioni appesi.

Installazione

1. Creare un ambiente virtuale (opzionale ma consigliato):

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Installare dipendenze:

```bash
python3 -m pip install -r requirements.txt
```

Esempio d'uso

Se il tuo robot è all'indirizzo 192.168.100.102 con credenziali SSH `niryo` / `robotics`:

```bash
python3 data_collector.py --ip 192.168.100.102 --user niryo --password robotics --interval 2 --output dati_robot.csv
```

Se il robot non espone HTTP ma parla Modbus (TCP), puoi usare lo script in modalità Modbus specificando i registri che contengono le coordinate.

Esempio (registri base per ogni valore, con float 32-bit su 2 registri):

```bash
python3 data_collector.py --ip 192.168.100.102 --modbus --modbus-port 502 \
	--modbus-registers "x:100,y:102,z:104,rx:106,ry:108,rz:110" \
	--interval 1 --output dati_modbus.csv
```

Nota: lo script usa `pymodbus` per connettersi via Modbus TCP. Se il device Modbus è raggiungibile solo in localhost sulla macchina del robot
e non sulla rete, puoi prima connetterti via SSH e attivare un tunnel (o esporre il servizio).

Se non conosci la mappatura registri, incolla qui l'output/descrizione del dispositivo Modbus e ti aiuto a configurarla.

Opzioni utili
- `--pose-endpoint`: endpoint HTTP per la pose (default `/api/pose`).
- `--http-user` e `--http-pass`: se l'endpoint HTTP richiede Basic Auth.
- `--key`: percorso a chiave privata SSH se non si usa password.
- `--count`: numero di campioni da acquisire (altrimenti va in loop continuo).
- `--debug`: abilita logging dettagliato.

Assunzioni e note
- Il programma tenta di adattarsi a diversi formati JSON per la pose, ma potresti dover modificare `--pose-endpoint` o la funzione `get_pose_http` se la risposta del robot è diversa.
- Per raccogliere la CPU e la memoria il codice esegue comandi via SSH (`free`, `top`, `/proc/*`, `df`). Se la distribuzione del robot differisce, potrebbero essere necessari aggiustamenti.
- Il file CSV è appeso ad ogni esecuzione. Se vuoi un nuovo file, rimuovi o rinomina il file di output.

Privacy / Sicurezza
- Fornire le credenziali solo su reti sicure. Considera di usare chiavi SSH invece di password.

Prossimi possibili miglioramenti
- Supporto nativo per l'API ufficiale Niryo, se disponibile.
- Esportazione in formati diversi (JSONL, InfluxDB, MQTT).
- Aggiungere autenticazione più robusta e retry/backoff.

Se vuoi, posso adattare lo script per il formato esatto della tua API `/api/pose` o aggiungere l'invio dei dati a un server remoto.
