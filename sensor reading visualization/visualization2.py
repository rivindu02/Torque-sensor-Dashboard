import sys
import sqlite3
import pandas as pd
import pyqtgraph as pg
import qdarkstyle
import matplotlib.pyplot as plt
import asyncio
from bleak import BleakClient, BleakScanner
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QWidget, QSlider, QSplitter
from PyQt6.QtCore import QTimer, Qt
from mpl_toolkits.mplot3d import Axes3D
from reportlab.pdfgen import canvas

# BLE Sensor Configuration
SENSOR_ADDRESS = "XX:XX:XX:XX:XX:XX"  # Replace with sensor's MAC address
CHARACTERISTIC_UUID = "0000xxxx-0000-1000-8000-00805f9b34fb"  # Replace with correct UUID

# Database File
DB_FILE = "torque_data.db"
THRESHOLD = 100  # Default torque alert limit

class TorqueDashboard(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Torque Sensor Dashboard")
        self.setGeometry(200, 200, 900, 600)

        # UI Elements
        self.label = QLabel("Torque Value: Waiting for data...", self)
        self.label.setStyleSheet("color: #00CC66; font-size: 16px; font-weight: bold; padding: 8px;")

        self.graph = pg.PlotWidget()
        self.graph.setBackground("black")
        self.graph.setTitle("Real-Time Torque Graph", color="white", size="14pt")

        self.button_export_csv = QPushButton("📄 Export as CSV")
        self.button_export_csv.clicked.connect(self.export_csv)

        self.button_export_pdf = QPushButton("📄 Export as PDF")
        self.button_export_pdf.clicked.connect(self.export_pdf)

        self.button_toggle_theme = QPushButton("🌙 Toggle Theme")
        self.button_toggle_theme.clicked.connect(self.switch_theme)

        self.slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self.slider_threshold.setMinimum(10)
        self.slider_threshold.setMaximum(200)
        self.slider_threshold.setValue(THRESHOLD)
        self.slider_threshold.valueChanged.connect(self.update_threshold)
        self.label_slider = QLabel(f"Alert Threshold: {THRESHOLD} Ncm")

        self.button_plot_history = QPushButton("📊 View Historical Data")
        self.button_plot_history.clicked.connect(self.plot_torque_history)

        self.button_scan_ble = QPushButton("🔍 Scan BLE Sensors")
        self.button_scan_ble.clicked.connect(self.scan_ble_devices)

        self.button_connect_ble = QPushButton("🔗 Connect & Start Readings")
        self.button_connect_ble.clicked.connect(self.connect_to_ble_sensor)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.graph)
        layout.addWidget(self.label_slider)
        layout.addWidget(self.slider_threshold)
        layout.addWidget(self.button_export_csv)
        layout.addWidget(self.button_export_pdf)
        layout.addWidget(self.button_toggle_theme)
        layout.addWidget(self.button_plot_history)
        layout.addWidget(self.button_scan_ble)
        layout.addWidget(self.button_connect_ble)

        container = QWidget()
        container.setLayout(layout)

        # Splitter for Drag & Drop UI
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(container)

        self.setCentralWidget(splitter)

        # Apply Dark Theme by default
        self.setStyleSheet(qdarkstyle.load_stylesheet_pyqt6())

        # Timer for real-time updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_graph)
        self.timer.start(1000)  # Updates every second

    async def scan_ble_devices(self):
        """Scan for BLE devices."""
        devices = await BleakScanner.discover()
        for device in devices:
            print(f"Found: {device.name} | Address: {device.address}")

    async def connect_to_ble_sensor(self):
        """Connect to BLE Torque Sensor and fetch real-time data."""
        async with BleakClient(SENSOR_ADDRESS) as client:
            while True:
                value = await client.read_gatt_char(CHARACTERISTIC_UUID)
                torque_value = int.from_bytes(value, byteorder="little")
                self.save_torque_value(torque_value)
                await asyncio.sleep(2)  # Adjust based on sensor update rate

    def plot_torque_history(self):
        """Plot historical torque readings in 2D and 3D."""
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql("SELECT * FROM torque_data ORDER BY timestamp ASC", conn)
        conn.close()

        if df.empty:
            self.label.setText("❌ No historical data to plot.")
            return

        # 2D Graph
        plt.style.use("seaborn-dark")
        plt.figure(figsize=(8, 5))
        plt.plot(df['timestamp'], df['torque_value'], marker="o", linestyle="-", color="b", label="Torque Readings")
        plt.xlabel("Time")
        plt.ylabel("Torque Value (Ncm)")
        plt.title("Torque Sensor Data Over Time")
        plt.xticks(rotation=45)
        plt.legend()
        plt.show()

        # 3D Graph
        fig = plt.figure()
        ax = fig.add_subplot(111, projection="3d")
        ax.scatter(df["timestamp"], df["torque_value"], df.index, c="blue")
        ax.set_xlabel("Time")
        ax.set_ylabel("Torque")
        ax.set_zlabel("Data Point")
        plt.show()


    def update_graph(self):
        """Fetch real-time torque data and update graph with alerts."""
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql("SELECT * FROM torque_data ORDER BY timestamp DESC LIMIT 50", conn)
        conn.close()

        if not df.empty:
            latest_value = df.iloc[-1]["torque_value"]
            self.graph.clear()
            self.graph.plot(df["timestamp"], df["torque_value"], pen=pg.mkPen("green" if latest_value < THRESHOLD else "red", width=2))

            if latest_value > THRESHOLD:
                self.label.setStyleSheet("color: red; font-weight: bold;")
                self.label.setText(f"⚠️ HIGH TORQUE: {latest_value} Ncm")
            else:
                self.label.setStyleSheet("color: green;")
                self.label.setText(f"Torque Value: {latest_value} Ncm")

    def update_threshold(self):
        """Update torque alert threshold."""
        global THRESHOLD
        THRESHOLD = self.slider_threshold.value()
        self.label_slider.setText(f"Alert Threshold: {THRESHOLD} Ncm")

    def export_csv(self):
        """Export data to CSV."""
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql("SELECT * FROM torque_data", conn)
        conn.close()
        df.to_csv("torque_data.csv", index=False)
        self.label.setText("✅ Data exported to torque_data.csv")

    def export_pdf(self):
        """Export data to PDF."""
        c = canvas.Canvas("torque_data.pdf")
        c.drawString(100, 750, "Torque Sensor Readings Report")
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql("SELECT * FROM torque_data", conn)
        conn.close()
        
        y = 700
        for index, row in df.iterrows():
            c.drawString(100, y, f"{row['timestamp']} - {row['torque_value']} Ncm")
            y -= 20
        
        c.save()
        self.label.setText("✅ Data exported to torque_data.pdf")

    def switch_theme(self):
        """Toggle between light and dark themes."""
        current_style = self.styleSheet()
        if "dark" in current_style:
            self.setStyleSheet("")  # Light mode
        else:
            self.setStyleSheet(qdarkstyle.load_stylesheet_pyqt6())  # Dark mode

app = QApplication(sys.argv)
window = TorqueDashboard()
window.show()
sys.exit(app.exec())