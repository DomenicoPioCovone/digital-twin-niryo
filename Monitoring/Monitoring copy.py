import pandas as pd
import matplotlib.pyplot as plt
 
FROM = "2026-04-27T15:20:53.777480+02:00"
 
TO   = "2026-04-27T15:21:27.791208+02:00"
 
df = pd.read_csv("./data/AnomaliaNonRilevato.csv")
 
df["timestamp"] = pd.to_datetime(df["timestamp"])
 
filtered = df[
 
    (df["timestamp"] >= pd.to_datetime(FROM)) &
 
    (df["timestamp"] <= pd.to_datetime(TO))
 
]
 
#filtered.to_csv("ditto_filtered.csv", index=False)
 
#print(filtered)

plt.figure(figsize=(12,6))

plt.plot(filtered["timestamp"], filtered["x_m"], label="x")
plt.plot(filtered["timestamp"], filtered["y_m"], label="y")
plt.plot(filtered["timestamp"], filtered["z_m"], label="z")

plt.plot(filtered["timestamp"], filtered["roll_rad"], label="roll")
plt.plot(filtered["timestamp"], filtered["pitch_rad"], label="pitch")
plt.plot(filtered["timestamp"], filtered["yaw_rad"], label="yaw")

# plt.plot(filtered["timestamp"], filtered["j1_rad"], label="j1")
# plt.plot(filtered["timestamp"], filtered["j2_rad"], label="j2")
# plt.plot(filtered["timestamp"], filtered["j3_rad"], label="j3")
# plt.plot(filtered["timestamp"], filtered["j4_rad"], label="j4")
# plt.plot(filtered["timestamp"], filtered["j5_rad"], label="j5")
# plt.plot(filtered["timestamp"], filtered["j6_rad"], label="j6")

plt.xlabel("Timestamp")
plt.ylabel("Valori cinematici")
plt.title("Traiettoria cinematica robot (posizione + orientamento + giunti)")
plt.legend()
plt.xticks(rotation=45)

plt.tight_layout()
plt.show()