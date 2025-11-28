const JSON_URL = "../data/kalshi_summary.json";
const REFRESH_MS = 60_000; // 60s – frontend refresh interval

const statusPill = document.getElementById("status-pill");
const statusText = document.getElementById("status-text");
const lastUpdatedEl = document.getElementById("last-updated");
const fillsCountEl = document.getElementById("fills-count");
const settlementsCountEl = document.getElementById("settlements-count");
const fillsPill = document.getElementById("fills-pill");
const settlementsPill = document.getElementById("settlements-pill");
const fillsTableBody = document.getElementById("fills-table-body");
const settlementsTableBody = document.getElementById("settlements-table-body");
const refreshButton = document.getElementById("refresh-button");
const refreshIntervalLabel = document.getElementById("refresh-interval-label");

refreshIntervalLabel.textContent = Math.round(REFRESH_MS / 1000).toString();

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
  // Top summary
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

  renderFillsTable(fills);
  renderSettlementsTable(settlements);
}

function renderFillsTable(fills) {
  fillsTableBody.innerHTML = "";

  if (fills.length === 0) {
    fillsTableBody.innerHTML =
      '<tr><td colspan="5" class="placeholder">No fills in the last 24 hours.</td></tr>';
    return;
  }

  // Show most recent first if we have timestamps
  const sorted = [...fills].sort((a, b) => {
    const ta = getSafeTimestamp(a);
    const tb = getSafeTimestamp(b);
    return tb - ta;
  });

  sorted.slice(0, 30).forEach((fill) => {
    const tr = document.createElement("tr");

    const timeCell = document.createElement("td");
    timeCell.textContent = formatTimeCell(fill);

    const marketCell = document.createElement("td");
    marketCell.textContent =
      fill.market_ticker ||
      fill.event_ticker ||
      fill.ticker ||
      fill.contract_id ||
      "—";

    const sideCell = document.createElement("td");
    sideCell.textContent = fill.side || fill.direction || "—";

    const sizeCell = document.createElement("td");
    sizeCell.textContent = fill.size ?? fill.quantity ?? "—";

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

  sorted.slice(0, 30).forEach((settlement) => {
    const tr = document.createElement("tr");

    const timeCell = document.createElement("td");
    timeCell.textContent = formatTimeCell(settlement);

    const marketCell = document.createElement("td");
    marketCell.textContent =
      settlement.market_ticker ||
      settlement.event_ticker ||
      settlement.ticker ||
      "—";

    const outcomeCell = document.createElement("td");
    outcomeCell.textContent =
      settlement.outcome || settlement.result || settlement.position || "—";

    const cashCell = document.createElement("td");
    cashCell.textContent = formatCashChange(settlement);

    tr.appendChild(timeCell);
    tr.appendChild(marketCell);
    tr.appendChild(outcomeCell);
    tr.appendChild(cashCell);

    settlementsTableBody.appendChild(tr);
  });
}

// Helpers

function getSafeTimestamp(obj) {
  const raw =
    obj.ts || obj.time || obj.timestamp || obj.settled_ts || obj.created_ts;
  if (raw == null) return 0;

  let num = typeof raw === "number" ? raw : Number(raw);
  if (isNaN(num)) return 0;

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
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatPrice(price) {
  if (price == null) return "—";
  const num = Number(price);
  if (isNaN(num)) return String(price);
  return num.toFixed(2);
}

function formatCashChange(settlement) {
  const possibleFields = [
    "cash_change",
    "cash_change_cents",
    "pnl",
    "realized_pnl",
  ];

  let value = null;

  for (const key of possibleFields) {
    if (Object.prototype.hasOwnProperty.call(settlement, key)) {
      value = settlement[key];
      break;
    }
  }

  if (value == null) return "—";

  const num = Number(value);
  if (isNaN(num)) return String(value);

  // Not assuming cents vs dollars; just show with 2 decimals
  return num.toFixed(2);
}

// Wiring

refreshButton.addEventListener("click", () => {
  fetchSummary();
});

document.addEventListener("DOMContentLoaded", () => {
  fetchSummary();
  setInterval(fetchSummary, REFRESH_MS);
});
