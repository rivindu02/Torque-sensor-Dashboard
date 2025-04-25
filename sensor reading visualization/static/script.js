document.addEventListener("DOMContentLoaded", function () {
    let thresholdInput = document.getElementById("threshold");
    let thresholdValue = document.getElementById("threshold-value");

    thresholdInput.addEventListener("input", function () {
        thresholdValue.innerText = thresholdInput.value + " Nm";
        localStorage.setItem("threshold", thresholdInput.value);
    });

    fetchTorqueData();
    setInterval(fetchTorqueData, 2000);
});

function fetchTorqueData() {
    fetch("/torque")
        .then(response => response.json())
        .then(data => {
            document.getElementById("torque-value").innerText = data.torque_value;
            updateGraph(data.torque_value);
        });
}

function updateGraph(torqueValue) {
    let trace = {
        x: [new Date()],
        y: [torqueValue],
        mode: "lines+markers",
        marker: { color: torqueValue > localStorage.getItem("threshold") ? "red" : "green" }
    };

    Plotly.newPlot("graph", [trace], { title: "Real-Time Torque Readings" });
}

document.getElementById("export-csv-button").addEventListener("click", function () {
    window.location.href = "/export_csv";
});

document.getElementById("export-pdf-button").addEventListener("click", function () {
    window.location.href = "/export_pdf";
});

function toggleTheme() {
    document.body.classList.toggle("dark-mode");
}