document.addEventListener("DOMContentLoaded", () => {
    // 1. CONFIGURATION
    // Looking for the 'data' folder next to index.html
    const DATA_FILE = 'data/kalshi_summary.json';
    
    console.log("Initializing Dashboard...");
    
    // 2. FETCH DATA
    // We append ?t=... to stop the browser from remembering old 0 values
    fetch(`${DATA_FILE}?t=${Date.now()}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status} - File not found at '${DATA_FILE}'`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Data loaded:", data);
            updateDashboard(data);
        })
        .catch(error => {
            showError(error);
        });
});

/**
 * Main function to map JSON data to HTML elements
 */
function updateDashboard(data) {
    const acc = data.account || {};
    const sum = data.summary || {};
    
    // Status Indicator
    document.getElementById('status-dot').className = "dot live";
    document.getElementById('last-updated').innerText = `Updated: ${data.meta.updated_at}`;

    // --- HERO SECTION ---
    document.getElementById('total-value').innerText = formatUSD(acc.total_account_value);
    
    const profit = parseFloat(sum.net_profit || 0);
    const profitEl = document.getElementById('total-profit');
    profitEl.innerText = formatUSD(profit);
    profitEl.className = profit >= 0 ? "value text-green" : "value text-red";

    // --- GRID SECTION ---
    document.getElementById('cash-balance').innerText = formatUSD(acc.cash_balance);
    document.getElementById('money-in-bets').innerText = formatUSD(acc.money_in_bets);
    document.getElementById('total-deposits').innerText = formatUSD(sum.total_deposits);
    
    const roi = parseFloat(sum.roi_percent || 0);
    const roiEl = document.getElementById('roi-percent');
    roiEl.innerText = roi.toFixed(1) + "%";
    roiEl.className = roi >= 0 ? "text-green" : "text-red";

    // --- TABLES ---
    renderFills(data.fills);
    renderSettlements(data.settlements);
}

/**
 * Render the Recent Trades table
 */
function renderFills(fills) {
    const tbody = document.querySelector("#fills-table tbody");
    tbody.innerHTML = ""; // Clear loading state

    if (!fills || fills.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No trades recorded</td></tr>`;
        return;
    }

    // Show last 10 trades
    fills.slice(0, 10).forEach(fill => {
        const row = document.createElement("tr");
        const dateStr = new Date(fill.created_time).toLocaleDateString();
        // Price is in cents in JSON, convert to dollars for display
        const price = (fill.price_cents / 100).toFixed(2);
        
        row.innerHTML = `
            <td>${dateStr}</td>
            <td>${fill.ticker}</td>
            <td style="font-weight:bold; color: ${fill.side === 'yes' ? '#4caf50' : '#ff5252'}">${fill.side.toUpperCase()}</td>
            <td>${fill.count}</td>
            <td>$${price}</td>
        `;
        tbody.appendChild(row);
    });
}

/**
 * Render the Settlements table
 */
function renderSettlements(settlements) {
    const tbody = document.querySelector("#settlements-table tbody");
    tbody.innerHTML = "";

    if (!settlements || settlements.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No settlements yet</td></tr>`;
        return;
    }

    settlements.slice(0, 10).forEach(settlement => {
        const row = document.createElement("tr");
        const dateStr = new Date(settlement.settled_time).toLocaleDateString();
        const payout = (settlement.received_cents / 100).toFixed(2);
        
        row.innerHTML = `
            <td>${dateStr}</td>
            <td>${settlement.ticker}</td>
            <td>${settlement.outcome}</td>
            <td class="text-green">+$${payout}</td>
        `;
        tbody.appendChild(row);
    });
}

/**
 * Helper: Format Number as USD Currency
 */
function formatUSD(amount) {
    const num = parseFloat(amount) || 0;
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(num);
}

/**
 * Helper: Show Error Box
 */
function showError(error) {
    console.error(error);
    document.getElementById('status-dot').className = "dot error";
    document.getElementById('last-updated').innerText = "Connection Failed";
    
    const errorBox = document.getElementById('error-box');
    const errorMsg = document.getElementById('error-message');
    
    errorBox.classList.remove('hidden');
    errorMsg.innerText = error.message;
}
