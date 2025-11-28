const JSON_URL = "../data/kalshi_summary.json";
const REFRESH_MS = 60_000; // 60 seconds

const statusPill = document.getElementById("status-pill");
const statusText = document.getElementById("status-text");

const lastUpdatedEl = document.getElementById("last-updated");
const fillsCountEl = document.getElementById("fills-count");
const settlementsCountEl = document.getElementById("settlements-count");

const realizedPnlEl = document.getElementById("realized-pnl");
const cashInEl = document.getElementById("cash-in");
const cashOutEl = document.getElementById("cash-out");
const winRateEl = document.getElementById("win-rate");

const fillsPill = document.getElementById("fills-pill");
const settlementsPill = document.getElementById("settlements-pill");

const fillsTableBody = document.getElementById("fills-table-body");
const settlementsTableBody = document.getElementById("settlements-table-body");

const refreshButton = document.getElementById("refresh-button");
const refreshIntervalLabel = document.getElementById("refresh-interval-label");

refreshIntervalLabel.textContent = Math.round(REFRESH_MS / 1000).toString();

// Chart instances
let pnlByMarketChart = null;
let pnlOverTimeChart = null;

async function fetchSummary() {
  try {
    setStatus("Loading…", false);

    const cacheBuster = `t=${Date.now()}`;
    const url = JSON_URL.includes("?")
      ? `${JSON_URL}&${cacheBuster}`
      : `${JSON_URL}?${cacheBuster}`;

    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    renderDashboard(data);
    setStatus("Live · data loaded", false);
  } catch (err) {
    console.error("Error fetching summary:", err);
    setStatus("Error loading data", true);
  }
}

function setStatus(text, isError) {
  statusText.textContent = text;
  if (isError) {
    statusPill.classList.add("error");
  } else {
    statusPill.classList.remove("error");
  }
}

function renderDashboard(data) {
  const generatedAt = data.generated_at || null;
  if (generatedAt) {
    const dt = new Date(generatedAt);
    lastUpdatedEl.textContent =
      isNaN(dt.getTime()) ? generatedAt : dt.toLocaleString();
  } else {
    lastUpdatedEl.textContent = "—";
  }

  const fills = Array.isArray(data.fills_last_1_day)
    ? data.fills_last_1_day
    : [];
  const settlements = Array.isArray(data.settlements_last_1_day)
    ? data.settlements_last_1_day
    : [];

  fillsCountEl.textContent = fills.length.toString();
  settlementsCountEl.textContent = settlements.length.toString();

  fillsPill.textContent =
    fills.length === 0 ? "No fills in last 24h" : `${fills.length} fill(s)`;
  settlementsPill.textContent =
    settlements.length === 0
      ? "No settlements in last 24h"
      : `${settlements.length} settlement(s)`;

  // Money analytics from settlements
  const analytics = computeAnalytics(settlements);
  realizedPnlEl.textContent = formatDollars(analytics.realizedPnl);
  realizedPnlEl.classList.remove("positive", "negative");
  if (analytics.realizedPnl > 0) realizedPnlEl.classList.add("positive");
  if (analytics.realizedPnl < 0) realizedPnlEl.classList.add("negative");

  cashInEl.textContent = formatDollars(analytics.cashIn);
  cashOutEl.textContent = formatDollars(-analytics.cashOut); // show as negative dollars
  cashOutEl.classList.add("negative");

  winRateEl.textContent =
    analytics.totalSettlements > 0
      ? `${analytics.winRate.toFixed(1)}%`
      : "—";

  renderFillsTable(fills);
  renderSettlementsTable(settlements);

  renderPnlByMarketChart(analytics.pnlByMarket);
  renderPnlOverTimeChart(analytics.cumulativeSeries);
}

/* ---------- ANALYTICS ---------- */

function computeAnalytics(settlements) {
  let realizedPnl = 0;
  let cashIn = 0;
  let cashOut = 0;
  let winCount = 0;
  let lossCount = 0;

  const pnlByMarket = {};
  const series = [];

  const sorted = [...settlements].sort((a, b) => {
    const ta = getSafeTimestamp(a);
    const tb = getSafeTimestamp(b);
    return ta - tb;
  });

  let running = 0;

  for (const s of sorted) {
    const cashChange = extractCashChange(s);
    if (cashChange === null) continue;

    realizedPnl += cashChange;

    if (cashChange > 0) {
      cashIn += cashChange;
      winCount++;
    } else if (cashChange < 0) {
      cashOut += -cashChange;
      lossCount++;
    }

    const marketLabel = getMarketLabel(s);
    pnlByMarket[marketLabel] = (pnlByMarket[marketLabel] || 0) + cashChange;

    const ts = getSafeTimestamp(s);
    if (ts) {
      running += cashChange;
      series.push({
        ts,
        cumulative: running,
      });
    }
  }

  const totalSettlements = winCount + lossCount;
  const winRate = totalSettlements > 0 ? (winCount / totalSettlements) * 100 : 0;

  return {
    realizedPnl,
    cashIn,
    cashOut,
    winRate,
    totalSettlements,
    pnlByMarket,
    cumulativeSeries: series,
  };
}

/* ---------- TABLE RENDERING ---------- */

function renderFillsTable(fills) {
  fillsTableBody.innerHTML = "";

  if (fills.length === 0) {
    fillsTableBody.innerHTML =
      '<tr><td colspan="5" class="placeholder">No fills in the last 24 hours.</td></tr>';
    return;
  }

  const sorted = [...fills].sort((a, b) => {
    const ta = getSafeTimestamp(a);
    const tb = getSafeTimestamp(b);
    return tb - ta;
  });

  sorted.slice(0, 40).forEach((fill) => {
    const tr = document.createElement("tr");

    const timeCell = document.createElement("td");
    timeCell.textContent = formatTimeCell(fill);

    const marketCell = document.createElement("td");
    marketCell.textContent = getMarketLabel(fill);

    const sideCell = document.createElement("td");
    sideCell.textContent = fill.side || fill.direction || "—";

    const sizeCell = document.createElement("td");
    const size =
      fill.size ??
      fill.quantity ??
      fill.contracts ??
      fill.contracts_count ??
      null;
    sizeCell.textContent = size == null ? "—" : size;

    const priceCell = document.createElement("td");
    priceCell.textContent = formatPrice(fill.price);

    tr.appendChild(timeCell);
    tr.appendChild(marketCell);
    tr.appendChild(sideCell);
    tr.appendChild(sizeCell);
    tr.appendChild(priceCell);

    fillsTableBody.appendChild(tr);
  });
}

function renderSettlementsTable(settlements) {
  settlementsTableBody.innerHTML = "";

  if (settlements.length === 0) {
    settlementsTableBody.innerHTML =
      '<tr><td colspan="4" class="placeholder">No settlements in the last 24 hours.</td></tr>';
    return;
  }

  const sorted = [...settlements].sort((a, b) => {
    const ta = getSafeTimestamp(a);
    const tb = getSafeTimestamp(b);
    return tb - ta;
  });

  sorted.slice(0, 40).forEach((s) => {
    const tr = document.createElement("tr");

    const timeCell = document.createElement("td");
    timeCell.textContent = formatTimeCell(s);

    const marketCell = document.createElement("td");
    marketCell.textContent = getMarketLabel(s);

    const outcomeCell = document.createElement("td");
    outcomeCell.textContent =
      s.outcome || s.result || s.position || s.status || "—";

    const cashCell = document.createElement("td");
    const change = extractCashChange(s);
    cashCell.textContent =
      change === null ? "—" : formatDollars(change, { showPlus: true });

    tr.appendChild(timeCell);
    tr.appendChild(marketCell);
    tr.appendChild(outcomeCell);
    tr.appendChild(cashCell);

    settlementsTableBody.appendChild(tr);
  });
}

/* ---------- CHARTS ---------- */

function renderPnlByMarketChart(pnlByMarket) {
  const ctx = document.getElementById("pnl-by-market-chart");
  if (!ctx) return;

  const labels = Object.keys(pnlByMarket);
  const values = labels.map((k) => pnlByMarket[k]);

  if (pnlByMarketChart) {
    pnlByMarketChart.destroy();
  }

  if (labels.length === 0) {
    // nothing to chart
    pnlByMarketChart = null;
    return;
  }

  pnlByMarketChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "P&L ($)",
          data: values,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: {
          ticks: {
            maxRotation: 45,
            minRotation: 0,
          },
        },
        y: {
          title: {
            display: true,
            text: "Dollars",
          },
        },
      },
    },
  });
}

function renderPnlOverTimeChart(series) {
  const ctx = document.getElementById("pnl-over-time-chart");
  if (!ctx) return;

  if (pnlOverTimeChart) {
    pnlOverTimeChart.destroy();
  }

  if (!series || series.length === 0) {
    pnlOverTimeChart = null;
    return;
  }

  const labels = series.map((p) =>
    new Date(p.ts * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    })
  );
  const values = series.map((p) => p.cumulative);

  pnlOverTimeChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Cumulative P&L ($)",
          data: values,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: {
          title: {
            display: true,
            text: "Dollars",
          },
        },
      },
    },
  });
}

/* ---------- HELPERS ---------- */

function getSafeTimestamp(obj) {
  const candidates = [
    "ts",
    "timestamp",
    "time",
    "fill_ts",
    "settlement_ts",
    "created_ts",
    "settled_ts",
  ];

  let raw = null;
  for (const key of candidates) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      raw = obj[key];
      break;
    }
  }

  if (raw == null) return 0;

  if (typeof raw === "string") {
    // ISO string
    const dt = Date.parse(raw);
    if (!Number.isNaN(dt)) {
      return Math.floor(dt / 1000);
    }
  }

  let num = Number(raw);
  if (Number.isNaN(num)) return 0;

  // If it's milliseconds, convert to seconds
  if (num > 10_000_000_000) {
    num = num / 1000;
  }

  return num;
}

function formatTimeCell(obj) {
  const ts = getSafeTimestamp(obj);
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function getMarketLabel(obj) {
  return (
    obj.market_ticker ||
    obj.event_ticker ||
    obj.ticker ||
    obj.market_id ||
    obj.contract_id ||
    "—"
  );
}

function formatPrice(price) {
  if (price == null) return "—";
  const num = Number(price);
  if (Number.isNaN(num)) return String(price);
  return num.toFixed(2);
}

function extractCashChange(settlement) {
  const candidates = [
    "cash_change",
    "cash_change_cents",
    "pnl",
    "realized_pnl",
    "cash_delta",
  ];

  for (const key of candidates) {
    if (Object.prototype.hasOwnProperty.call(settlement, key)) {
      const v = settlement[key];
      if (v == null) return null;
      const num = Number(v);
      if (Number.isNaN(num)) return null;

      // If Kalshi uses cents for this field, it will be relatively large –
      // you can adjust this threshold later if needed.
      if (Math.abs(num) > 10000) {
        return num / 100; // treat as cents -> dollars
      }
      return num;
    }
  }

  return null;
}

function formatDollars(amount, opts = {}) {
  const { showPlus = false } = opts;
  if (amount == null || Number.isNaN(amount)) return "$—";
  const sign = amount > 0 && showPlus ? "+" : "";
  return `${sign}$${amount.toFixed(2)}`;
}

/* ---------- WIRING ---------- */

refreshButton.addEventListener("click", () => {
  fetchSummary();
});

document.addEventListener("DOMContentLoaded", () => {
  fetchSummary();
  setInterval(fetchSummary, REFRESH_MS);
});
