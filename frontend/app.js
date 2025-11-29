const JSON_URL = "../data/kalshi_summary.json";
const REFRESH_MS = 60_000;

let pnlChart = null;
let breakdownChart = null;

// ---------------------- helpers ---------------------- //

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
    if (raw > 1e12) return raw; // ms
    return raw * 1000; // s
  }
  return null;
}

function formatTime(obj) {
  const ts = getSafeTimestamp(obj);
  if (!ts) return "-";
  return new Date(ts).toLocaleString();
}

// Turn tickers into readable markets
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
    case "KXHIGHAUS":
      label = "HIGHAUS";
      break;
    default:
      label = prefix.replace(/^KX/, "");
      break;
  }

  const restPretty = rest.split("-").join(" • ");
  return `${label} • ${restPretty}`;
}

function setSignedText(el, value) {
  if (!el) return;
  el.textContent = formatCurrency(value, true);
  el.classList.remove("pos", "neg", "zero");
  if (value > 0) el.classList.add("pos");
  else if (value < 0) el.classList.add("neg");
  else el.classList.add("zero");
}

// ---------------------- summary ---------------------- //

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

  // Navbar bubbles
  document.getElementById("nav-account-value").textContent =
    formatCurrency(accountValue);
  const navNet = document.getElementById("nav-net-profit");
  setSignedText(navNet, netProfit);

  // Metric cards
  document.getElementById("metric-deposits").textContent =
    formatCurrency(totalDeposits);
  document.getElementById("metric-account-value").textContent =
    formatCurrency(accountValue);
  document.getElementById("metric-cash").textContent =
    formatCurrency(cash);
  document.getElementById("metric-positions-value").textContent =
    formatCurrency(positionsValue);

  setSignedText(
    document.getElementById("metric-net-profit"),
    netProfit
  );
  setSignedText(
    document.getElementById("metric-realized-pnl"),
    realizedPnl
  );
  setSignedText(
    document.getElementById("metric-unrealized-pnl"),
    unrealizedPnl
  );

  document.getElementById("metric-roi").textContent = toPercent(roi);
  document.getElementById("metric-house-money").textContent =
    toPercent(housePct);

  const genEl = document.getElementById("summary-generated-at");
  if (genEl && data.generated_at) {
    const d = new Date(data.generated_at);
    genEl.textContent = `Updated: ${d.toLocaleString()}`;
  }
}

// ---------------------- charts ---------------------- //

function renderCharts(data) {
  const ctxPnl = document.getElementById("pnlChart");
  const ctxBreakdown = document.getElementById("breakdownChart");
  if (!ctxPnl || !ctxBreakdown) return;

  const stats = data.summary || {};
  const account = data.account || {};

  const series = stats.cumulative_series || [];
  const labels = series.map((p) =>
    new Date(p.ts).toLocaleDateString()
  );
  const values = series.map((p) => Number(p.cumulative || 0));

  if (pnlChart) pnlChart.destroy();
  pnlChart = new Chart(ctxPnl, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Realized P&L",
          data: values,
          tension: 0.2,
        },
      ],
    },
    options: {
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: {
          ticks: { autoSkip: true, maxTicksLimit: 6 },
        },
      },
    },
  });

  const cash = Number(account.cash || 0);
  const positionsValue = Number(account.positions_value || 0);
  const netProfit = Number(stats.net_profit || 0);

  const breakdownLabels = ["Cash", "Positions", "Net Profit"];
  const breakdownValues = [cash, positionsValue, netProfit];

  if (breakdownChart) breakdownChart.destroy();
  breakdownChart = new Chart(ctxBreakdown, {
    type: "doughnut",
    data: {
      labels: breakdownLabels,
      datasets: [
        {
          data: breakdownValues,
        },
      ],
    },
    options: {
      plugins: {
        legend: { position: "bottom" },
      },
    },
  });
}

// ---------------------- trades (simple + table) ---------------------- //

function renderFillsSimple(fills) {
  const list = document.getElementById("fills-simple-list");
  if (!list) return;
  list.innerHTML = "";

  if (!fills || !fills.length) {
    const li = document.createElement("li");
    li.className = "placeholder";
    li.textContent = "No recent trades.";
    list.appendChild(li);
    return;
  }

  const sorted = [...fills].sort(
    (a, b) => (getSafeTimestamp(b) || 0) - (getSafeTimestamp(a) || 0)
  );
  const top = sorted.slice(0, 12);

  for (const f of top) {
    const li = document.createElement("li");

    const size =
      f.count ??
      f.size ??
      f.quantity ??
      f.contracts ??
      f.contracts_count ??
      0;
    const price = Number(f.price || 0);
    const cost = Number(size) * price;

    const main = document.createElement("div");
    main.className = "trade-main-line";

    const timeSpan = document.createElement("span");
    timeSpan.className = "trade-time";
    timeSpan.textContent = formatTime(f);

    const marketSpan = document.createElement("span");
    marketSpan.className = "trade-market";
    marketSpan.textContent = formatTickerReadable(
      f.ticker || f.market || ""
    );

    const actionSpan = document.createElement("span");
    actionSpan.className =
      "trade-action " +
      ((f.action || "").toLowerCase() === "buy"
        ? "trade-buy"
        : "trade-sell");
    actionSpan.textContent = (f.action || "").toUpperCase();

    main.appendChild(timeSpan);
    main.appendChild(document.createTextNode(" • "));
    main.appendChild(marketSpan);
    main.appendChild(document.createTextNode(" • "));
    main.appendChild(actionSpan);

    const extra = document.createElement("div");
    extra.className = "trade-extra";
    extra.textContent = `${size} contracts at ${price.toFixed(
      2
    )}  → cost $${cost.toFixed(2)}`;

    li.appendChild(main);
    li.appendChild(extra);
    list.appendChild(li);
  }
}

function renderFillsTable(fills) {
  const tbody = document.getElementById("fills-table-body");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!fills || !fills.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "placeholder";
    td.textContent = "No recent trades.";
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
    td.textContent = "No recent settlements.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  const sorted = [...settlements].sort(
    (a, b) => (getSafeTimestamp(b) || 0) - (getSafeTimestamp(a) || 0)
  );

  for (const s of sorted) {
    const tr = document.createElement("tr");
    const cashChange =
      Number(s.cash_change ?? s.cashChange ?? 0);

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

// ---------------------- fetch + boot ---------------------- //

async function fetchAndRender() {
  try {
    const resp = await fetch(`${JSON_URL}?t=${Date.now()}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    renderSummary(data);
    renderCharts(data);
    renderFillsSimple(data.fills_last_n_days || []);
    renderFillsTable(data.fills_last_n_days || []);
    renderSettlementsTable(data.settlements_last_n_days || []);
  } catch (err) {
    console.error("Failed to fetch summary JSON:", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  fetchAndRender();
  setInterval(fetchAndRender, REFRESH_MS);
});
