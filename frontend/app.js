document.addEventListener("DOMContentLoaded", () => {
    // DIAGNOSTIC STEP 1: Define the path
    // Since index.html is in 'frontend', looking for 'data' inside 'frontend'
    const dataPath = 'data/kalshi_summary.json';
    
    console.log("Attempting to fetch data from:", dataPath);

    fetch(`${dataPath}?t=${new Date().getTime()}`)
        .then(response => {
            // DIAGNOSTIC STEP 2: Check if file exists
            if (!response.ok) {
                throw new Error(`HTTP Error: ${response.status} - File not found at ${response.url}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Data loaded successfully:", data); // Check Console (F12) to see this
            renderDashboard(data);
        })
        .catch(err => {
            console.error("CRITICAL FAILURE:", err);
            // Display error clearly on the website
            document.getElementById('narrative-text').innerHTML = 
                `<div style="background: #330000; padding: 10px; border: 1px solid red; color: #ff9999;">
                    <strong>SYSTEM ERROR:</strong><br>
                    ${err.message}<br><br>
                    <em>Open your browser console (F12) for more details.</em>
                </div>`;
        });
});

function formatMoney(amount) {
    // FAIL-SAFE: Convert to float before formatting
    // If 'amount' is null/undefined, default to 0
    const num = parseFloat(amount) || 0;
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(num);
}

function renderDashboard(data) {
    // DIAGNOSTIC STEP 3: Safe access to nested objects
    const acc = data.account || {};
    const sum = data.summary || {};
    const fills = data.fills || [];
    const settlements = data.settlements || [];

    // 1. HEADER
    document.getElementById('last-updated').innerText = "Updated: " + (data.meta ? data.meta.updated_at : "Unknown");
    document.getElementById('hero-total-val').innerText = formatMoney(acc.total_account_value);
    
    // Profit Color Logic
    const profitVal = parseFloat(sum.net_profit) || 0;
    const profitElem = document.getElementById('hero-profit');
    profitElem.innerText = formatMoney(profitVal);
    profitElem.className = profitVal >= 0 ? "hero-value positive" : "hero-value negative";

    // 2. METRIC CARDS
    document.getElementById('val-deposits').innerText = formatMoney(sum.total_deposits);
    document.getElementById('val-cash').innerText = formatMoney(acc.cash_balance);
    document.getElementById('val-bets').innerText = formatMoney(acc.money_in_bets);
    
    const roiVal = parseFloat(sum.roi_percent) || 0;
    const roiElem = document.getElementById('val-roi');
    roiElem.innerText = roiVal.toFixed(1) + "%";
    roiElem.className = roiVal >= 0 ? "metric-value positive" : "metric-value negative";

    // 3. NARRATIVE
    const narrative = `
        You have put in <strong>${formatMoney(sum.total_deposits)}</strong>. 
        You have <strong>${formatMoney(acc.cash_balance)}</strong> in cash and 
        <strong>${formatMoney(acc.money_in_bets)}</strong> in bets.
    `;
    document.getElementById('narrative-text').innerHTML = narrative;

    // 4. TRADES TABLE
    const fillsTable = document.querySelector('#fills-table tbody');
    fillsTable.innerHTML = '';
    
    if (fills.length > 0) {
        fills.slice(0, 10).forEach(f => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${new Date(f.created_time).toLocaleDateString()}</td>
                <td>${f.ticker}</td>
                <td>${f.side}</td>
                <td>${f.count}</td>
                <td>${formatMoney(f.price_cents / 100)}</td>
            `;
            fillsTable.appendChild(row);
        });
    } else {
        fillsTable.innerHTML = '<tr><td colspan="5" style="text-align:center; opacity:0.6;">No recent trades found.</td></tr>';
    }

    // 5. SETTLEMENTS TABLE
    const setTable = document.querySelector('#settlements-table tbody');
    setTable.innerHTML = '';
    
    if (settlements.length > 0) {
        settlements.slice(0, 10).forEach(s => {
            const row = document.createElement('tr');
            const payout = (s.received_cents / 100);
            row.innerHTML = `
                <td>${new Date(s.settled_time).toLocaleDateString()}</td>
                <td>${s.ticker}</td>
                <td>${s.outcome}</td>
                <td>${formatMoney(payout)}</td>
            `;
            setTable.appendChild(row);
        });
    } else {
        setTable.innerHTML = '<tr><td colspan="4" style="text-align:center; opacity:0.6;">No settlements found.</td></tr>';
    }
}
