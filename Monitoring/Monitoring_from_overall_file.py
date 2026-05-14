import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("./AnalisiFrequenza/Aliasing1000ms.csv")

# parsing corretto con timezone
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

print("Righe totali:", len(df))

# opzionale ma consigliato
df = df.sort_values("timestamp")

# ------------------ GRAFICO 1: POSIZIONE ------------------
plt.figure(figsize=(12,6))

plt.plot(df["timestamp"], df["x_m"], label="x")
plt.plot(df["timestamp"], df["y_m"], label="y")
plt.plot(df["timestamp"], df["z_m"], label="z")

plt.xlabel("Timestamp")
plt.ylabel("Posizione (m)")
plt.title("Traiettoria posizione (x, y, z)")
plt.legend()
plt.xticks(rotation=45)

plt.tight_layout()
plt.show()

# ------------------ GRAFICO 2: ROTAZIONE ------------------
plt.figure(figsize=(12,6))

plt.plot(df["timestamp"], df["roll_rad"], label="roll")
plt.plot(df["timestamp"], df["pitch_rad"], label="pitch")
plt.plot(df["timestamp"], df["yaw_rad"], label="yaw")

plt.xlabel("Timestamp")
plt.ylabel("Rotazione (rad)")
plt.title("Orientamento (roll, pitch, yaw)")
plt.legend()
plt.xticks(rotation=45)

plt.tight_layout()
plt.show()