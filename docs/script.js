async function update() {
    const res = await fetch('data/kalshi_summary.json?t=' + Date.now());
    const data = await res.json();
    document.getElementById('target-val').innerText = data.target_temp + "°F";
    document.getElementById('bet-status').innerHTML = data.active_bet 
        ? `Currently Holding: <span class="status">${data.active_bet}</span><br>Targeting 25% Profit Exit`
        : "No active positions. Waiting for 10 AM Snipe.";
}
update();
setInterval(update, 60000);
