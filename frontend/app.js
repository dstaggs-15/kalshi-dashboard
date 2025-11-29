document.addEventListener("DOMContentLoaded", () => {
    fetch('data/kalshi_summary.json')
        .then(response => {
            if (!response.ok) throw new Error("Could not find data file");
            return response.json();
        })
        .then(data => renderDashboard(data))
        .catch(err => console.error("Error loading data:", err));
});

function formatMoney(amount) {
    // Determine color class based on sign
    const num = parseFloat(amount);
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(num);
}

function renderDashboard(data) {
    const acc = data.account;
    const sum = data.summary;

    // 1. UPDATE HEADER
    document.getElementById('last-updated').innerText = "Updated: " + data.meta.updated_at;
    document.getElementById('hero-total-val').innerText = formatMoney(acc.total_account_value);
    
    // Profit Color Logic
    const profitElem = document.getElementById('hero-profit');
    profitElem.innerText = formatMoney(sum.net_profit);
    profitElem.className = sum.net_profit >= 0 ? "hero-value positive" : "hero-value negative";

    // 2. UPDATE CARDS
    document.getElementById('val-deposits').innerText = formatMoney(sum.total_deposits);
    document.getElementById('val-cash').innerText = formatMoney(acc.cash_balance);
    document.getElementById('val-bets').innerText = formatMoney(acc.money_in_bets);
    
    const roiElem = document.getElementById('val-roi');
    roiElem.innerText = sum.roi_percent + "%";
    roiElem.className = sum.roi_percent >= 0 ? "metric-value positive" : "metric-value negative";

    // 3. GENERATE NARRATIVE
    const narrativeText = `
        You have put in <strong>${formatMoney(sum.total_deposits)}</strong>. 
        Right now, you have <strong>${formatMoney(acc.cash_balance)}</strong> in cash and 
        <strong>${formatMoney(acc.money_in_bets)}</strong> in active bets. 
        Your total account value is <strong>${formatMoney(acc.total_account_value)}</strong>.
    `;
    document.getElementById('narrative-text').innerHTML = narrativeText;

    // 4. POPULATE TRADES TABLE
    const fillsTable = document.querySelector('#fills-table tbody');
    fillsTable.innerHTML = '';
    data.fills.slice(0, 10).forEach(fill => {
        const row = document.createElement('tr');
        // Parse date for display
        const dateStr = new Date(fill.created_time).toLocaleDateString();
        row.innerHTML = `
            <td>${dateStr}</td>
            <td>${fill.ticker}</td>
            <td>${fill.side.toUpperCase()}</td>
            <td>${fill.count}</td>
            <td>${fill.price_cents}¢</td>
        `;
        fillsTable.appendChild(row);
    });

    // 5. POPULATE SETTLEMENTS TABLE
    const setTable = document.querySelector('#settlements-table tbody');
    setTable.innerHTML = '';
    if (data.settlements.length === 0) {
        setTable.innerHTML = '<tr><td colspan="4">No recent settlements found.</td></tr>';
    } else {
        data.settlements.slice(0, 10).forEach(s => {
            const row = document.createElement('tr');
            const dateStr = new Date(s.settled_time).toLocaleDateString();
            const payout = (s.received_cents / 100).toFixed(2);
            row.innerHTML = `
                <td>${dateStr}</td>
                <td>${s.ticker}</td>
                <td>${s.outcome}</td>
                <td>$${payout}</td>
            `;
            setTable.appendChild(row);
        });
    }
}
