async function loadQuantData() {
    try {
        const response = await fetch('frontend/data/kalshi_summary.json');
        const data = await response.json();

        document.getElementById('temp-val').innerText = `${data.forecast.mu}°F`;
        document.getElementById('sigma-val').innerText = `Confidence: ±${data.forecast.sigma}`;
        document.getElementById('status-badge').innerText = data.dry_run ? "PAPER TRADING" : "LIVE";
        document.getElementById('status-badge').style.background = data.dry_run ? "#f59e0b" : "#10b981";

        const list = document.getElementById('trade-list');
        if (data.recommendations.length > 0) {
            document.getElementById('edge-count').innerText = data.recommendations.length;
            list.innerHTML = data.recommendations.map(t => `
                <div class="trade-item">
                    <span><strong>${t.ticker}</strong> ($${t.price})</span>
                    <span class="edge-pill">+${(t.edge * 100).toFixed(1)}% Edge</span>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error("Data not ready yet.");
    }
}
setInterval(loadQuantData, 5000); // Refresh every 5 seconds
loadQuantData();
