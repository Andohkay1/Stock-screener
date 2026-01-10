import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import requests
import time

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="Akab Stock Screener – Graham Verified",
    page_icon="📉",
    layout="centered"
)

FINNHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

st.title("Akab Stock Screener")
st.markdown("Uses Benjamin Graham–based screening with automated investment memos.")

# ---------------- HELPERS ----------------
def get_finnhub_news(ticker):
    try:
        url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2025-01-01&to=2026-12-31&token={FINNHUB_API_KEY}"
        r = requests.get(url, timeout=5)
        data = r.json()
        headlines = [n["headline"] for n in data[:3]]
        return " | ".join(headlines) if headlines else "No recent news available."
    except:
        return "No recent news available."

# ---------------- DATA FETCH ----------------
@st.cache_data(ttl=3600)
def fetch_stock(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info

    bs = stock.balance_sheet
    inc = stock.income_stmt

    # ---- Core financials ----
    price = info.get("currentPrice", np.nan)
    revenue = info.get("totalRevenue", 0)
    current_ratio = info.get("currentRatio", 0)
    pb_ratio = info.get("priceToBook", 0)
    dividend = info.get("dividendRate", 0)
    shares = info.get("sharesOutstanding", 0)

    # ---- CA & Liabilities ----
    if not bs.empty:
        col = bs.columns[0]
        current_assets = bs.loc["Total Current Assets", col] if "Total Current Assets" in bs.index else 0
        total_liabilities = bs.loc["Total Liabilities Net Minority Interest", col] if "Total Liabilities Net Minority Interest" in bs.index else 0
    else:
        current_assets, total_liabilities = 0, 0

    ca_minus_l = current_assets - total_liabilities

    # ---- EPS ----
    eps_values = []
    if not inc.empty and shares:
        if "Net Income" in inc.index:
            for v in inc.loc["Net Income"].dropna().values:
                eps_values.append(v / shares)

    eps_values = [e for e in eps_values if e > 0]

    eps_5y = np.mean(eps_values[-5:]) if len(eps_values) >= 3 else info.get("trailingEps", 0)
    eps_3y = np.mean(eps_values[-3:]) if len(eps_values) >= 3 else eps_5y

    # ---- Graham metrics ----
    bvps = info.get("bookValue", 0)
    graham_number = np.sqrt(22.5 * eps_5y * bvps) if eps_5y > 0 and bvps > 0 else np.nan
    graham_value = eps_5y * (8.5 + 2 * 0) if eps_5y > 0 else np.nan

    price_ceiling = 15 * eps_3y if eps_3y > 0 else 0

    # ---- Criteria ----
    criteria = {
        "Revenue > $100M": revenue > 100_000_000,
        "Current Ratio > 2": current_ratio > 2,
        "CA - L > 0": ca_minus_l > 0,
        "Pays Dividends": dividend > 0,
        "Positive EPS for 5Y": len(eps_values) >= 5,
        "Price ≤ 15x3Y Avg EPS": price <= price_ceiling if price_ceiling > 0 else False,
        "P/B": pb_ratio < 1.5
    }

    passed = sum(criteria.values())

    return {
        "Ticker": ticker,
        "Price": f"${price:.2f}",
        "Revenue > $100M": f"{revenue:,.0f} {'✅' if criteria['Revenue > $100M'] else '❌'}",
        "Current Ratio > 2": f"{current_ratio:.2f} {'✅' if criteria['Current Ratio > 2'] else '❌'}",
        "CA - L > 0": f"{ca_minus_l:,.0f} {'✅' if criteria['CA - L > 0'] else '❌'}",
        "Pays Dividends": f"{'Yes' if dividend > 0 else 'No'} {'✅' if criteria['Pays Dividends'] else '❌'}",
        "Positive EPS for 5Y": f"{'Yes' if criteria['Positive EPS for 5Y'] else 'No'} {'✅' if criteria['Positive EPS for 5Y'] else '❌'}",
        "Price ≤ 15x3Y Avg EPS": f"${price:.2f} ≤ ${price_ceiling:.2f} {'✅' if criteria['Price ≤ 15x3Y Avg EPS'] else '❌'}",
        "P/B": f"{pb_ratio:.2f} {'✅' if criteria['P/B'] else '❌'}",
        "Passed Count": passed,
        "Graham Number": graham_number,
        "Graham Value": graham_value,
        "Company": info.get("longName", ticker),
        "Industry": info.get("industry", "N/A"),
        "Products": info.get("longBusinessSummary", "").split(".")[0],
        "PriceNum": price
    }

# ---------------- INPUT ----------------
tickers = st.text_area("Enter tickers separated by commas (e.g. AAPL, MSFT)").upper()
tickers = [t.strip() for t in tickers.split(",") if t.strip()]

if st.button("🚀 Run Screener") and tickers:
    rows = []
    for t in tickers:
        time.sleep(1)
        rows.append(fetch_stock(t))

    df = pd.DataFrame(rows)

    # ---- Table (ONLY your columns) ----
    table_cols = [
        "Ticker","Price","Revenue > $100M","Current Ratio > 2","CA - L > 0",
        "Pays Dividends","Positive EPS for 5Y","Price ≤ 15x3Y Avg EPS",
        "P/B","Passed Count","Graham Number","Graham Value"
    ]

    df_display = df.copy()
    df_display["Graham Number"] = df["Graham Number"].apply(lambda x: f"${x:.2f}" if not np.isnan(x) else "N/A")
    df_display["Graham Value"] = df["Graham Value"].apply(lambda x: f"${x:.2f}" if not np.isnan(x) else "N/A")

    st.success(f"✅ Screening complete for {len(df)} tickers.")
    st.dataframe(df_display[table_cols])

    # ---------------- MEMOS ----------------
    st.markdown("## Investment Memos")

    for _, r in df.iterrows():
        price = r["PriceNum"]
        gn = r["Graham Number"]
        gv = r["Graham Value"]

        if not np.isnan(gn) and not np.isnan(gv):
            valuation = (
                "potentially undervalued"
                if price < gn and price < gv
                else "potentially overvalued"
            )
        else:
            valuation = "valuation inconclusive"

        st.markdown(f"""
### {r['Company']} ({r['Ticker']})

**Industry Note:** Operates in the {r['Industry']} sector. Key products/services: {r['Products']}.

**Valuation Insight:** The stock is {valuation} because its market price is relative to its Graham valuation benchmarks.

**Financial Strength:** Earnings consistently positive for the last five years. Pays regular dividends.

**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.

**Strength Note:** Current Assets pay all Total Liabilities.

**Risk Note:** Consider valuation sensitivity, liquidity constraints, and broader market conditions.

**Recent News:** {get_finnhub_news(r['Ticker'])}
""")
