// static/script.js
// static/script.js
document.addEventListener("DOMContentLoaded", () => {
  const statusEl    = document.getElementById("status");
  const torqueEl    = document.getElementById("torque");
  const graphEl     = document.getElementById("graph");
  const threshInput = document.getElementById("threshold");
  const threshVal   = document.getElementById("thresh-val");
  const histModal   = document.getElementById("history-modal");
  const histGraph   = document.getElementById("history-graph");

  // Persist threshold
  threshInput.value = localStorage.getItem("threshold")||50;
  threshVal.innerText = threshInput.value;
  threshInput.oninput = () => {
    threshVal.innerText = threshInput.value;
    localStorage.setItem("threshold", threshInput.value);
  };

  // Start BLE reader
  document.getElementById("btn-start").onclick = () => {
    fetch("/start");
  };

  // Periodic updates
  setInterval(() => {
    fetch("/status").then(r=>r.json()).then(j=>statusEl.innerText = "Status: " + j.status);
    fetch("/torque").then(r=>r.json()).then(j=>{
      torqueEl.innerText = j.torque_value ?? "--";
      torqueEl.style.color = (j.torque_value > threshInput.value) ? "tomato" : "#00CC66";
      Plotly.react(graphEl, [{
        x: [new Date()],
        y: [j.torque_value],
        mode:"lines+markers",
        marker:{ color: (j.torque_value>threshInput.value)?"tomato":"#00CC66" }
      }], { margin:{t:30}, title:"Real-Time Torque" });
    });
  }, 2000);

  // Export buttons
  document.getElementById("export-csv").onclick = ()=> location.href="/export_csv";
  document.getElementById("export-pdf").onclick = ()=> location.href="/export_pdf";

  // History modal
  document.getElementById("view-history").onclick = ()=>{
    fetch("/history").then(r=>r.json()).then(data=>{
      Plotly.newPlot(histGraph, [{
        x: data.map(d=>new Date(d.t)),
        y: data.map(d=>d.v),
        mode:"lines", line:{shape:"hv"}
      }], { margin:{t:30}, title:"Last 100 Readings" });
      histModal.style.display = "block";
    });
  };
  document.getElementById("close-modal").onclick = ()=> histModal.style.display="none";

  // Theme toggle
  document.getElementById("toggle-theme").onclick = ()=>{
    document.body.classList.toggle("dark-mode");
  };
});
