// BLE Configuration - Using exact UUIDs from your MCU code
// BLE Configuration - Verified UUIDs
const TORQUE_SERVICE_UUID = '18424398-7cbc-11e9-8f9e-2a86e4085a59';
const TORQUE_CHARACTERISTIC_UUID = '0000fff1-0000-1000-8000-00805f9b34fb'; // Temporary generic UUID

// Global variables
let torqueSensorDevice = null;
let torqueCharacteristic = null;
let torqueChart = null;
let dataPoints = [];
const MAX_DATA_POINTS = 100;
let keepAliveInterval = null;

// Initialize Chart
function initChart() {
    const ctx = document.getElementById('torqueChart').getContext('2d');
    torqueChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Array(MAX_DATA_POINTS).fill(''),
            datasets: [{
                label: 'Torque (Nm)',
                data: Array(MAX_DATA_POINTS).fill(null),
                borderColor: 'rgb(75, 192, 192)',
                tension: 0.1
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: false
                }
            },
            animation: {
                duration: 0
            }
        }
    });
}

// Update chart with new data
function updateChart(value) {
    dataPoints.push(value);
    if (dataPoints.length > MAX_DATA_POINTS) {
        dataPoints.shift();
    }
    torqueChart.data.datasets[0].data = dataPoints;
    torqueChart.update();
}

// Fallback polling function
function startPolling() {
    const poll = async () => {
        if (!torqueSensorDevice?.gatt?.connected) return;
        
        try {
            const value = await torqueCharacteristic.readValue();
            handleTorqueNotification({ target: { value } });
            setTimeout(poll, 100); // Poll every 100ms
        } catch (error) {
            console.error('Polling error:', error);
            setTimeout(poll, 1000); // Retry after delay
        }
    };
    poll();
}

// Handle torque data
function handleTorqueNotification(event) {
    try {
        const value = event.target.value;
        if (!value || value.byteLength < 2) {
            console.warn('Invalid data length');
            return;
        }
        
        // Assuming little-endian 16-bit unsigned int
        const rawValue = value.getUint16(0, true); 
        const torque = rawValue / 1000.0; // Adjust scaling as needed
        
        document.getElementById('torqueValue').textContent = `Torque: ${torque.toFixed(3)} Nm`;
        updateChart(torque);
        
    } catch (error) {
        console.error('Data processing error:', error);
    }
}

// Enhanced Connection Function
// Enhanced connection function with characteristic discovery
async function connectToSensor() {
    try {
        console.log('Requesting Bluetooth Device...');
        torqueSensorDevice = await navigator.bluetooth.requestDevice({
            filters: [{ name: 'Torque Sensor' }],
            optionalServices: [TORQUE_SERVICE_UUID]
        });

        torqueSensorDevice.addEventListener('gattserverdisconnected', onDisconnected);
        
        console.log('Connecting to GATT Server...');
        const server = await torqueSensorDevice.gatt.connect();
        
        console.log('Getting Service...');
        const service = await server.getPrimaryService(TORQUE_SERVICE_UUID);
        
        console.log('Discovering All Characteristics...');
        const characteristics = await service.getCharacteristics();
        
        // Debug: List all characteristics
        console.log('Available Characteristics:');
        characteristics.forEach((char, idx) => {
            console.log(`#${idx}: UUID=${char.uuid}, Properties=${JSON.stringify(char.properties)}`);
        });

        // Find the correct characteristic by properties
        torqueCharacteristic = characteristics.find(c => 
            c.properties.notify ||  // Prefer notify
            c.properties.read      // Fallback to readable
        );
        
        if (!torqueCharacteristic) {
            throw new Error('No suitable characteristic found for torque readings');
        }

        console.log('Using Characteristic:', torqueCharacteristic.uuid);
        
        // Enable notifications if available
        if (torqueCharacteristic.properties.notify) {
            await torqueCharacteristic.startNotifications();
            torqueCharacteristic.addEventListener('characteristicvaluechanged', handleTorqueNotification);
        } else {
            // Fallback to polling if notifications not available
            startPolling();
        }
        
        updateStatus(true);
        document.getElementById('connectBtn').disabled = true;
        document.getElementById('disconnectBtn').disabled = false;
        
    } catch (error) {
        console.error('Connection failed:', error);
        alert(`Connection failed: ${error.message}\n\nFound characteristics:\n${
            characteristics ? characteristics.map(c => c.uuid).join('\n') : 'none'
        }`);
        onDisconnected();
    }
}

// Robust notification setup
async function setupNotifications() {
    try {
        await torqueCharacteristic.startNotifications();
        
        const notificationHandler = (event) => {
            try {
                const value = event.target.value;
                if (!value || value.byteLength < 2) {
                    console.warn('Invalid notification data');
                    return;
                }
                
                // Read as little-endian 16-bit unsigned int
                const rawValue = value.getUint16(0, true); 
                
                // Convert to torque (adjust scaling as needed)
                const torque = rawValue / 1000.0; 
                
                // Update UI
                document.getElementById('torqueValue').textContent = `Torque: ${torque.toFixed(3)} Nm`;
                updateChart(torque);
                
            } catch (error) {
                console.error('Error processing notification:', error);
                // Attempt to reconnect
                setTimeout(reconnect, 1000);
            }
        };
        
        torqueCharacteristic.addEventListener('characteristicvaluechanged', notificationHandler);
        
    } catch (error) {
        console.error('Notification setup failed:', error);
        throw error;
    }
}

// Reconnection logic
function reconnect() {
    if (torqueSensorDevice && torqueSensorDevice.gatt.connected) {
        return;
    }
    console.log('Attempting to reconnect...');
    connectToSensor();
}

// Disconnection handler
function onDisconnected() {
    console.log('Disconnected callback triggered');
    
    // Clean up
    if (keepAliveInterval) {
        clearInterval(keepAliveInterval);
        keepAliveInterval = null;
    }
    
    if (torqueCharacteristic) {
        try {
            torqueCharacteristic.removeEventListener('characteristicvaluechanged', handleTorqueNotification);
        } catch (e) {
            console.warn('Error removing listener:', e);
        }
        torqueCharacteristic = null;
    }
    
    // Update UI
    updateStatus(false);
    document.getElementById('connectBtn').disabled = false;
    document.getElementById('disconnectBtn').disabled = true;
    
    // Attempt to reconnect automatically
    setTimeout(reconnect, 2000);
}

// Manual disconnect
function disconnectFromSensor() {
    if (!torqueSensorDevice) return;
    
    if (torqueSensorDevice.gatt.connected) {
        torqueSensorDevice.gatt.disconnect();
    }
    onDisconnected();
}

// Update connection status UI
function updateStatus(connected) {
    const statusElement = document.getElementById('status');
    if (connected) {
        statusElement.textContent = 'Connected to Torque Sensor';
        statusElement.className = 'status connected';
    } else {
        statusElement.textContent = 'Disconnected';
        statusElement.className = 'status disconnected';
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initChart();
    
    document.getElementById('connectBtn').addEventListener('click', connectToSensor);
    document.getElementById('disconnectBtn').addEventListener('click', disconnectFromSensor);
    
    // Check if Web Bluetooth is supported
    if (!navigator.bluetooth) {
        alert('Web Bluetooth API is not available in this browser!');
        document.getElementById('connectBtn').disabled = true;
    }
});