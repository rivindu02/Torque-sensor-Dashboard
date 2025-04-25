from flask import Flask, render_template, jsonify, send_file
import sqlite3
import pandas as pd
import asyncio
from bleak import BleakScanner, BleakClient
from reportlab.pdfgen import canvas
import os


# BLE Sensor Configuration
SENSOR_ADDRESS = "XX:XX:XX:XX:XX:XX"  # Replace with sensor MAC address
CHARACTERISTIC_UUID = "0000xxxx-0000-1000-8000-00805f9b34fb"  # Replace with correct UUID

# Database Setup
DB_FILE = "torque_data.db"

app = Flask(__name__)

# 📌 Serve Web Dashboard
@app.route("/")
def dashboard():
    return render_template("index.html")

# 📌 Fetch Latest Torque Reading
@app.route("/torque")
def get_torque():
    """Fetch the latest torque value, ensuring it exists."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM torque_data ORDER BY timestamp DESC LIMIT 1")
    result = cursor.fetchone()
    conn.close()

    if result is None:  # 🛠 If no data exists, return a safe default
        return jsonify({"timestamp": "No Data Available", "torque_value": "No Data"})

    return jsonify({"timestamp": result[1], "torque_value": result[2]})

# 📌 Export Data as CSV
@app.route("/export_csv")
def export_csv():
    """Generate and send a CSV file with torque data."""
    csv_path = "sensor reading visualization/torque_data.csv"

    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM torque_data", conn)
    conn.close()

    # Ensure the CSV file is created
    df.to_csv(csv_path, index=False)

    if os.path.exists(csv_path):
        return send_file(csv_path, as_attachment=True)
    else:
        return "Error: CSV file not found.", 500

# 📌 Export Data as PDF
@app.route("/export_pdf")
def export_pdf():
    """Generate and send a PDF file with torque data."""
    pdf_path = "sensor reading visualization/torque_data.pdf"

    # Create the PDF file first
    c = canvas.Canvas(pdf_path)
    c.drawString(100, 750, "Torque Sensor Readings Report")

    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM torque_data", conn)
    conn.close()

    y = 700
    for _, row in df.iterrows():
        c.drawString(100, y, f"{row['timestamp']} - {row['torque_value']} Ncm")
        y -= 20

    c.save()

    # Ensure file exists before sending
    if os.path.exists(pdf_path):
        return send_file(pdf_path, as_attachment=True)
    else:
        return "Error: PDF file not found.", 500


# 📌 BLE Scanning for Sensors
@app.route("/scan_ble")
async def scan_ble_devices():
    devices = await BleakScanner.discover()
    found_devices = [{"name": device.name, "address": device.address} for device in devices]
    return jsonify(found_devices)

# 📌 BLE Connection & Data Retrieval
@app.route("/connect_ble")
async def connect_to_ble_sensor():
    async with BleakClient(SENSOR_ADDRESS) as client:
        while True:
            value = await client.read_gatt_char(CHARACTERISTIC_UUID)
            torque_value = int.from_bytes(value, byteorder="little")
            save_torque_value(torque_value)
            await asyncio.sleep(2)  # Adjust based on sensor update rate

# 📌 Save Torque Readings in Database
def save_torque_value(torque_value):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO torque_data (torque_value) VALUES (?)", (torque_value,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    app.run(debug=True)