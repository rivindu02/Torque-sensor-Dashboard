#!/usr/bin/env python3
"""
Bluetooth Low Energy Receiver for 24-bit ADC Torque Sensor Data
Integrates with existing web UI dashboard
"""

import asyncio
from bleak import BleakClient, BleakScanner
from datetime import datetime
from flask import Flask, jsonify, send_from_directory
import csv
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import threading
import time

class BluetoothReceiver:
    def __init__(self):
        self.client = None
        self.is_connected = False
        self.is_running = False
        self.current_torque = 0.0
        self.data_history = []
        self.threshold = 50.0
        self.max_history = 1000

        # BLE configuration
        self.service_uuid = "12345678-1234-5678-1234-567812345678"
        self.rx_char_uuid = "87654321-4321-6789-4321-678943218765"

        # ADC Configuration (matching transmitter)
        self.adc_config = {
            'adc_bits': 24,
            'adc_max_value': 16777215,  # 2^24 - 1
            'voltage_min': 0.8e-3,      # 0.8mV
            'voltage_max': 1.1e-3,      # 1.1mV
            'neutral_voltage': 0.987e-3, # 0.987mV
            'torque_scale': 100.0       # N·cm per mV
        }

    async def discover_transmitters(self):
        """Discover BLE devices advertising the specified service UUID"""
        print(f"Scanning for BLE devices with service UUID {self.service_uuid}...")
        devices = await BleakScanner.discover(timeout=10.0)
        matching_devices = [
            d for d in devices
            if d.metadata.get('uuids') and self.service_uuid.lower() in [uuid.lower() for uuid in d.metadata['uuids']]
        ]
        print("\nMatching devices:")
        for d in matching_devices:
            print(f"  {d.address} - {d.name or 'Unknown'}")
        return matching_devices

    async def connect_to_transmitter(self):
        """Connect to the first transmitter with the specified service UUID"""
        try:
            devices = await self.discover_transmitters()
            if not devices:
                print("No transmitters found with the specified service UUID")
                return False

            device = devices[0]
            print(f"Connecting to {device.address}...")
            self.client = BleakClient(device.address, timeout=20.0)
            await self.client.connect()
            self.is_connected = await self.client.is_connected()
            
            if self.is_connected:
                print(f"Connected to {device.address}")
                return True
            else:
                print(f"Failed to connect to {device.address}")
                return False
                
        except Exception as e:
            print(f"Connection error: {e}")
            self.is_connected = False
            return False

    async def start_receiving(self):
        """Start receiving notifications from the transmitter"""
        if not self.is_connected:
            print("Not connected to transmitter")
            return {"status": "error", "message": "Not connected"}

        try:
            self.is_running = True
            # Subscribe to notifications
            await self.client.start_notify(self.rx_char_uuid, self._notification_handler)
            print("Started receiving notifications")
            return {"status": "started"}
        except Exception as e:
            print(f"Error starting receiver: {e}")
            self.is_running = False
            return {"status": "error", "message": str(e)}

    async def stop_receiving(self):
        """Stop receiving notifications"""
        self.is_running = False
        try:
            if self.client and self.is_connected:
                await self.client.stop_notify(self.rx_char_uuid)
                await self.client.disconnect()
            self.is_connected = False
            print("Stopped receiving")
            return {"status": "stopped"}
        except Exception as e:
            print(f"Stop error: {e}")
            return {"status": "error", "message": str(e)}

    def _notification_handler(self, sender, data):
        """Handle incoming notification data"""
        try:
            data_str = data.decode('utf-8').strip()
            adc_value = self._parse_adc_value(data_str)
            voltage = self._adc_to_voltage(adc_value)
            torque = self._voltage_to_torque(voltage)
            
            timestamp = datetime.now()
            self.current_torque = torque
            
            self.data_history.append({
                'timestamp': timestamp,
                'adc_value': adc_value,
                'voltage': voltage * 1000,  # mV
                'torque': torque
            })
            
            if len(self.data_history) > self.max_history:
                self.data_history.pop(0)
            
            print(f"Received - ADC: {adc_value}, Voltage: {voltage*1000:.3f}mV, Torque: {torque:.2f} N·cm")
            
        except Exception as e:
            print(f"Error processing data '{data_str}': {e}")

    def _parse_adc_value(self, data):
        """Parse ADC value from various formats"""
        data = data.strip()
        if data.startswith('0x') or data.startswith('0X'):
            return int(data, 16)
        elif data.startswith('0b') or data.startswith('0B'):
            return int(data, 2)
        else:
            return int(data)

    def _adc_to_voltage(self, adc_value):
        """Convert ADC value to voltage"""
        voltage = (
            (adc_value - self.adc_config['adc_min']) /
            (self.adc_config['adc_max'] - self.adc_config['adc_min']) *
            (self.adc_config['voltage_max'] - self.adc_config['voltage_min']) +
            self.adc_config['voltage_min']
        )
        return voltage

    def _voltage_to_torque(self, voltage):
        """Convert voltage to torque value"""
        voltage_offset = voltage - self.adc_config['neutral_voltage']
        torque = voltage_offset * self.adc_config['torque_scale'] * 1000  # Convert to N·cm
        return torque

    def get_status(self):
        """Get current connection status"""
        if self.is_connected and self.is_running:
            return "Connected"
        elif self.is_running:
            return "Waiting for connection"
        else:
            return "Disconnected"

    def get_torque_data(self):
        """Get current torque data"""
        return {
            'torque_value': round(self.current_torque, 2),
            'timestamp': datetime.now().isoformat(),
            'status': self.get_status()
        }

    def export_csv(self):
        """Export data history to CSV"""
        filename = f"torque_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['timestamp', 'adc_value', 'voltage_mv', 'torque_ncm']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for entry in self.data_history:
                writer.writerow({
                    'timestamp': entry['timestamp'].isoformat(),
                    'adc_value': entry['adc_value'],
                    'voltage_mv': entry['voltage'],
                    'torque_ncm': entry['torque']
                })
        return filename

    def export_pdf(self):
        """Export data history to PDF"""
        filename = f"torque_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        c = canvas.Canvas(filename, pagesize=letter)
        width, height = letter
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "Torque Sensor Data Report")
        c.setFont("Helvetica", 12)
        y = height - 100
        c.drawString(50, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        y -= 20
        c.drawString(50, y, f"Total Readings: {len(self.data_history)}")
        y -= 20
        if self.data_history:
            max_torque = max(entry['torque'] for entry in self.data_history)
            min_torque = min(entry['torque'] for entry in self.data_history)
            avg_torque = sum(entry['torque'] for entry in self.data_history) / len(self.data_history)
            c.drawString(50, y, f"Max Torque: {max_torque:.2f} N·cm")
            y -= 20
            c.drawString(50, y, f"Min Torque: {min_torque:.2f} N·cm")
            y -= 20
            c.drawString(50, y, f"Avg Torque: {avg_torque:.2f} N·cm")
        c.save()
        return filename

# Flask Web Server Integration
app = Flask(__name__)
receiver = BluetoothReceiver()

@app.route('/')
def index():
    return send_from_directory('.', 'transmitter.html')  # Serve the provided UI

@app.route('/transmitter.css')
def styles():
    return send_from_directory('.', 'transmitter.css')

@app.route('/transmitter.js')
def script():
    return send_from_directory('.', 'transmitter.js')

@app.route('/start', methods=['POST'])
def start_bluetooth():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(receiver.connect_to_transmitter())
    if result:
        loop.run_until_complete(receiver.start_receiving())
    loop.close()
    return jsonify(receiver.get_status())

@app.route('/stop', methods=['POST'])
def stop_bluetooth():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(receiver.stop_receiving())
    loop.close()
    return jsonify(result)

@app.route('/status')
def status():
    return jsonify({"status": receiver.get_status()})

@app.route('/torque')
def torque():
    return jsonify(receiver.get_torque_data())

@app.route('/export_csv')
def export_csv():
    filename = receiver.export_csv()
    return send_from_directory('.', filename, as_attachment=True)

@app.route('/export_pdf')
def export_pdf():
    filename = receiver.export_pdf()
    return send_from_directory('.', filename, as_attachment=True)

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    print("Starting Torque Sensor Bluetooth Receiver")
    print("========================================")
    print(f"Web Interface: http://localhost:5000")
    print(f"Service UUID: {receiver.service_uuid}")
    print("\nMake sure the transmitter is advertising the service UUID!")
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(receiver.stop_receiving())
        loop.close()