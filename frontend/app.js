// JavaScript for the redesigned Kalshi Analytics Dashboard.

// Path to the summary JSON relative to this HTML file.
// For your repo structure this is usually "../data/kalshi_summary.json".
const JSON_URL = "../data/kalshi_summary.json";
const REFRESH_MS = 60_000; // refresh every 60 seconds by default

// Chart instances
let investmentChart = null;
let performanceChart = null;

// -------------------------
// Main fetch + render
// -------------------------
async function fetchAndRender() {
    try {
        const cacheBuster = `t=${Date.now()}`;
        const url = JSON_URL.includes("?")
            ? `${JSON_URL}&${cacheBuster}`
            : `${JSON_URL}?${cacheBuster}`;

        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();

        const fills = Array.isArray(data.fills_last_1_day)
            ? data.fills_last_1_day
            : [];
        const settlements = Array.isArray(data.settlements_last_1_day)
            ? data.settlements_last_1_day
            : [];

        // Prefer Python-computed summary if present
        let summaryStats;
        if (data.summary && typeof data.summary.total_invested === "number") {
            const s = data.summary;
            summaryStats = {
                totalInvested: s.total_invested || 0,
                reinvested: s.reinvested || 0,
                cashInvested: s.cash_invested || 0,
                realizedPnL: s.realized_pnl || 0,
                portfolioValue: s.portfolio_value || 0,
                returnRate: s.return_rate || 0,
                cumulativeSeries: Array.isArray(s.cumulative_series)
                    ? s.cumulative_series
                    : [],
            };
        } else {
            // Fallback: compute in JS
            const settlementStats = computeSettlementStats(settlements);
            summaryStats = computeSummaryStats(fills, settlements, settlementStats);
        }

        // Activity stats (not currently displayed, but ready if you want cards)
        // const activityStats = computeActivityStats(fills);

        // -------- Update UI --------

        // Nav metrics
        updateText(
            "nav-portfolio-value",
            formatCurrency(summaryStats.portfolioValue)
        );
        updateText(
            "nav-total-invested",
            formatCurrency(summaryStats.totalInvested)
        );
        updateText(
            "nav-realized-pnl",
            formatCurrency(summaryStats.realizedPnL, true)
        );

        // Summary cards
        updateText("portfolio-value", formatCurrency(summaryStats.portfolioValue));
        updateText("total-invested", formatCurrency(summaryStats.totalInvested));
        updateText("cash-invested", formatCurrency(summaryStats.cashInvested));
        updateText("reinvested", formatCurrency(summaryStats.reinvested));
        updateText(
            "realized-pnl",
            formatCurrency(summaryStats.realizedPnL, true)
        );
        updateText(
            "return-rate",
            `${(summaryStats.returnRate * 100).toFixed(2)}%`
        );

        // Charts
        renderInvestmentChart(
            summaryStats.cashInvested,
            summaryStats.reinvested
        );
        renderPerformanceChart(summaryStats.cumulativeSeries);

        // Tables
        renderFillsTable(fills);
        renderSettlementsTable(settlements);

        // Refresh label
        const refreshIntervalLabel =
            document.getElementById("refresh-interval-label");
        if (refreshIntervalLabel) {
            refreshIntervalLabel.textContent = String(
                Math.round(REFRESH_MS / 1000)
            );
        }
    } catch (err) {
        console.error("Error loading summary:", err);
    }
}

// -------------------------
// Summary / stats helpers
// -------------------------

// Only used if Python summary is missing. Left here as a fallback.
function computeSummaryStats(fills, settlements, settlementStats) {
    let totalInvested = 0;
    let totalCashGenerated = 0;

    for (const f of fills) {
        const size =
            f.count ??
            f.size ??
            f.quantity ??
            f.contracts ??
            f.contracts_count ??
            0;
        const price = Number(f.price ?? 0);
        const cost = size * price;
        const action = (f.action ?? "").toLowerCase();

        if (action === "buy") {
            totalInvested += cost;
        } else if (action === "sell") {
            totalCashGenerated += cost;
        }
    }

    const reinvested = Math.min(totalInvested, totalCashGenerated);
    const cashInvested = totalInvested - reinvested;

    const realizedPnL = settlementStats.realizedPnL;
    const portfolioValue = cashInvested + reinvested + realizedPnL;
    const returnRate =
        totalInvested > 0 ? realizedPnL / totalInvested : 0;

    return {
        totalInvested,
        reinvested,
        cashInvested,
        realizedPnL,
        portfolioValue,
        returnRate,
        cumulativeSeries: settlementStats.cumulativeSeries,
    };
}

function computeSettlementStats(settlements) {
    let realizedPnL = 0;
    let cashIn = 0;
    let cashOut = 0;
    const cumulativeSeries = [];

    const sorted = [...settlements].sort(
        (a, b) => getSafeTimestamp(a) - getSafeTimestamp(b)
    );
    let running = 0;

    for (const s of sorted) {
        const cashChange = extractCashChange(s);
        if (cashChange === null) continue;

        realizedPnL += cashChange;
        if (cashChange > 0) cashIn += cashChange;
        else if (cashChange < 0) cashOut += -cashChange;

        const ts = getSafeTimestamp(s);
        if (!ts) continue;
        running += cashChange;
        cumulativeSeries.push({ ts, cumulative: running });
    }

    return { realizedPnL, cashIn, cashOut, cumulativeSeries };
}

// Still useful if you want activity cards later
function computeActivityStats(fills) {
    let tradesCount = fills.length;
    const markets = new Set();
    let totalContracts = 0;
    let grossVolume = 0;

    for (const f of fills) {
        const m = f.ticker ?? f.market ?? "";
        markets.add(m);
        const size =
            f.count ??
            f.size ??
            f.quantity ??
            f.contracts ??
            f.contracts_count ??
            0;
        const price = Number(f.price ?? 0);
        totalContracts += size;
        grossVolume += size * price;
    }

    return { tradesCount, marketsCount: markets.size, totalContracts, grossVolume };
}

// -------------------------
// Low-level helpers
// -------------------------

function extractCashChange(settlement) {
    const raw = settlement.cash_change ?? settlement.cashChange;
    if (raw === null || raw === undefined) return null;
    return Number(raw);
}

function getSafeTimestamp(obj) {
    const tsVal =
        obj.ts ??
        obj.timestamp ??
        obj.created_time ??
        obj.createdTime ??
        null;
    if (!tsVal) return null;

    let ms;
    if (typeof tsVal === "string") {
        const d = new Date(tsVal);
        if (!isNaN(d.getTime())) {
            ms = d.getTime();
        } else {
            const num = Number(tsVal);
            if (!isNaN(num)) {
                ms = num > 1e12 ? num : num * 1000;
            }
        }
    } else if (typeof tsVal === "number") {
        ms = tsVal > 1e12 ? tsVal : tsVal * 1000;
    }
    return ms ?? null;
}

function updateText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function formatCurrency(value, withSign = false) {
    if (typeof value !== "number" || isNaN(value)) return "$0.00";
    const sign = value < 0 ? "-" : withSign ? "+" : "";
    const abs = Math.abs(value);
    return `${sign}$${abs.toFixed(2)}`;
}

// -------------------------
// Charts
// -------------------------

function renderInvestmentChart(cashInvested, reinvested) {
    const canvas = document.getElementById("investment-breakdown-chart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const data = {
        labels: ["Cash Invested", "Reinvested"],
        datasets: [
            {
                data: [cashInvested, reinvested],
                backgroundColor: [
                    "rgba(46, 204, 113, 0.7)",
                    "rgba(52, 152, 219, 0.7)",
                ],
                borderColor: [
                    "rgba(46, 204, 113, 1)",
                    "rgba(52, 152, 219, 1)",
                ],
                borderWidth: 1,
            },
        ],
    };

    const options = {
        plugins: {
            legend: {
                position: "bottom",
                labels: { color: "#e6eaf1" },
            },
        },
    };

    if (investmentChart) investmentChart.destroy();
    investmentChart = new Chart(ctx, {
        type: "doughnut",
        data,
        options,
    });
}

function renderPerformanceChart(cumulativeSeries) {
    const canvas = document.getElementById("performance-chart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const sorted = [...cumulativeSeries].sort((a, b) => a.ts - b.ts);
    const labels = sorted.map((item) =>
        new Date(item.ts).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
        })
    );
    const dataVals = sorted.map((item) => item.cumulative);

    const data = {
        labels,
        datasets: [
            {
                label: "Cumulative P&L",
                data: dataVals,
                fill: false,
                tension: 0.2,
                borderWidth: 2,
            },
        ],
    };

    const options = {
        scales: {
            x: {
                ticks: { color: "#e6eaf1" },
                grid: { color: "#2f415c" },
            },
            y: {
                ticks: { color: "#e6eaf1" },
                grid: { color: "#2f415c" },
            },
        },
        plugins: {
            legend: { display: false },
        },
    };

    if (performanceChart) performanceChart.destroy();
    performanceChart = new Chart(ctx, {
        type: "line",
        data,
        options,
    });
}

// -------------------------
// Tables
// -------------------------

function renderFillsTable(fills) {
    const tbody = document.getElementById("fills-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!fills.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 6;
        td.className = "placeholder";
        td.textContent = "No fills in the last 24h";
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    for (const f of fills) {
        const tr = document.createElement("tr");
        const ts = getSafeTimestamp(f);
        const timeStr = ts
            ? new Date(ts).toLocaleString()
            : "-";
        const size =
            f.count ??
            f.size ??
            f.quantity ??
            f.contracts ??
            f.contracts_count ??
            0;
        const price = Number(f.price ?? 0);
        const cost = size * price;

        tr.innerHTML = `
            <td>${timeStr}</td>
            <td>${f.ticker ?? f.market ?? ""}</td>
            <td>${(f.action ?? "").toUpperCase()}</td>
            <td>${size}</td>
            <td>${price.toFixed(2)}</td>
            <td>${cost.toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
    }
}

function renderSettlementsTable(settlements) {
    const tbody = document.getElementById("settlements-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!settlements.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 4;
        td.className = "placeholder";
        td.textContent = "No settlements in the last 24h";
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    const sorted = [...settlements].sort(
        (a, b) => getSafeTimestamp(b) - getSafeTimestamp(a)
    );

    for (const s of sorted) {
        const tr = document.createElement("tr");
        const ts = getSafeTimestamp(s);
        const timeStr = ts
            ? new Date(ts).toLocaleString()
            : "-";
        const ticker = s.ticker ?? s.market ?? "";
        const outcome =
            s.outcome ??
            s.final_position ??
            s.finalPosition ??
            "";
        const cashChange = extractCashChange(s);
        const cashDisplay =
            cashChange !== null
                ? formatCurrency(cashChange, true)
                : "-";

        tr.innerHTML = `
            <td>${timeStr}</td>
            <td>${ticker}</td>
            <td>${outcome}</td>
            <td>${cashDisplay}</td>
        `;
        tbody.appendChild(tr);
    }
}

// -------------------------
// Boot
// -------------------------
document.addEventListener("DOMContentLoaded", () => {
    fetchAndRender();
    setInterval(fetchAndRender, REFRESH_MS);

    const refreshButton = document.getElementById("refresh-button");
    if (refreshButton) {
        refreshButton.addEventListener("click", () => {
            fetchAndRender();
        });
    }
});