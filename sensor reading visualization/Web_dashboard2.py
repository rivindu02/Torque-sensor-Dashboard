from flask import Flask, render_template, jsonify, send_file
import sqlite3, threading, asyncio, os, platform
import json
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

# On Linux, force the random‐address client
if platform.system() == "Linux":
    from bleak.backends.bluezdbus import BlueZClient as BLEClient, AddressType
else:
    from bleak import BleakClient as BLEClient
    AddressType = None

app = Flask(__name__, static_folder="static", template_folder="templates")

# — Settings —
# Load config.json
with open("config.json", "r") as f:
    CONFIG = json.load(f)

SENSOR_NAME = CONFIG.get("sensorName", "Torque Sensor")
SENSOR_MAC = CONFIG.get("sensorAddress", "48:23:35:F4:00:0B")
TORQUE_UUID = CONFIG.get("torqueUUID", "3473E583-0516-642E-5C1D-06A0FAAD9366")  # Updated UUID
MANUFACTURER_NAME = "Renesas"  # For additional verification
MODEL_NUMBER = "DA14531"  # For additional verification

DB_FILE = "torque_data.db"

# Global status
status = "Disconnected"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS torque_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            torque_value INTEGER
        )
    """)
    conn.commit()
    conn.close()

def save_val(val):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO torque_data (torque_value) VALUES (?)", (val,))
    conn.commit()
    conn.close()

async def ble_loop():
    global status
    while True:
        # ── 1) Scan with callback ──
        status = "Scanning…"
        found = asyncio.Event()
        device_holder = {}

        def detection_callback(device: BLEDevice, adv: AdvertisementData):
            # Check MAC address and manufacturer data if available
            if (device.address.lower() == SENSOR_MAC.lower() or 
                (adv.manufacturer_data and MANUFACTURER_NAME in str(adv.manufacturer_data))):
                device_holder['dev'] = device
                device_holder['adv'] = adv
                found.set()

        scanner = BleakScanner(detection_callback)
        await scanner.start()
        try:
            await asyncio.wait_for(found.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            status = "Sensor not found"
            await scanner.stop()
            await asyncio.sleep(5.0)
            continue
        finally:
            await scanner.stop()

        dev = device_holder['dev']
        adv = device_holder.get('adv', None)
        status = f"Found {dev.name or dev.address}"

        # ── 2) Connect using full BLEDevice ──
        try:
            if platform.system() == "Linux":
                client = BLEClient(dev.address, address_type=AddressType.random)
            else:
                client = BLEClient(dev)

            async with client:
                if not client.is_connected:
                    status = "Connection failed"
                    await asyncio.sleep(5.0)
                    continue

                status = "Connected ✓"
                
                # Verify device information
                try:
                    model_number = await client.read_gatt_char("00002a24-0000-1000-8000-00805f9b34fb")
                    if MODEL_NUMBER not in model_number.decode():
                        status = "Wrong device model"
                        continue
                except Exception as e:
                    status = f"Device verification failed: {str(e)}"
                    continue

                # ── 3) Read loop ──
                while client.is_connected:
                    try:
                        raw = await client.read_gatt_char(TORQUE_UUID)
                        val = int.from_bytes(raw, byteorder="little", signed=False)
                        save_val(val)
                        status = f"Streaming: {val} N·cm"
                    except Exception as e:
                        status = f"Read error: {str(e)}"
                        await asyncio.sleep(1.0)
                        break  # Exit read loop on error
                    await asyncio.sleep(1.0)

        except Exception as e:
            status = f"BLE Error: {str(e)}"
            await asyncio.sleep(5.0)

@app.route("/")
def dashboard():
    return render_template("index.html")

@app.route("/status")
def get_status():
    return jsonify({"status": status})

@app.route("/torque")
def get_torque():
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT timestamp, torque_value FROM torque_data ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"timestamp":None, "torque_value":None})
    return jsonify({"timestamp": row[0], "torque_value": row[1]})

@app.route("/history")
def get_history():
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT timestamp, torque_value FROM torque_data ORDER BY id DESC LIMIT 100"
    ).fetchall()
    conn.close()
    data = [{"t":r[0], "v":r[1]} for r in reversed(rows)]
    return jsonify(data)

@app.route("/export_csv")
def export_csv():
    import pandas as pd
    path = "torque_data.csv"
    df = pd.read_sql("SELECT * FROM torque_data", sqlite3.connect(DB_FILE))
    df.to_csv(path, index=False)
    return send_file(path, as_attachment=True)

@app.route("/export_pdf")
def export_pdf():
    from reportlab.pdfgen import canvas
    path = "torque_data.pdf"
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("SELECT timestamp, torque_value FROM torque_data").fetchall()
    conn.close()
    c = canvas.Canvas(path)
    c.drawString(100,800,"Torque Sensor Report")
    y = 780
    for ts, v in rows:
        c.drawString(100,y,f"{ts} – {v} N·cm")
        y -= 15
        if y < 50:
            c.showPage(); y = 800
    c.save()
    return send_file(path, as_attachment=True)

@app.route("/start")
def start_ble():
    global ble_thread
    if not ble_thread.is_alive():
        ble_thread = threading.Thread(target=lambda: asyncio.run(ble_loop()), daemon=True)
        ble_thread.start()
    return jsonify({"status":"BLE reader started"})


if __name__ == "__main__":
    init_db()
    ble_thread = threading.Thread(target=lambda: asyncio.run(ble_loop()), daemon=True)
    ble_thread.start()
    app.run(debug=True)