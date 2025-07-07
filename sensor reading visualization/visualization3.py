import sys
import sqlite3
import pandas as pd
import numpy as np
import pyqtgraph as pg
from pyqtgraph.graphicsItems.DateAxisItem import DateAxisItem
import qdarkstyle
import matplotlib.pyplot as plt
import asyncio
import threading
import json

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel,
    QVBoxLayout, QWidget, QSlider, QSplitter, QHBoxLayout
)
from PyQt6.QtCore import QTimer, Qt
from reportlab.pdfgen import canvas

# — User settings —
SENSOR_MAC        = "48:23:35:34:05:C6"
DB_FILE           = "torque_data.db"
THRESHOLD_DEFAULT = 100  # N·cm

# — The actual HX711 characteristic UUID (2-byte read) —
# Load config.json
with open("config.json", "r") as f:
    CONFIG = json.load(f)

SENSOR_NAME = CONFIG.get("sensorName", "TorqueSensor")
SENSOR_MAC = CONFIG.get("sensorAddress", "00:00:00:00:00:00")
HX711_UUID = CONFIG.get("hx711UUID", "00000000-0000-0000-0000-000000000000")
class TorqueDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Torque Sensor Dashboard")
        self.setGeometry(200, 200, 900, 600)

        # --- Status & Torque Labels (side by side) ---
        self.status_label = QLabel("Status: Disconnected", self)
        self.status_label.setStyleSheet("color: #888; font-size:14px; padding:4px;")
        self.torque_label = QLabel("Torque: -- N·cm", self)
        self.torque_label.setStyleSheet("color: #00CC66; font-size:16px; font-weight:bold; padding:4px;")
        top_hbox = QHBoxLayout()
        top_hbox.addWidget(self.status_label)
        top_hbox.addStretch()
        top_hbox.addWidget(self.torque_label)

        # --- Real-time graph ---
        date_axis = DateAxisItem(orientation="bottom")
        self.graph = pg.PlotWidget(axisItems={"bottom": date_axis})
        self.graph.setBackground("black")
        self.graph.setTitle("Real-Time Torque", color="white", size="14pt")

        # --- Threshold slider ---
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(10, 200)
        self.slider.setValue(THRESHOLD_DEFAULT)
        self.slider.valueChanged.connect(self.on_threshold_changed)
        self.threshold_label = QLabel(f"Alert Threshold: {THRESHOLD_DEFAULT} N·cm")

        # --- Buttons ---
        self.btn_scan       = QPushButton("🔍 Scan BLE Sensors")
        self.btn_connect    = QPushButton("🔗 Connect & Start Readings")
        self.btn_export_csv = QPushButton("📄 Export CSV")
        self.btn_export_pdf = QPushButton("📄 Export PDF")
        self.btn_history    = QPushButton("📊 View History")
        self.btn_theme      = QPushButton("🌙 Toggle Theme")

        self.btn_scan.clicked.connect(self._start_thread(self.scan_ble_devices))
        self.btn_connect.clicked.connect(self._start_thread(self.connect_to_sensor))
        self.btn_export_csv.clicked.connect(self.export_csv)
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        self.btn_history.clicked.connect(self.plot_history)
        self.btn_theme.clicked.connect(self.toggle_theme)

        # --- Layout assembly ---
        main_vbox = QVBoxLayout()
        main_vbox.addLayout(top_hbox)
        main_vbox.addWidget(self.graph)
        main_vbox.addWidget(self.threshold_label)
        main_vbox.addWidget(self.slider)
        for w in (self.btn_scan, self.btn_connect,
                  self.btn_export_csv, self.btn_export_pdf,
                  self.btn_history, self.btn_theme):
            main_vbox.addWidget(w)

        container = QWidget()
        container.setLayout(main_vbox)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(container)
        self.setCentralWidget(splitter)

        # Dark theme
        self.setStyleSheet(qdarkstyle.load_stylesheet_pyqt6())

        # Graph update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_graph)
        self.timer.start(1000)

    def _start_thread(self, coro_fn):
        """Run an async method in a daemon thread."""
        def wrapper():
            asyncio.run(coro_fn())
        return lambda: threading.Thread(target=wrapper, daemon=True).start()

    async def scan_ble_devices(self):
        """Quick scan to list BLE devices in console."""
        self.status_label.setText("Status: Scanning…")
        devices = await BleakScanner.discover(timeout=5.0)
        for d in devices:
            print(f"{d.name or '—':20s} | {d.address} | {d.metadata.get('uuids')}")
        self.status_label.setText("Status: Scan complete")

    async def connect_to_sensor(self):
        """Directly connect on button click, then stream HX711 data."""
        self.status_label.setText("Status: Connecting…")
        client = None
        try:
            client = BleakClient(SENSOR_MAC)
            await client.connect(timeout=10.0)
            if not client.is_connected:
                self.status_label.setText("Status: Connection failed")
                return

            self.status_label.setText("Status: Connected ✓")
            while client.is_connected:
                try:
                    raw = await client.read_gatt_char(HX711_UUID)
                    val = int.from_bytes(raw, byteorder="little", signed=False)
                except Exception:
                    self.status_label.setText("Status: Read error")
                    await asyncio.sleep(1.0)
                    continue

                self.torque_label.setText(f"Torque: {val} N·cm")
                self._save(val)
                await asyncio.sleep(1.0)

        except Exception as e:
            self.status_label.setText(f"Status: BLE Error: {e}")
        finally:
            if client and client.is_connected:
                await client.disconnect()

    def update_graph(self):
        """Refresh the plot based on the last 50 records."""
        df = pd.read_sql(
            "SELECT * FROM torque_data ORDER BY timestamp DESC LIMIT 50",
            sqlite3.connect(DB_FILE)
        )
        if df.empty:
            return

        times = []
        for ts in df["timestamp"]:
            try:
                times.append(float(ts))
            except:
                times.append(pd.to_datetime(ts).timestamp())
        times = np.array(times)
        vals = df["torque_value"].to_numpy()

        latest = vals[-1]
        pen = pg.mkPen("green" if latest < self.slider.value() else "red", width=2)
        self.graph.clear()
        self.graph.plot(x=times, y=vals, pen=pen)

        # keep torque label color in sync
        if latest > self.slider.value():
            self.torque_label.setStyleSheet("color:red; font-weight:bold;")
        else:
            self.torque_label.setStyleSheet("color:green;")

    def on_threshold_changed(self):
        v = self.slider.value()
        self.threshold_label.setText(f"Alert Threshold: {v} N·cm")

    def export_csv(self):
        df = pd.read_sql("SELECT * FROM torque_data", sqlite3.connect(DB_FILE))
        df.to_csv("torque_data.csv", index=False)
        self.status_label.setText("Status: CSV exported")

    def export_pdf(self):
        c = canvas.Canvas("torque_data.pdf")
        c.drawString(100, 750, "Torque Sensor Report")
        df = pd.read_sql("SELECT * FROM torque_data", sqlite3.connect(DB_FILE))
        y = 720
        for _, r in df.iterrows():
            c.drawString(100, y, f"{r['timestamp']} – {r['torque_value']} N·cm")
            y -= 20
            if y < 50:
                c.showPage()
                y = 750
        c.save()
        self.status_label.setText("Status: PDF exported")

    def plot_history(self):
        df = pd.read_sql(
            "SELECT * FROM torque_data ORDER BY timestamp",
            sqlite3.connect(DB_FILE)
        )
        if df.empty:
            self.status_label.setText("Status: No data")
            return

        xt = pd.to_datetime(df["timestamp"])
        plt.figure(figsize=(8, 5))
        plt.plot(xt, df["torque_value"], marker="o")
        plt.xlabel("Time")
        plt.ylabel("Torque (N·cm)")
        plt.title("Torque History")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()

    def _save(self, val):
        """Insert into SQLite, guarding against overflow."""
        if not (-(2**63) <= val < 2**63):
            return
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS torque_data ("
            "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, torque_value INTEGER)"
        )
        conn.execute("INSERT INTO torque_data (torque_value) VALUES (?)", (val,))
        conn.commit()
        conn.close()

    def toggle_theme(self):
        if "dark" in self.styleSheet().lower():
            self.setStyleSheet("")  # light
        else:
            self.setStyleSheet(qdarkstyle.load_stylesheet_pyqt6())


if __name__ == "__main__":
    app    = QApplication(sys.argv)
    window = TorqueDashboard()
    window.show()
    sys.exit(app.exec())
