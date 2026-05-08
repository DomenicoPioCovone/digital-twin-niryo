import pandas as pd
import matplotlib.pyplot as plt

FROM = "2026-04-27T15:37:07+02:00"

df = pd.read_csv("./data/AnomaliaNonRilevato.csv")

# parsing corretto con timezone
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

# converto anche FROM in UTC
from_ts = pd.to_datetime(FROM, utc=True)

# filtro
filtered = df[df["timestamp"] >= from_ts]

print("Righe totali:", len(df))
print("Righe filtrate:", len(filtered))

# ------------------ GRAFICO 1: POSIZIONE ------------------
plt.figure(figsize=(12,6))

plt.plot(filtered["timestamp"], filtered["x_m"], label="x")
plt.plot(filtered["timestamp"], filtered["y_m"], label="y")
plt.plot(filtered["timestamp"], filtered["z_m"], label="z")

plt.xlabel("Timestamp")
plt.ylabel("Posizione (m)")
plt.title("Traiettoria posizione (x, y, z)")
plt.legend()
plt.xticks(rotation=45)

plt.tight_layout()
plt.show()

# ------------------ GRAFICO 2: ROTAZIONE ------------------
plt.figure(figsize=(12,6))

plt.plot(filtered["timestamp"], filtered["roll_rad"], label="roll")
plt.plot(filtered["timestamp"], filtered["pitch_rad"], label="pitch")
plt.plot(filtered["timestamp"], filtered["yaw_rad"], label="yaw")

plt.xlabel("Timestamp")
plt.ylabel("Rotazione (rad)")
plt.title("Orientamento (roll, pitch, yaw)")
plt.legend()
plt.xticks(rotation=45)

plt.tight_layout()
plt.show()