const JSON_URL = "../data/kalshi_summary.json";
const REFRESH_MS = 60_000; // 60 seconds

const statusPill = document.getElementById("status-pill");
const statusText = document.getElementById("status-text");

const lastUpdatedEl = document.getElementById("last-updated");
const noSettlementsNote = document.getElementById("no-settlements-note");

const realizedPnlEl = document.getElementById("realized-pnl");
const cashInEl = document.getElementById("cash-in");
const cashOutEl = document.getElementById("cash-out");
const winRateEl = document.getElementById("win-rate");

const settlementsCountEl = document.getElementById("settlements-count");
const settlementsPill = document.getElementById("settlements-pill");

const tradesCountEl = document.getElementById("trades-count");
const marketsCountEl = document.getElementById("markets-count");
const contractsTradedEl = document.getElementById("contracts-traded");
const grossVolumeEl = document.getElementById("gross-volume");
const avgStakeEl = document.getElementById("avg-stake");
const yesNoBreakdownEl = document.getElementById("yes-no-breakdown");
const activityPill = document.getElementById("activity-pill");

const settlementsTableBody = document.getElementById("settlements-table-body");

const refreshButton = document.getElementById("refresh-button");
const refreshIntervalLabel = document.getElementById("refresh-interval-label");

const pnlByMarketPlaceholder = document.getElementById("pnl-by-market-placeholder");
const pnlOverTimePlaceholder = document.getElementById("pnl-over-time-placeholder");

refreshIntervalLabel.textContent = Math.round(REFRESH_MS / 1000).toString();

// Chart instances
let pnlByMarketChart = null;
let pnlOverTimeChart = null;

/* ------------------ FETCH & STATUS ------------------ */

async function fetchSummary() {
  try {
    setStatus("Loading…", false);

    const cacheBuster = `t=${Date.now()}`;
    const url = JSON_URL.includes("?")
      ? `${JSON_URL}&${cacheBuster}`
      : `${JSON_URL}?${cacheBuster}`;

    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

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

/* ------------------ RENDER MAIN DASHBOARD ------------------ */

function renderDashboard(data) {
  // Time
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

  const hasSettlements = settlements.length > 0;
  noSettlementsNote.style.display = hasSettlements ? "none" : "block";

  // Money stats from settlements
  const settlementStats = computeSettlementStats(settlements);
  renderMoneyCards(settlementStats);

  // Trading activity from fills
  const activityStats = computeActivityStats(fills);
  renderActivityCards(activityStats);

  // Settlements table
  renderSettlementsTable(settlements);

  // Charts
  renderPnlByMarketChart(settlementStats.pnlByMarket);
  renderPnlOverTimeChart(settlementStats.cumulativeSeries);
}

/* ------------------ COMPUTE STATS ------------------ */

function computeSettlementStats(settlements) {
  let realizedPnl = 0;
  let cashIn = 0;
  let cashOut = 0;
  let wins = 0;
  let losses = 0;

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
      wins++;
    } else if (cashChange < 0) {
      cashOut += -cashChange;
      losses++;
    }

    const market = getMarketLabel(s);
    pnlByMarket[market] = (pnlByMarket[market] || 0) + cashChange;

    const ts = getSafeTimestamp(s);
    if (ts) {
      running += cashChange;
      series.push({ ts, cumulative: running });
    }
  }

  const totalSettlements = wins + losses;
  const winRate = totalSettlements > 0 ? (wins / totalSettlements) * 100 : 0;

  settlementsCountEl.textContent = totalSettlements.toString();
  settlementsPill.textContent =
    totalSettlements === 0
      ? "No settlements in last 24h"
      : `${totalSettlements} settlement(s)`;

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

function computeActivityStats(fills) {
  let trades = fills.length;
  const markets = new Set();
  let totalContracts = 0;
  let grossVolume = 0;
  let yesCount = 0;
  let noCount = 0;

  for (const f of fills) {
    const m = getMarketLabel(f);
    markets.add(m);

    const size =
      f.size ??
      f.quantity ??
      f.contracts ??
      f.contracts_count ??
      0;
    const price = Number(f.price ?? 0);

    totalContracts += Number(size) || 0;
    grossVolume += Math.abs((Number(size) || 0) * price);

    const side = (f.side || f.direction || "").toString().toLowerCase();
    if (side === "yes") yesCount++;
    if (side === "no") noCount++;
  }

  const avgStake = trades > 0 ? grossVolume / trades : 0;

  return {
    trades,
    marketsCount: markets.size,
    totalContracts,
    grossVolume,
    avgStake,
    yesCount,
    noCount,
  };
}

/* ------------------ RENDER CARDS / TABLES ------------------ */

function renderMoneyCards(stats) {
  realizedPnlEl.textContent = formatDollars(stats.realizedPnl);
  realizedPnlEl.classList.remove("positive", "negative");
  if (stats.realizedPnl > 0) realizedPnlEl.classList.add("positive");
  if (stats.realizedPnl < 0) realizedPnlEl.classList.add("negative");

  cashInEl.textContent = formatDollars(stats.cashIn);
  cashOutEl.textContent = formatDollars(-stats.cashOut); // show as negative
  cashOutEl.classList.add("negative");

  if (stats.totalSettlements > 0) {
    winRateEl.textContent = `${stats.winRate.toFixed(1)}%`;
  } else {
    winRateEl.textContent = "—";
  }
}

function renderActivityCards(activity) {
  tradesCountEl.textContent =
    activity.trades > 0 ? activity.trades.toString() : "0";

  marketsCountEl.textContent =
    activity.marketsCount > 0 ? activity.marketsCount.toString() : "0";

  contractsTradedEl.textContent =
    activity.totalContracts > 0 ? activity.totalContracts.toString() : "0";

  grossVolumeEl.textContent = formatDollars(activity.grossVolume);
  avgStakeEl.textContent = formatDollars(activity.avgStake);

  if (activity.trades === 0) {
    yesNoBreakdownEl.textContent = "No trades today";
    activityPill.textContent = "No trades in last 24h";
  } else {
    const yesPct =
      activity.trades > 0 ? (activity.yesCount / activity.trades) * 100 : 0;
    const noPct =
      activity.trades > 0 ? (activity.noCount / activity.trades) * 100 : 0;

    yesNoBreakdownEl.textContent = `Yes: ${activity.yesCount} (${yesPct.toFixed(
      0
    )}%) · No: ${activity.noCount} (${noPct.toFixed(0)}%)`;

    activityPill.textContent = `${activity.trades} trade${
      activity.trades === 1 ? "" : "s"
    } in last 24h`;
  }
}

function renderSettlementsTable(settlements) {
  settlementsTableBody.innerHTML = "";

  if (!settlements || settlements.length === 0) {
    settlementsTableBody.innerHTML =
      '<tr><td colspan="4" class="placeholder">No settlements in the last 24 hours.</td></tr>';
    return;
  }

  const sorted = [...settlements].sort((a, b) => {
    const ta = getSafeTimestamp(a);
    const tb = getSafeTimestamp(b);
    return tb - ta;
  });

  sorted.slice(0, 50).forEach((s) => {
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
    if (change === null) {
      cashCell.textContent = "—";
    } else {
      cashCell.textContent = formatDollars(change, { showPlus: true });
      if (change > 0) cashCell.classList.add("positive");
      if (change < 0) cashCell.classList.add("negative");
    }

    tr.appendChild(timeCell);
    tr.appendChild(marketCell);
    tr.appendChild(outcomeCell);
    tr.appendChild(cashCell);

    settlementsTableBody.appendChild(tr);
  });
}

/* ------------------ CHARTS ------------------ */

function renderPnlByMarketChart(pnlByMarket) {
  const canvas = document.getElementById("pnl-by-market-chart");
  if (!canvas) return;

  const labels = Object.keys(pnlByMarket || {});
  const values = labels.map((k) => pnlByMarket[k]);

  if (pnlByMarketChart) pnlByMarketChart.destroy();

  if (!labels.length) {
    canvas.style.display = "none";
    pnlByMarketPlaceholder.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  pnlByMarketPlaceholder.style.display = "none";

  pnlByMarketChart = new Chart(canvas, {
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
      plugins: { legend: { display: false } },
      scales: {
        y: {
          title: { display: true, text: "Dollars" },
        },
      },
    },
  });
}

function renderPnlOverTimeChart(series) {
  const canvas = document.getElementById("pnl-over-time-chart");
  if (!canvas) return;

  if (pnlOverTimeChart) pnlOverTimeChart.destroy();

  if (!series || !series.length) {
    canvas.style.display = "none";
    pnlOverTimePlaceholder.style.display = "block";
    return;
  }

  canvas.style.display = "block";
  pnlOverTimePlaceholder.style.display = "none";

  const labels = series.map((p) =>
    new Date(p.ts * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    })
  );
  const values = series.map((p) => p.cumulative);

  pnlOverTimeChart = new Chart(canvas, {
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
      plugins: { legend: { display: false } },
      scales: {
        y: {
          title: { display: true, text: "Dollars" },
        },
      },
    },
  });
}

/* ------------------ HELPERS ------------------ */

function getSafeTimestamp(obj) {
  const keys = [
    "ts",
    "timestamp",
    "time",
    "fill_ts",
    "settlement_ts",
    "created_ts",
    "settled_ts",
  ];

  for (const k of keys) {
    if (Object.prototype.hasOwnProperty.call(obj, k) && obj[k] != null) {
      const raw = obj[k];

      if (typeof raw === "string") {
        const parsed = Date.parse(raw);
        if (!Number.isNaN(parsed)) return Math.floor(parsed / 1000);
      }

      let num = Number(raw);
      if (Number.isNaN(num)) continue;
      if (num > 10_000_000_000) num = num / 1000; // ms -> s
      return num;
    }
  }
  return 0;
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

function extractCashChange(settlement) {
  const keys = [
    "cash_change",
    "cash_change_cents",
    "pnl",
    "realized_pnl",
    "cash_delta",
  ];

  for (const k of keys) {
    if (Object.prototype.hasOwnProperty.call(settlement, k)) {
      const raw = settlement[k];
      if (raw == null) return null;
      let num = Number(raw);
      if (Number.isNaN(num)) return null;

      // crude “is this cents?” check
      if (Math.abs(num) > 10000) num = num / 100;
      return num;
    }
  }

  return null;
}

function formatDollars(amount, opts = {}) {
  const { showPlus = false } = opts;
  if (amount == null || Number.isNaN(amount)) return "$0.00";
  const sign = amount > 0 && showPlus ? "+" : "";
  return `${sign}$${amount.toFixed(2)}`;
}

/* ------------------ WIRING ------------------ */

refreshButton.addEventListener("click", () => {
  fetchSummary();
});

document.addEventListener("DOMContentLoaded", () => {
  fetchSummary();
  setInterval(fetchSummary, REFRESH_MS);
});
