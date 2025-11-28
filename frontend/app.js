// JavaScript for the Kalshi Analytics Dashboard

const JSON_URL = "../data/kalshi_summary.json";
const REFRESH_MS = 60_000;

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

    const fills = Array.isArray(data.fills_last_n_days)
      ? data.fills_last_n_days
      : [];
    const settlements = Array.isArray(data.settlements_last_n_days)
      ? data.settlements_last_n_days
      : [];

    const account = data.account || {};
    const summaryRaw = data.summary || {};

    // Account numbers from get_balance (matches Kalshi app)
    const accountStats = {
      cash: Number(account.cash || 0),
      positions: Number(account.positions_value || 0),
      portfolioTotal: Number(account.portfolio_total || 0),
    };

    // Investment stats from fills/settlements
    const summaryStats = {
      totalInvested: Number(summaryRaw.total_invested || 0),
      reinvested: Number(summaryRaw.reinvested || 0),
      cashInvested: Number(summaryRaw.cash_invested || 0),
      realizedPnL: Number(summaryRaw.realized_pnl || 0),
      portfolioValue: Number(summaryRaw.portfolio_value || 0),
      returnRate: Number(summaryRaw.return_rate || 0),
      cumulativeSeries: Array.isArray(summaryRaw.cumulative_series)
        ? summaryRaw.cumulative_series
        : [],
    };

    // ---------- NAV METRICS (matches Kalshi) ----------
    updateText(
      "nav-portfolio-value",
      formatCurrency(accountStats.portfolioTotal)
    );
    updateText("nav-total-invested", formatCurrency(summaryStats.totalInvested));
    updateText(
      "nav-realized-pnl",
      formatCurrency(summaryStats.realizedPnL, true)
    );

    // ---------- SUMMARY CARDS ----------
    // Portfolio value here = positions + cash (same as Kalshi Portfolio screen)
    updateText(
      "portfolio-value",
      formatCurrency(accountStats.portfolioTotal)
    );
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

    // ---------- CHARTS ----------
    renderInvestmentChart(
      summaryStats.cashInvested,
      summaryStats.reinvested
    );
    renderPerformanceChart(summaryStats.cumulativeSeries);

    // ---------- TABLES ----------
    renderFillsTable(fills);
    renderSettlementsTable(settlements);

    const refreshIntervalLabel = document.getElementById(
      "refresh-interval-label"
    );
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
// Helpers for stats / formatting
// -------------------------

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

function formatCurrency(value, withSign = false) {
  if (typeof value !== "number" || isNaN(value)) return "$0.00";
  const sign = value < 0 ? "-" : withSign ? "+" : "";
  const abs = Math.abs(value);
  return `${sign}$${abs.toFixed(2)}`;
}

function updateText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// -------------------------
// Human-readable ticker formatter
// -------------------------

function formatTickerReadable(ticker, side = null) {
  if (!ticker || typeof ticker !== "string") return "";

  // NFL game pattern: KXNFLGAME-25NOV27CINBAL-CIN
  if (ticker.startsWith("KXNFLGAME-")) {
    const parts = ticker.split("-");
    if (parts.length >= 3) {
      const event = parts[1]; // 25NOV27CINBAL
      const contract = parts[2]; // CIN

      if (event.length >= 13) {
        const yy = event.slice(0, 2);
        const mon = event.slice(2, 5).toUpperCase();
        const dd = event.slice(5, 7);
        const team1 = event.slice(7, 10).toUpperCase();
        const team2 = event.slice(10, 13).toUpperCase();

        const monthNames = {
          JAN: "Jan",
          FEB: "Feb",
          MAR: "Mar",
          APR: "Apr",
          MAY: "May",
          JUN: "Jun",
          JUL: "Jul",
          AUG: "Aug",
          SEP: "Sep",
          OCT: "Oct",
          NOV: "Nov",
          DEC: "Dec",
        };

        const monthLabel = monthNames[mon] || mon;
        const dateLabel = `${monthLabel} ${dd}, 20${yy}`;

        const matchup = `${team1} @ ${team2}`;
        const sideLabel = side ? side.toUpperCase() : "";
        const teamContract = contract.toUpperCase();

        // Example: CIN @ BAL – YES (CIN) – Nov 27, 2025
        return `${matchup} \u2013 ${sideLabel} (${teamContract}) \u2013 ${dateLabel}`;
      }
    }
  }

  // Fallback: just return the ticker as-is
  return ticker;
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
    new Date(item.ts).toLocaleString([], {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
  );
  const dataVals = sorted.map((item) => item.cumulative);

  const data = {
    labels,
    datasets: [
      {
        label: "Cumulative Realized P&L",
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
    td.textContent = "No fills in the selected window";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const f of fills) {
    const tr = document.createElement("tr");
    const ts = getSafeTimestamp(f);
    const timeStr = ts ? new Date(ts).toLocaleString() : "-";

    const size =
      f.count ??
      f.size ??
      f.quantity ??
      f.contracts ??
      f.contracts_count ??
      0;
    const price = Number(f.price ?? 0);
    const cost = size * price;

    const rawTicker = f.ticker ?? f.market ?? "";
    const prettyTicker = formatTickerReadable(rawTicker, f.side);

    tr.innerHTML = `
      <td>${timeStr}</td>
      <td>${prettyTicker}</td>
      <td>${(f.action ?? "").toUpperCase()}</td>
      <td>${size}</td>
      <td>${price.toFixed(2)}</td>
      <td>${cost.toFixed(2)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function extractCashChange(settlement) {
  const raw = settlement.cash_change ?? settlement.cashChange;
  if (raw === null || raw === undefined) return null;
  return Number(raw);
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
    td.textContent = "No settlements in the selected window";
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
    const timeStr = ts ? new Date(ts).toLocaleString() : "-";

    const rawTicker = s.ticker ?? s.market ?? "";
    const prettyTicker = formatTickerReadable(rawTicker);

    const outcome =
      s.outcome ??
      s.final_position ??
      s.finalPosition ??
      "";
    const cashChange = extractCashChange(s);
    const cashDisplay =
      cashChange !== null ? formatCurrency(cashChange, true) : "-";

    tr.innerHTML = `
      <td>${timeStr}</td>
      <td>${prettyTicker}</td>
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