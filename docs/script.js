let chartInstance = null;
async function refresh() {
    const res = await fetch('data/kalshi_summary.json?t=' + Date.now());
    const data = await res.json();
    document.getElementById('temp-val').innerText = `${data.forecast.mu}°F`;
    document.getElementById('sigma-val').innerText = `Confidence: ±${data.forecast.sigma}`;
    
    if(data.recommendations.length > 0) {
        const best = data.recommendations[0];
        document.getElementById('bet-action').innerText = `BUY: ${best.ticker}`;
        document.getElementById('bet-details').innerText = `Bought at $${best.price.toFixed(2)} | Target Sell: $${(best.price * 1.2).toFixed(2)}`;
    }
    renderGraph(data.forecast.mu, data.forecast.sigma);
}

function renderGraph(mu, sigma) {
    const ctx = document.getElementById('probChart').getContext('2d');
    const labels = [], points = [];
    for (let x = mu - 10; x <= mu + 10; x += 0.5) {
        labels.push(x);
        points.push((1 / (sigma * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * Math.pow((x - mu) / sigma, 2)));
    }
    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{ label: 'Probability', data: points, borderColor: '#58a6ff', fill: true, backgroundColor: 'rgba(88,166,255,0.1)' }]
        },
        options: { scales: { y: { display: false } }, plugins: { legend: { display: false } } }
    });
}
refresh();
