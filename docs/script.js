let chartInstance = null;

async function refreshDashboard() {
    try {
        const res = await fetch('data/kalshi_summary.json?t=' + Date.now());
        const data = await res.json();

        // 1. Update Basic Info
        document.getElementById('temp-val').innerText = data.forecast.mu;
        document.getElementById('uncertainty-desc').innerText = `Uncertainty: ±${data.forecast.sigma}°F (95% range: ${data.forecast.mu - 5} - ${data.forecast.mu + 5})`;
        document.getElementById('target-date').innerText = `Market Target: KLAX Daily High (${data.last_updated.split(' ')[0]})`;
        
        const badge = document.getElementById('status-badge');
        badge.innerText = data.dry_run ? "PAPER TRADING" : "LIVE BOT";
        badge.style.background = data.dry_run ? "#d29922" : "#238636";

        // 2. Display Best Bet
        const actionBox = document.getElementById('best-bet-action');
        const details = document.getElementById('bet-details');
        if (data.recommendations.length > 0) {
            const best = data.recommendations[0];
            actionBox.innerText = `BUY YES: ${best.ticker}`;
            details.innerText = `Entering at $${best.price} | Target Sell: $${(best.price * 1.2).toFixed(2)} (+20%)`;
        } else {
            actionBox.innerText = "HOLD / NO EDGE";
            details.innerText = "Market prices are currently too efficient to profit.";
        }

        // 3. Render Graph
        renderGraph(data.forecast.mu, data.forecast.sigma);

        // 4. List Trades
        const list = document.getElementById('trade-list');
        list.innerHTML = data.recommendations.map(t => `
            <div class="trade-item">
                <div><strong>${t.ticker}</strong><br><small>Entry: $${t.price}</small></div>
                <div class="edge-pill">+${(t.edge * 100).toFixed(1)}% Edge</div>
            </div>
        `).join('');

    } catch (e) { console.error("Data fetch error", e); }
}

function renderGraph(mu, sigma) {
    const ctx = document.getElementById('probChart').getContext('2d');
    const labels = [];
    const points = [];
    
    // Create points for a bell curve
    for (let x = mu - 10; x <= mu + 10; x += 0.5) {
        labels.push(x + "°");
        const val = (1 / (sigma * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * Math.pow((x - mu) / sigma, 2));
        points.push(val);
    }

    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Probability Density',
                data: points,
                borderColor: '#58a6ff',
                backgroundColor: 'rgba(88, 166, 255, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: { plugins: { legend: { display: false } }, scales: { y: { display: false } } }
    });
}

setInterval(refreshDashboard, 30000);
refreshDashboard();
