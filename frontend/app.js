// JavaScript for the Kalshi Portfolio Dashboard

const JSON_URL = "../data/kalshi_summary.json";
const REFRESH_MS = 60_000; // 60s

// ------------------------------
// Entry point
// ------------------------------
async function fetchAndRender() {
  try {
    const cacheBuster = `t=${Date.now()}`;
    const url = JSON_URL.includes("?")
      ? `${JSON_URL}&${cacheBuster}`
      : `${JSON_URL}?${cacheBuster}`;

    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();

    const account = data.account || {};
    const summary = data.summary || {};

    // --- Core numbers from backend (with safe defaults) ---
    const deposits = toNumber(summary.total_deposits, 0);
    const cash = toNumber(account.cash, 0);

    // portfolio_total comes from Kalshi's portfolio_value (via backend)
    let portfolioTotal = toNumber(account.portfolio_total, NaN);
    if (!Number.isFinite(portfolioTotal)) {
      // Fallback: if portfolio_total isn't present for some reason,
      // approximate as cash + positions_value (older backend behavior).
      portfolioTotal =
        cash + toNumber(account.positions_value, 0);
    }

    // Money in bets (positions value).
    // This is the important fix:
    // If backend gave us positions_value and it's non-trivial, use it.
    // Otherwise, compute it directly as portfolio - cash.
    let positionsValue = toNumber(account.positions_value, NaN);
    if (!Number.isFinite(positionsValue) || Math.abs(positionsValue) < 0.01) {
      positionsValue = Math.max(portfolioTotal - cash, 0);
    }

    // Net profit: prefer backend's net_profit, fallback to portfolio - deposits.
    const netProfit = toNumber(
      summary.net_profit,
      portfolioTotal - deposits,
    );

    // Realized P&L (closed bets) from backend
    const realizedPnL = toNumber(summary.realized_pnl, 0);

    // Unrealized P&L: backend field if present, otherwise netProfit - realized
    let unrealizedPnL;
    if (summary.unrealized_pnl !== undefined && summary.unrealized_pnl !== null) {
      unrealizedPnL = toNumber(summary.unrealized_pnl, 0);
    } else {
      unrealizedPnL = netProfit - realizedPnL;
    }

    // ROI: backend net_profit_percent is a fraction (e.g. 0.37),
    // otherwise compute from current numbers.
    let roiFraction;
    if (summary.net_profit_percent !== undefined && summary.net_profit_percent !== null) {
      roiFraction = toNumber(summary.net_profit_percent, 0);
    } else {
      roiFraction = deposits > 0 ? netProfit / deposits : 0;
    }
    const roiPercent = roiFraction * 100;

    // ------------------------------
    // Update NAV "bubbles" at the top
    // ------------------------------
    updateText("nav-portfolio-total", formatCurrency(portfolioTotal));
    updateText("nav-cash", formatCurrency(cash));
    updateText("nav-deposits", formatCurrency(deposits));
    updateText("nav-profit", formatCurrency(netProfit, true));

    // ------------------------------
    // Update main summary table
    // ------------------------------
    updateText("summary-deposits", formatCurrency(deposits));
    updateText("summary-cash", formatCurrency(cash));
    updateText("summary-positions", formatCurrency(positionsValue));
    updateText("summary-portfolio", formatCurrency(portfolioTotal));
    updateText("summary-realized-pnl", formatCurrency(realizedPnL, true));
    updateText("summary-unrealized-pnl", formatCurrency(unrealizedPnL, true));
    updateText("summary-net-profit", formatCurrency(netProfit, true));
    updateText("summary-roi", `${roiPercent.toFixed(2)}%`);

    // ------------------------------
    // Render tables (fills & settlements)
    // ------------------------------
    const fills = Array.isArray(data.fills_last_n_days)
      ? data.fills_last_n_days
      : [];
    const settlements = Array.isArray(data.settlements_last_n_days)
      ? data.settlements_last_n_days
      : [];

    renderFillsTable(fills);
    renderSettlementsTable(settlements);

    // ------------------------------
    // Refresh label
    // ------------------------------
    const refreshIntervalLabel = document.getElementById(
      "refresh-interval-label",
    );
    if (refreshIntervalLabel) {
      refreshIntervalLabel.textContent = String(Math.round(REFRESH_MS / 1000));
    }
  } catch (err) {
    console.error("Error loading summary:", err);
  }
}

// ------------------------------
// Helpers
// ------------------------------
function toNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function formatCurrency(value, showSign = false) {
  const num = toNumber(value, 0);
  const abs = Math.abs(num);
  const sign =
    showSign && num > 0
      ? "+"
      : showSign && num < 0
      ? "-"
      : "";
  const formatted = abs.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return sign ? `${sign}${formatted.slice(1)}` : formatted;
}

function updateText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// Safely extract a timestamp (ms) from API objects
function getSafeTimestamp(obj) {
  if (!obj || typeof obj !== "object") return null;
  const raw =
    obj.ts ??
    obj.timestamp ??
    obj.created_time ??
    obj.createdTime ??
    obj.settled_time ??
    null;
  if (!raw) return null;

  // Assume backend uses ms; if it's too small, treat as seconds
  const n = Number(raw);
  if (!Number.isFinite(n)) return null;
  if (n > 1_000_000_000_000) return n;
  return n * 1000;
}

function formatDateTime(tsMs) {
  if (!tsMs) return "";
  const d = new Date(tsMs);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ------------------------------
// Human-readable ticker formatter
// ------------------------------
function formatTickerReadable(ticker) {
  if (!ticker || typeof ticker !== "string") return "";

  // NFL game example: KXNFLGAME-25NOV28CHIPHI-CHI
  if (ticker.startsWith("KXNFLGAME-")) {
    const parts = ticker.split("-");
    if (parts.length >= 3) {
      const dateTeams = parts[1]; // e.g. 25NOV28CHIPHI
      const side = parts[2]; // CHI / PHI

      if (dateTeams.length >= 13) {
        const yy = dateTeams.slice(0, 2);
        const mon = dateTeams.slice(2, 5).toUpperCase();
        const dd = dateTeams.slice(5, 7);
        const team1 = dateTeams.slice(7, 10).toUpperCase();
        const team2 = dateTeams.slice(10, 13).toUpperCase();

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
        return `NFL Game • ${matchup} • ${dateLabel} • ${side}`;
      }
    }
  }

  // NCAA football example: KXNCAAFGAME-25NOV28TXAMTEX-TEX
  if (ticker.startsWith("KXNCAAFGAME-")) {
    const parts = ticker.split("-");
    if (parts.length >= 3) {
      const dateTeams = parts[1];
      const side = parts[2];
      if (dateTeams.length >= 13) {
        const yy = dateTeams.slice(0, 2);
        const mon = dateTeams.slice(2, 5).toUpperCase();
        const dd = dateTeams.slice(5, 7);
        const team1 = dateTeams.slice(7, 10).toUpperCase();
        const team2 = dateTeams.slice(10, 13).toUpperCase();

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
        return `NCAA Football • ${matchup} • ${dateLabel} • ${side}`;
      }
    }
  }

  // Heisman / politics / other: just return something readable
  return ticker;
}

// ------------------------------
// Fills table
// ------------------------------
function renderFillsTable(fills) {
  const tbody = document.getElementById("fills-table-body");
  if (!tbody) return;

  tbody.innerHTML = "";

  if (!fills.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "placeholder";
    td.textContent = "No recent fills in this window";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  const sorted = [...fills].sort(
    (a, b) => (getSafeTimestamp(b) || 0) - (getSafeTimestamp(a) || 0),
  );

  for (const f of sorted) {
    const tr = document.createElement("tr");

    const tsMs = getSafeTimestamp(f);
    const timeCell = formatDateTime(tsMs);

    const ticker = f.ticker ?? f.market_ticker ?? "";
    const side = (f.action ?? "").toUpperCase();
    const size = toNumber(f.size ?? f.count, 0);
    const price = toNumber(f.price, 0);
    const cost = size * price;

    const tds = [
      timeCell,
      formatTickerReadable(ticker),
      side || "",
      size.toString(),
      price.toFixed(2),
      formatCurrency(cost),
    ];

    for (const text of tds) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }

    tbody.appendChild(tr);
  }
}

// ------------------------------
// Settlements table
// ------------------------------
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
    (a, b) => (getSafeTimestamp(b) || 0) - (getSafeTimestamp(a) || 0),
  );

  for (const s of sorted) {
    const tr = document.createElement("tr");

    const tsMs = getSafeTimestamp(s);
    const when = formatDateTime(tsMs);

    const ticker = s.ticker ?? s.market_ticker ?? "";
    const readableTicker = formatTickerReadable(ticker);

    const rawChange = extractCashChange(s);
    const isWin = rawChange !== null && rawChange > 0;
    const isLoss = rawChange !== null && rawChange < 0;
    const pnlText =
      rawChange === null ? "" : formatCurrency(rawChange / 100, true); // settlements often in cents

    const tds = [
      when,
      readableTicker,
      isWin ? "Win" : isLoss ? "Loss" : "",
      pnlText,
    ];

    for (const text of tds) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }

    tbody.appendChild(tr);
  }
}

// ------------------------------
// Boot the app
// ------------------------------
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
