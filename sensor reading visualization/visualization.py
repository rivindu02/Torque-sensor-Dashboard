import asyncio
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from bleak import BleakScanner, BleakClient

# BLE Sensor Configuration
SENSOR_ADDRESS = "XX:XX:XX:XX:XX:XX"  # Replace with sensor MAC address
CHARACTERISTIC_UUID = "0000xxxx-0000-1000-8000-00805f9b34fb"  # Replace with correct UUID


# Database Setup
DB_FILE = "torque_data.db"

def setup_database():
    """Creates the database table if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS torque_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            torque_value REAL
        )
    """)
    conn.commit()
    conn.close()

def save_torque_value(torque_value):
    """Stores the torque reading in the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO torque_data (torque_value) VALUES (?)", (torque_value,))
    conn.commit()
    conn.close()

async def scan_ble_devices():
    """Scans for BLE devices."""
    devices = await BleakScanner.discover()
    for device in devices:
        print(f"Found: {device.name} | Address: {device.address}")

async def get_torque_data():
    """Connects to the sensor and retrieves real-time torque data."""
    async with BleakClient(SENSOR_ADDRESS) as client:
        while True:
            value = await client.read_gatt_char(CHARACTERISTIC_UUID)
            torque_value = int.from_bytes(value, byteorder="little")
            print(f"Torque Value: {torque_value} Nm")
            save_torque_value(torque_value)
            await asyncio.sleep(2)  # Adjust based on sensor update rate

def plot_torque_history():
    """Plots stored torque values."""
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM torque_data ORDER BY timestamp ASC", conn)
    conn.close()

    if df.empty:
        print("No data available to plot.")
        return

    plt.plot(df['timestamp'], df['torque_value'], marker="o", linestyle="-", color="b", label="Torque Readings")
    plt.xlabel("Time")
    plt.ylabel("Torque Value (Nm)")
    plt.title("Torque Sensor Data Over Time")
    plt.xticks(rotation=45)
    plt.legend()
    plt.show()

# Run the setup before using the system
setup_database()

# Uncomment the following lines when you have a BLE sensor
# asyncio.run(scan_ble_devices())
# asyncio.run(get_torque_data())

# Uncomment this to view stored torque history
# plot_torque_history()