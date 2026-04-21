# Digital Twin – Data Collector per Niryo NED2

Raccoglie dati dal robot Niryo NED2 a frequenza configurabile (default **50 ms / 20 Hz**)
e li salva in CSV con timestamp ISO a microsecondi.
Applicazione Multi-Thread formata da 4 Thread A,B,C,D

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

## DittoSender

- Funge da legante tra il data_collector e Ditto. Prende una riga dati generata ,suddivide le features e fa una PUT tramite richieste HTTP verso Ditto
Thread A (Sampler) -> build_row() -> queue Ditto -> Thread D (DittoWriter) -> DittoSender.publish_row() -> HTTP REST API -> Eclipse Ditto (Digital Twin)
---

##  Comunicazione tra thread
Sampler  ->  Queue  -> Weiter -> Queue -> DittoSander
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

## Flusso dati completo
Robot → TCP → data_collector    
↓  
build_row  
↓  
queue Ditto  
↓  
Thread DittoWriter  
↓  
HTTP PUT (REST)  
↓  
Eclipse Ditto (localhost:8080)