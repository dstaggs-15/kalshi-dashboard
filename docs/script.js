async function refreshData() {
    try {
        // Look in the data folder directly next to index.html
        const res = await fetch('data/kalshi_summary.json?t=' + new Date().getTime());
        const data = await res.json();

        document.getElementById('temp-val').innerText = `${data.forecast.mu}°F`;
        document.getElementById('sigma-val').innerText = `Uncertainty: ±${data.forecast.sigma}`;
        document.getElementById('update-text').innerText = `Last Pulse: ${data.last_updated}`;
        
        const badge = document.getElementById('status-badge');
        badge.innerText = data.dry_run ? "DRY RUN" : "LIVE";
        badge.style.background = data.dry_run ? "#f59e0b" : "#10b981";

        const list = document.getElementById('trade-list');
        if (data.recommendations.length > 0) {
            list.innerHTML = data.recommendations.map(t => `
                <div class="trade-item">
                    <span><strong>${t.ticker}</strong> ($${t.price.toFixed(2)})</span>
                    <span class="edge-pill">+${(t.edge * 100).toFixed(1)}% Edge</span>
                </div>
            `).join('');
        } else {
            list.innerHTML = "<p>No trades meet the edge threshold right now.</p>";
        }
    } catch (e) {
        console.log("Waiting for bot data...");
    }
}
setInterval(refreshData, 10000);
refreshData();
