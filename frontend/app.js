// JavaScript for the Kalshi Portfolio Tracker

const JSON_URL = "../data/kalshi_summary.json";
const REFRESH_MS = 60_000;

// --------------------------------------------------
// Helpers
// --------------------------------------------------

function formatCurrency(value, withSign = false) {
  const n = Number(value || 0);
  const sign = withSign && n > 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}

function toPercent(value) {
  const n = Number(value || 0);
  return `${n.toFixed(1)}%`;
}

function getSafeTimestamp(obj) {
  if (!obj) return null;
  const raw = obj.created_time || obj.ts || obj.timestamp || obj.updated_ts;
  if (!raw) return null;

  if (typeof raw === "string") {
    const d = new Date(raw);
    if (!isNaN(d)) return d.getTime();
    return null;
  }

  if (typeof raw === "number") {
    // seconds vs ms
    if (raw > 1e12) return raw;
    return raw * 1000;
  }

  return null;
}

function formatTime(obj) {
  const ts = getSafeTimestamp(obj);
  if (!ts) return "-";
  return new Date(ts).toLocaleString();
}

// Rough ticker cleaner: turn
//   KXNFLGAME-25NOV27CINBAL-CIN
// into
//   NFL Game • 25NOV27CINBAL • CIN
function formatTickerReadable(ticker) {
  if (!ticker || typeof ticker !== "string") return "";

  const parts = ticker.split("-");
  if (parts.length === 1) return ticker;

  const prefix = parts[0];
  const rest = parts.slice(1).join("-");

  let label;
  switch (prefix) {
    case "KXNFLGAME":
      label = "NFL Game";
      break;
    case "KXNCAAFGAME":
      label = "NCAA Football";
      break;
    case "KXHEISMAN":
      label = "Heisman";
      break;
    case "KXZELENSKYYPUTINMEET":
      label = "Zelenskyy–Putin Meet";
      break;
    default:
      label = prefix.replace(/^KX/, "");
      break;
  }

  // Split remaining components for readability
  const restPretty = rest.split("-").join(" • ");
  return `${label} • ${restPretty}`;
}

// apply sign + color class
function setSignedCell(id, value) {
  const el = document.getElementById(id);
  if (!el) return;

  el.textContent = formatCurrency(value, true);
  el.classList.remove("pos", "neg", "zero");
  if (value > 0) el.classList.add("pos");
  else if (value < 0) el.classList.add("neg");
  else el.classList.add("zero");
}

// --------------------------------------------------
// Rendering summary
// --------------------------------------------------

function renderSummary(data) {
  const account = data.account || {};
  const stats = data.summary || {};

  const cash = Number(account.cash || 0);
  const positionsValue = Number(account.positions_value || 0);
  const accountValue = Number(account.portfolio_total || 0);

  const totalDeposits = Number(stats.total_deposits || 0);
  const realizedPnl = Number(stats.realized_pnl || 0);
  const unrealizedPnl = Number(stats.unrealized_pnl || 0);
  const netProfit = Number(stats.net_profit || 0);
  const housePct = Number(stats.house_money_pct || 0);

  const roi =
    totalDeposits > 0 ? (netProfit / totalDeposits) * 100.0 : 0.0;

  // Header metrics
  document.getElementById("metric-account-value").textContent =
    formatCurrency(accountValue);
  document.getElementById("metric-cash").textContent =
    formatCurrency(cash);
  document.getElementById("metric-deposits").textContent =
    formatCurrency(totalDeposits);
  setSignedCell("metric-net-profit", netProfit);

  // Summary table
  document.getElementById("cell-total-deposits").textContent =
    formatCurrency(totalDeposits);
  document.getElementById("cell-cash").textContent =
    formatCurrency(cash);
  document.getElementById("cell-positions-value").textContent =
    formatCurrency(positionsValue);
  document.getElementById("cell-account-value").textContent =
    formatCurrency(accountValue);
  setSignedCell("cell-realized-pnl", realizedPnl);
  setSignedCell("cell-unrealized-pnl", unrealizedPnl);
  setSignedCell("cell-net-profit", netProfit);
  document.getElementById("cell-roi").textContent = toPercent(roi);

  const genEl = document.getElementById("summary-generated-at");
  if (genEl && data.generated_at) {
    const d = new Date(data.generated_at);
    genEl.textContent = `Updated: ${d.toLocaleString()}  |  House money: ${toPercent(
      housePct
    )} of portfolio`;
  }
}

// --------------------------------------------------
// Rendering tables
// --------------------------------------------------

function renderFillsTable(fills) {
  const tbody = document.getElementById("fills-table-body");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!fills || !fills.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "placeholder";
    td.textContent = "No fills in the selected window";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  const sorted = [...fills].sort(
    (a, b) => (getSafeTimestamp(b) || 0) - (getSafeTimestamp(a) || 0)
  );

  for (const f of sorted) {
    const tr = document.createElement("tr");

    const size =
      f.count ??
      f.size ??
      f.quantity ??
      f.contracts ??
      f.contracts_count ??
      0;
    const price = Number(f.price || 0);
    const cost = Number(size) * price;

    tr.innerHTML = `
      <td>${formatTime(f)}</td>
      <td>${formatTickerReadable(f.ticker || f.market || "")}</td>
      <td>${(f.action || "").toUpperCase()}</td>
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

  if (!settlements || !settlements.length) {
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
    (a, b) => (getSafeTimestamp(b) || 0) - (getSafeTimestamp(a) || 0)
  );

  for (const s of sorted) {
    const cashChange =
      Number(s.cash_change ?? s.cashChange ?? 0);

    const tr = document.createElement("tr");
    const cashCell = document.createElement("td");
    cashCell.textContent = formatCurrency(cashChange, true);
    cashCell.classList.add(
      cashChange > 0 ? "pos" : cashChange < 0 ? "neg" : "zero"
    );

    tr.innerHTML = `
      <td>${formatTime(s)}</td>
      <td>${formatTickerReadable(s.ticker || s.market || "")}</td>
      <td>${s.outcome || s.final_position || s.finalPosition || ""}</td>
    `;
    tr.appendChild(cashCell);

    tbody.appendChild(tr);
  }
}

// --------------------------------------------------
// Fetch + boot
// --------------------------------------------------

async function fetchAndRender() {
  try {
    const url = `${JSON_URL}?t=${Date.now()}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    renderSummary(data);
    renderFillsTable(data.fills_last_n_days || []);
    renderSettlementsTable(data.settlements_last_n_days || []);
  } catch (err) {
    console.error("Failed to fetch summary JSON:", err);
  }
}

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
