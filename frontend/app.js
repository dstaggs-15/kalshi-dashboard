document.addEventListener("DOMContentLoaded", () => {
    // LOCATION FIX: 
    // Since index.html is in 'frontend/' and the json is in 'frontend/data/',
    // we use the relative path 'data/kalshi_summary.json'.
    const dataPath = 'data/kalshi_summary.json';
    
    // We add a timestamp (?t=...) to force the browser to load new data 
    // instead of showing cached zeros.
    fetch(`${dataPath}?t=${new Date().getTime()}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Could not find file at ${dataPath}`);
            }
            return response.json();
        })
        .then(data => renderDashboard(data))
        .catch(err => {
            console.error("Error loading data:", err);
            document.getElementById('narrative-text').innerHTML = 
                `<span style="color: red;">Error: Could not read data.<br>
                Looking for: <strong>frontend/${dataPath}</strong></span>`;
        });
});

function formatMoney(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

function renderDashboard(data) {
    const acc = data.account;
    const sum = data.summary;

    // 1. HEADER
    document.getElementById('last-updated').innerText = "Updated: " + data.meta.updated_at;
    document.getElementById('hero-total-val').innerText = formatMoney(acc.total_account_value);
    
    const profitElem = document.getElementById('hero-profit');
    profitElem.innerText = formatMoney(sum.net_profit);
    profitElem.className = sum.net_profit >= 0 ? "hero-value positive" : "hero-value negative";

    // 2. CARDS
    document.getElementById('val-deposits').innerText = formatMoney(sum.total_deposits);
    document.getElementById('val-cash').innerText = formatMoney(acc.cash_balance);
    document.getElementById('val-bets').innerText = formatMoney(acc.money_in_bets);
    
    const roiElem = document.getElementById('val-roi');
    roiElem.innerText = sum.roi_percent.toFixed(1) + "%";
    roiElem.className = sum.roi_percent >= 0 ? "metric-value positive" : "metric-value negative";

    // 3. NARRATIVE
    const narrative = `
        You have put in <strong>${formatMoney(sum.total_deposits)}</strong>. 
        You currently have <strong>${formatMoney(acc.cash_balance)}</strong> in cash and 
        <strong>${formatMoney(acc.money_in_bets)}</strong> in active bets.
    `;
    document.getElementById('narrative-text').innerHTML = narrative;

    // 4. TRADES TABLE
    const fillsTable = document.querySelector('#fills-table tbody');
    fillsTable.innerHTML = '';
    
    if (data.fills && data.fills.length > 0) {
        data.fills.slice(0, 10).forEach(f => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${new Date(f.created_time).toLocaleDateString()}</td>
                <td>${f.ticker}</td>
                <td>${f.side}</td>
                <td>${f.count}</td>
                <td>${f.price_cents}¢</td>
            `;
            fillsTable.appendChild(row);
        });
    } else {
        fillsTable.innerHTML = '<tr><td colspan="5">No trades found in JSON.</td></tr>';
    }

    // 5. SETTLEMENTS TABLE
    const setTable = document.querySelector('#settlements-table tbody');
    setTable.innerHTML = '';
    
    if (data.settlements && data.settlements.length > 0) {
        data.settlements.slice(0, 10).forEach(s => {
            const row = document.createElement('tr');
            const payout = (s.received_cents / 100).toFixed(2);
            row.innerHTML = `
                <td>${new Date(s.settled_time).toLocaleDateString()}</td>
                <td>${s.ticker}</td>
                <td>${s.outcome}</td>
                <td>$${payout}</td>
            `;
            setTable.appendChild(row);
        });
    } else {
        setTable.innerHTML = '<tr><td colspan="4">No settlements found in JSON.</td></tr>';
    }
}
