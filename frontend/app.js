// JavaScript for the redesigned Kalshi Analytics Dashboard.

// Path to the summary JSON relative to this HTML file. The default
// location is within the redesign/data folder. Adjust as needed if
// hosting elsewhere.
const JSON_URL = './data/kalshi_summary.json';
const REFRESH_MS = 60_000; // refresh every 60 seconds by default

// Chart instances
let investmentChart = null;
let performanceChart = null;

// Fetch and render the dashboard
async function fetchAndRender() {
    try {
        const cacheBuster = `t=${Date.now()}`;
        const url = JSON_URL.includes('?') ? `${JSON_URL}&${cacheBuster}` : `${JSON_URL}?${cacheBuster}`;
        const res = await fetch(url, { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        renderDashboard(data);
    } catch (err) {
        console.error('Error loading summary:', err);
    }
}

function renderDashboard(data) {
    const fills = Array.isArray(data.fills_last_1_day) ? data.fills_last_1_day : [];
    const settlements = Array.isArray(data.settlements_last_1_day) ? data.settlements_last_1_day : [];

    // Compute various stats
    const settlementStats = computeSettlementStats(settlements);
    const activityStats = computeActivityStats(fills);
    const summaryStats = computeSummaryStats(fills, settlements, settlementStats);

    // Update nav metrics
    updateText('nav-portfolio-value', formatCurrency(summaryStats.portfolioValue));
    updateText('nav-total-invested', formatCurrency(summaryStats.totalInvested));
    updateText('nav-realized-pnl', formatCurrency(summaryStats.realizedPnL, true));

    // Update summary metric cards
    updateText('portfolio-value', formatCurrency(summaryStats.portfolioValue));
    updateText('total-invested', formatCurrency(summaryStats.totalInvested));
    updateText('cash-invested', formatCurrency(summaryStats.cashInvested));
    updateText('reinvested', formatCurrency(summaryStats.reinvested));
    updateText('realized-pnl', formatCurrency(summaryStats.realizedPnL, true));
    updateText('return-rate', `${(summaryStats.returnRate * 100).toFixed(2)}%`);

    // Render charts
    renderInvestmentChart(summaryStats.cashInvested, summaryStats.reinvested);
    renderPerformanceChart(summaryStats.cumulativeSeries);

    // Render tables
    renderFillsTable(fills);
    renderSettlementsTable(settlements);

    // Update refresh interval label
    const refreshIntervalLabel = document.getElementById('refresh-interval-label');
    if (refreshIntervalLabel) {
        refreshIntervalLabel.textContent = Math.round(REFRESH_MS / 1000).toString();
    }
}

// Compute summary stats from fills and settlements
function computeSummaryStats(fills, settlements, settlementStats) {
    let totalInvested = 0;
    let totalCashGenerated = 0;
    for (const f of fills) {
        const size = f.size ?? f.quantity ?? f.contracts ?? f.contracts_count ?? 0;
        const price = Number(f.price ?? 0);
        const cost = size * price;
        if ((f.action ?? '').toLowerCase() === 'buy') {
            totalInvested += cost;
        } else if ((f.action ?? '').toLowerCase() === 'sell') {
            totalCashGenerated += cost;
        }
    }
    // Approximate reinvestment as portion of buys funded by sells
    const reinvested = Math.min(totalInvested, totalCashGenerated);
    const cashInvested = totalInvested - reinvested;
    // Realized PnL from settlements (from settlementStats)
    const realizedPnL = settlementStats.realizedPnL;
    // Approximate portfolio value: cost of current positions (net buys) + realized PnL
    const portfolioValue = cashInvested + reinvested + realizedPnL;
    const returnRate = totalInvested > 0 ? (realizedPnL / totalInvested) : 0;
    return {
        totalInvested,
        reinvested,
        cashInvested,
        realizedPnL,
        portfolioValue,
        returnRate,
        cumulativeSeries: settlementStats.cumulativeSeries
    };
}

// Compute stats from settlements (realized PnL, cash in/out, cumulative series)
function computeSettlementStats(settlements) {
    let realizedPnL = 0;
    let cashIn = 0;
    let cashOut = 0;
    let cumulativeSeries = [];
    // sort by timestamp ascending
    const sorted = [...settlements].sort((a, b) => {
        const ta = getSafeTimestamp(a);
        const tb = getSafeTimestamp(b);
        return ta - tb;
    });
    let running = 0;
    for (const s of sorted) {
        const cashChange = extractCashChange(s);
        if (cashChange === null) continue;
        realizedPnL += cashChange;
        if (cashChange > 0) {
            cashIn += cashChange;
        } else if (cashChange < 0) {
            cashOut += -cashChange;
        }
        const ts = getSafeTimestamp(s);
        if (ts) {
            running += cashChange;
            cumulativeSeries.push({ t: ts, cumulative: running });
        }
    }
    return { realizedPnL, cashIn, cashOut, cumulativeSeries };
}

// Compute stats from fills (activity metrics)
function computeActivityStats(fills) {
    let trades = fills.length;
    const markets = new Set();
    let totalContracts = 0;
    let grossVolume = 0;
    for (const f of fills) {
        const m = f.ticker ?? f.market ?? f.ticker_label ?? '';
        markets.add(m);
        const size = f.size ?? f.quantity ?? f.contracts ?? f.contracts_count ?? 0;
        const price = Number(f.price ?? 0);
        totalContracts += size;
        grossVolume += size * price;
    }
    return { tradesCount: trades, marketsCount: markets.size, totalContracts, grossVolume };
}

// Helpers
function extractCashChange(settlement) {
    // Kalshi SDK uses `cash_change` or `cashChange` depending on object shape
    const raw = settlement.cash_change ?? settlement.cashChange;
    if (raw === null || raw === undefined) return null;
    // Convert to number; could be string or float
    return Number(raw);
}

function getSafeTimestamp(obj) {
    // Kalshi SDK uses ts or timestamp or created_time; try them in order
    const tsVal = obj.ts ?? obj.timestamp ?? obj.created_time ?? obj.createdTime ?? null;
    if (!tsVal) return null;
    // if value is ISO string, convert to Date
    let ms;
    if (typeof tsVal === 'string') {
        const d = new Date(tsVal);
        if (!isNaN(d.getTime())) {
            ms = d.getTime();
        } else {
            // maybe it's seconds or ms string
            const num = Number(tsVal);
            if (!isNaN(num)) {
                ms = num > 1e12 ? num : num * 1000;
            }
        }
    } else if (typeof tsVal === 'number') {
        ms = tsVal > 1e12 ? tsVal : tsVal * 1000;
    } else {
        ms = null;
    }
    return ms;
}

function updateText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function formatCurrency(value, withSign = false) {
    if (typeof value !== 'number' || isNaN(value)) return '$0.00';
    const sign = value < 0 ? '-' : (withSign ? '+' : '');
    const abs = Math.abs(value);
    return `${sign}$${abs.toFixed(2)}`;
}

function renderInvestmentChart(cashInvested, reinvested) {
    const ctx = document.getElementById('investment-breakdown-chart').getContext('2d');
    const data = {
        labels: ['Cash Invested', 'Reinvested'],
        datasets: [
            {
                data: [cashInvested, reinvested],
                backgroundColor: [
                    'rgba(46, 204, 113, 0.7)', // accent
                    'rgba(52, 152, 219, 0.7)'  // secondary accent
                ],
                borderColor: [
                    'rgba(46, 204, 113, 1)',
                    'rgba(52, 152, 219, 1)'
                ],
                borderWidth: 1
            }
        ]
    };
    const options = {
        plugins: {
            legend: {
                position: 'bottom',
                labels: { color: '#e6eaf1' }
            }
        }
    };
    if (investmentChart) investmentChart.destroy();
    investmentChart = new Chart(ctx, {
        type: 'doughnut',
        data,
        options
    });
}

function renderPerformanceChart(cumulativeSeries) {
    const ctx = document.getElementById('performance-chart').getContext('2d');
    // Sort by time to ensure proper order
    const sorted = [...cumulativeSeries].sort((a, b) => a.t - b.t);
    const labels = sorted.map(item => new Date(item.t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    const dataVals = sorted.map(item => item.cumulative);
    const data = {
        labels,
        datasets: [
            {
                label: 'Cumulative P&L',
                data: dataVals,
                fill: false,
                tension: 0.2,
                borderWidth: 2,
                // Colours will respect default Chart.js dark theme variables unless overridden
            }
        ]
    };
    const options = {
        scales: {
            x: {
                ticks: { color: '#e6eaf1' },
                grid: { color: '#2f415c' }
            },
            y: {
                ticks: { color: '#e6eaf1' },
                grid: { color: '#2f415c' }
            }
        },
        plugins: {
            legend: {
                display: false
            }
        }
    };
    if (performanceChart) performanceChart.destroy();
    performanceChart = new Chart(ctx, {
        type: 'line',
        data,
        options
    });
}

function renderFillsTable(fills) {
    const tbody = document.getElementById('fills-table-body');
    tbody.innerHTML = '';
    if (!fills.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 6;
        td.className = 'placeholder';
        td.textContent = 'No fills in the last 24h';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }
    for (const f of fills) {
        const tr = document.createElement('tr');
        const ts = getSafeTimestamp(f);
        const timeStr = ts ? new Date(ts).toLocaleString() : '-';
        const size = f.size ?? f.quantity ?? f.contracts ?? f.contracts_count ?? 0;
        const price = Number(f.price ?? 0);
        const cost = size * price;
        tr.innerHTML = `
            <td>${timeStr}</td>
            <td>${f.ticker ?? f.market ?? ''}</td>
            <td>${(f.action ?? '').toUpperCase()}</td>
            <td>${size}</td>
            <td>${price.toFixed(2)}</td>
            <td>${cost.toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
    }
}

function renderSettlementsTable(settlements) {
    const tbody = document.getElementById('settlements-table-body');
    tbody.innerHTML = '';
    if (!settlements.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 4;
        td.className = 'placeholder';
        td.textContent = 'No settlements in the last 24h';
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }
    // Sort by time descending for table
    const sorted = [...settlements].sort((a, b) => getSafeTimestamp(b) - getSafeTimestamp(a));
    for (const s of sorted) {
        const tr = document.createElement('tr');
        const ts = getSafeTimestamp(s);
        const timeStr = ts ? new Date(ts).toLocaleString() : '-';
        const ticker = s.ticker ?? s.market ?? '';
        const outcome = s.outcome ?? s.final_position ?? s.finalPosition ?? '';
        const cashChange = extractCashChange(s);
        const cashDisplay = cashChange !== null ? formatCurrency(cashChange, true) : '-';
        tr.innerHTML = `
            <td>${timeStr}</td>
            <td>${ticker}</td>
            <td>${outcome}</td>
            <td>${cashDisplay}</td>
        `;
        tbody.appendChild(tr);
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Initial fetch and render
    fetchAndRender();
    // Auto-refresh interval
    setInterval(fetchAndRender, REFRESH_MS);
    // Manual refresh button
    const refreshButton = document.getElementById('refresh-button');
    if (refreshButton) {
        refreshButton.addEventListener('click', () => {
            fetchAndRender();
        });
    }
});
