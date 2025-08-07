// static/script.js
document.addEventListener("DOMContentLoaded", () => {
  const statusEl    = document.getElementById("status");
  const torqueEl    = document.getElementById("torque");
  const graphEl     = document.getElementById("graph");
  const threshInput = document.getElementById("threshold");
  const threshVal   = document.getElementById("thresh-val");

  // Persist threshold
  threshInput.value = localStorage.getItem("threshold")||50;
  threshVal.innerText = threshInput.value;
  threshInput.oninput = () => {
    threshVal.innerText = threshInput.value;
    localStorage.setItem("threshold", threshInput.value);
  };

  // Start BLE reader
  document.getElementById("btn-start").onclick = () => {
    fetch("/start")
      .then(r => r.json())
      .then(data => {
        console.log("Start response:", data);
        statusEl.innerText = "Status: " + data.status;
      })
      .catch(err => console.error("Start error:", err));
  };

  // Stop BLE reader
  const stopBtn = document.getElementById("btn-stop");
  if (stopBtn) {
    stopBtn.onclick = () => {
      fetch("/stop")
        .then(r => r.json())
        .then(data => {
          console.log("Stop response:", data);
          statusEl.innerText = "Status: " + data.status;
        })
        .catch(err => console.error("Stop error:", err));
    };
  }

  // Periodic updates
  setInterval(() => {
    fetch("/status")
      .then(r => r.json())
      .then(j => statusEl.innerText = "Status: " + j.status)
      .catch(err => console.error("Status fetch error:", err));
    
    fetch("/torque")
      .then(r => r.json())
      .then(j => {
        torqueEl.innerText = j.torque_value ?? "--";
        torqueEl.style.color = (j.torque_value > threshInput.value) ? "tomato" : "#00CC66";
        
        // Update real-time graph if Plotly is available
        if (typeof Plotly !== 'undefined' && graphEl) {
          Plotly.react(graphEl, [{
            x: [new Date()],
            y: [j.torque_value],
            mode:"lines+markers",
            marker:{ color: (j.torque_value > threshInput.value) ? "tomato" : "#00CC66" }
          }], { margin:{t:30}, title:"Real-Time Torque" });
        }
      })
      .catch(err => console.error("Torque fetch error:", err));
  }, 2000);

  // Export buttons
  const csvBtn = document.getElementById("export-csv");
  if (csvBtn) {
    csvBtn.onclick = () => {
      console.log("CSV export clicked");
      window.location.href = "/export_csv";
    };
  }

  const pdfBtn = document.getElementById("export-pdf");
  if (pdfBtn) {
    pdfBtn.onclick = () => {
      console.log("PDF export clicked");
      window.location.href = "/export_pdf";
    };
  }

  // Theme toggle
  const themeBtn = document.getElementById("toggle-theme");
  if (themeBtn) {
    themeBtn.onclick = () => {
      console.log("Theme toggle clicked");
      document.body.classList.toggle("dark-mode");
      
      // Save theme preference
      const isDark = document.body.classList.contains("dark-mode");
      localStorage.setItem("theme", isDark ? "dark" : "light");
    };
  }

  // Load saved theme
  const savedTheme = localStorage.getItem("theme");
  if (savedTheme === "dark") {
    document.body.classList.add("dark-mode");
  }
});
