async function updateDashboard() {
    try {
        const res = await fetch('data/kalshi_summary.json?t=' + Date.now());
        const data = await res.json();
        
        document.getElementById('target-val').innerText = data.target_temp + "°F";
        
        const betStatus = document.getElementById('bet-status');
        if (data.active_bet) {
            betStatus.innerHTML = `LIVE POSITION: <span class="status">${data.active_bet}</span><br>Monitoring for 25% Profit Exit...`;
        } else {
            betStatus.innerText = "No active trades. Sniper waiting for 10:00 AM EST Market Open.";
        }
    } catch (e) {
        console.log("Waiting for data...");
    }
}
updateDashboard();
setInterval(updateDashboard, 60000);
