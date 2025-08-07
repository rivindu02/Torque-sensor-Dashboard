from flask import Flask, render_template, jsonify, send_file
import sqlite3
import asyncio
import threading
import platform
import json
from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from flask import request

# On Linux, force the random-address client
if platform.system() == "Linux":
    from bleak.backends.bluezdbus import BlueZClient as BLEClient, AddressType
else:
    from bleak import BleakClient as BLEClient
    AddressType = None

app = Flask(__name__, static_folder="static", template_folder="templates")

# — Settings —
# Load config.json
try:
    with open("config.json", "r") as f:
        CONFIG = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print("Warning: config.json not found or invalid, using default values")
    CONFIG = {}

SENSOR_NAME = CONFIG.get("sensorName", "Torque Sensor")
SERVICE_UUID = CONFIG.get("serviceUUID", "18424398-7cbc-11e9-8f9e-2a86e4085a59")
TORQUE_UUID = CONFIG.get("characteristicUUID", "15005991-b131-3396-014c-664c9867b917")
MANUFACTURER_NAME = CONFIG.get("manufacturerName", "Renesas")
MODEL_NUMBER = CONFIG.get("modelNumber", "DA14531")
OFFSET = CONFIG.get("offset", 880804)  # Approx raw value for 2.1 mV (zero torque, 10.5% of 8,388,607)
SCALE = CONFIG.get("scale", 1.33e-7)  # Placeholder: N·cm per count, assumes ±1 N·cm max torque

DB_FILE = "torque_data.db"

# Global status and thread control
status = "Disconnected"
ble_thread = None
stop_ble = False

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS torque_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            torque_value REAL
        )
    """)
    conn.commit()
    conn.close()

def save_val(val):
    print(f"Saving torque value: {val:.2f} N·cm")
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO torque_data (torque_value) VALUES (?)", (val,))
    conn.commit()
    conn.close()

async def ble_loop():
    global status, stop_ble
    while not stop_ble:
        # ── 1) Scan with callback ──
        status = "Scanning…"
        found = asyncio.Event()
        device_holder = {}

        def detection_callback(device: BLEDevice, adv: AdvertisementData):
            if (adv.service_uuids and SERVICE_UUID.lower() in [uuid.lower() for uuid in adv.service_uuids]) or \
               (device.name and SENSOR_NAME.lower() in device.name.lower()) or \
               (adv.manufacturer_data and MANUFACTURER_NAME in str(adv.manufacturer_data)):
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

        if stop_ble:
            break

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
                # Verify device has the required service
                try:
                    services = await client.get_services()
                    service_found = False
                    for service in services:
                        if service.uuid.lower() == SERVICE_UUID.lower():
                            service_found = True
                            break
                    if not service_found:
                        status = "Required service not found"
                        continue
                except Exception as e:
                    status = f"Service verification failed: {str(e)}"
                    continue

                # ── 3) Notification loop ──
                def notification_handler(sender, data):
                    global status
                    try:
                        # Log raw data for debugging
                        print(f"Notification raw data (hex): {data.hex()}")
                        print(f"Notification data length: {len(data)} bytes")

                        # Expect 4 bytes but use first 3 bytes for 24-bit signed integer
                        if len(data) < 3:
                            status = f"Unexpected notification data length: {len(data)} bytes (expected at least 3)"
                            print(status)
                            return

                        # Extract first 3 bytes for 24-bit signed integer
                        raw_val = int.from_bytes(data[:3], byteorder="little", signed=True)
                        print(f"Raw value (integer): {raw_val}")

                        # Log OFFSET and SCALE
                        print(f"OFFSET: {OFFSET}, SCALE: {SCALE}")

                        # Calculate torque
                        torque = (raw_val - OFFSET) * SCALE
                        print(f"Calculated torque: {torque:.2f} N·cm")

                        # Save to database
                        save_val(torque)
                        status = f"Streaming: {torque:.2f} N·cm"
                    except Exception as e:
                        status = f"Notification error: {str(e)}"
                        print(f"Notification error details: {str(e)}")

                try:
                    # Start notifications
                    await client.start_notify(TORQUE_UUID, notification_handler)
                    print(f"Subscribed to notifications for UUID: {TORQUE_UUID}")
                    # Keep connection alive while receiving notifications
                    while client.is_connected and not stop_ble:
                        await asyncio.sleep(1.0)
                    # Stop notifications when loop exits
                    await client.stop_notify(TORQUE_UUID)
                except Exception as e:
                    status = f"Notification setup error: {str(e)}"
                    print(f"Notification setup error details: {str(e)}")
                    await asyncio.sleep(5.0)
                    continue

        except Exception as e:
            status = f"BLE Error: {str(e)}"
            print(f"BLE Error details: {str(e)}")
            await asyncio.sleep(5.0)
    
    status = "Disconnected"

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
        return jsonify({"timestamp": None, "torque_value": None})
    return jsonify({"timestamp": row[0], "torque_value": row[1]})

@app.route("/export_csv")
def export_csv():
    import pandas as pd
    import os
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "torque_data.csv")
        df = pd.read_sql("SELECT * FROM torque_data", sqlite3.connect(DB_FILE))
        if df.empty:
            return jsonify({"error": "No data available for CSV export"}), 400
        df.to_csv(path, index=False)
        return send_file(path, as_attachment=True, download_name="torque_data.csv")
    except Exception as e:
        return jsonify({"error": f"CSV export failed: {str(e)}"}), 500

@app.route("/export_pdf")
def export_pdf():
    import tempfile
    import os
    try:
        from reportlab.pdfgen import canvas
        
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute("SELECT timestamp, torque_value FROM torque_data").fetchall()
        conn.close()
        
        if not rows:
            return jsonify({"error": "No data available for PDF export"}), 400
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            temp_path = tmp_file.name
        
        c = canvas.Canvas(temp_path)
        c.drawString(100, 800, "Torque Sensor Report")
        y = 780
        for ts, v in rows:
            c.drawString(100, y, f"{ts} – {v:.2f} N·cm")
            y -= 15
            if y < 50:
                c.showPage()
                y = 800
        c.save()
        
        response = send_file(temp_path, as_attachment=True, download_name="torque_data.pdf")
        response.call_on_close(lambda: os.unlink(temp_path))
        return response
        
    except ImportError:
        return jsonify({"error": "ReportLab library not installed. Install with: pip install reportlab"}), 500
    except Exception as e:
        return jsonify({"error": f"PDF export failed: {str(e)}"}), 500

@app.route("/start")
def start_ble():
    global ble_thread, stop_ble
    try:
        if ble_thread is None or not ble_thread.is_alive():
            stop_ble = False
            ble_thread = threading.Thread(target=lambda: asyncio.run(ble_loop()), daemon=True)
            ble_thread.start()
            return jsonify({"status": "BLE reader started"})
        else:
            return jsonify({"status": "BLE reader already running"})
    except Exception as e:
        return jsonify({"status": f"Error starting BLE: {str(e)}"})

@app.route("/stop")
def stop_ble_connection():
    global stop_ble
    stop_ble = True
    return jsonify({"status": "BLE reader stopped"})

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)

@app.route("/push", methods=["POST"])
def push_data():
    """
    Accept JSON { "torque_value": float, "timestamp": "ISO8601" }
    """
    payload = request.get_json(force=True)
    torque = payload.get("torque_value")
    ts     = payload.get("timestamp")
    if torque is None or ts is None:
        return jsonify({"error":"Missing fields"}), 400

    # Save to DB
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO torque_data (timestamp, torque_value) VALUES (?,?)",
        (ts, torque)
    )
    conn.commit()
    conn.close()
    return jsonify({"status":"ok"}), 200