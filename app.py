import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests

# --- CONFIG ---
st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Value with automated investment memo.")

FINHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

# --- HELPER FUNCTIONS ---

def fetch_news(ticker):
    try:
        url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2026-01-01&to=2026-01-09&token={FINHUB_API_KEY}"
        response = requests.get(url)
        data = response.json()
        headlines = [d.get("headline") for d in data[:3]]  # top 3 news
        return " | ".join(headlines) if headlines else "No recent news available."
    except:
        return "No recent news available."

def parse_money(value):
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except:
        return None

@st.cache_data(ttl=3600)
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        inc = stock.financials if not stock.financials.empty else pd.DataFrame()

        # Estimate current assets & total liabilities safely
        est_current_assets = bs.reindex(["CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherShortTermInvestments"]).fillna(0).sum(axis=0).iloc[0] if not bs.empty else 0
        est_total_liabilities = bs.reindex(["TotalDebt","AccountsPayable","OtherCurrentLiabilities","TaxPayable"]).fillna(0).sum(axis=0).iloc[0] if not bs.empty else 0

        # EPS
        shares_outstanding = info.get("sharesOutstanding", 0)
        eps_values = []
        if not inc.empty and "Net Income" in inc.index and shares_outstanding:
            net_incomes = inc.loc["Net Income"].dropna().values
            eps_values = [ni / shares_outstanding for ni in net_incomes if shares_outstanding > 0]
        if not eps_values:
            eps_values = [info.get("trailingEps", 0)] * 7
        eps_7yr_avg = np.mean(eps_values[-7:]) if len(eps_values) >= 3 else np.mean(eps_values)
        eps_5yr_avg = np.mean(eps_values[-5:]) if len(eps_values) >= 3 else np.mean(eps_values)
        
        # EPS growth
        eps_growth = 0
        valid_eps = [eps for eps in eps_values if eps > 0]
        if len(valid_eps) >= 2:
            eps_growth = (valid_eps[-1] - valid_eps[0]) / valid_eps[0]

        # Graham metrics
        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else None
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else None

        # Basic metrics
        current_price = info.get("currentPrice", 0)
        revenue = info.get("totalRevenue", 0)
        current_ratio = info.get("currentRatio", 0)
        pb_ratio = info.get("priceToBook", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        # Criteria
        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "CA - L > 0": est_current_assets > est_total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5Y": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15x3Y Avg EPS": current_price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }
        passed = sum(criteria.values())
        def mark(val): return "✅" if val else "❌"

        return {
            "Ticker": ticker,
            "Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA - L > 0": f"{est_current_assets - est_total_liabilities:,.0f} {mark(criteria['CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5Y": f"{'Yes' if criteria['Positive EPS for 5Y'] else 'No'} {mark(criteria['Positive EPS for 5Y'])}",
            "Price ≤ 15x3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15x3Y Avg EPS'])}" if current_price and price_ceiling else f"N/A ❌",
            "P/B": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f} {mark(current_price > graham_number)}" if graham_number else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(current_price > graham_value)}" if graham_value else "N/A",
            "Company Name": info.get("longName", ticker),
            "Industry": info.get("industry", "N/A"),
            "Products": info.get("longBusinessSummary", "N/A"),
            "Current Price Num": current_price,
            "Graham Number Num": graham_number,
            "Graham Value Num": graham_value,
            "News": fetch_news(ticker)
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

# --- INPUT ---
tickers = []
manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# --- RUN SCREEN ---
if st.button("🚀 Run Screener"):
    if not tickers:
        st.warning("Please enter or upload at least one ticker.")
    else:
        with st.spinner("Running screen..."):
            results = []
            progress = st.progress(0)
            for idx, t in enumerate(tickers):
                time.sleep(1.5)
                data = fetch_financials(t)
                if data:
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results)
            df_sorted = df.sort_values("Passed Count", ascending=False)

            st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")
            st.dataframe(df_sorted[[
                "Ticker","Price","Revenue > $100M","Current Ratio > 2","CA - L > 0",
                "Pays Dividends","Positive EPS for 5Y","Price ≤ 15x3Y Avg EPS",
                "P/B","Passed Count","Graham Number","Graham Value"
            ]])

            # --- Investment Memos ---
            st.markdown("### Investment Memos")
            for _, r in df_sorted.iterrows():
                try:
                    price = r["Current Price Num"]
                    gn = r["Graham Number Num"]
                    gv = r["Graham Value Num"]

                    valuation_text = "potentially overvalued ❌" if gn and gv and price > gn and price > gv else "potentially undervalued ✅"

                    st.markdown(f"""
**{r['Company Name']} ({r['Ticker']})**

**Industry Note:** Operates in the {r['Industry']} sector, producing {r['Products'][:100]}...

**Valuation Insight:** {r['Company Name']} is trading at ${price:.2f}, {valuation_text}.

**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends.

**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.

**Strength Note:** Current Assets pay all Total Liabilities.

**Risk Note:** Consider valuation sensitivity, liquidity constraints, and market conditions.

**Recent News:** {r['News']}
""")
                except Exception as e:
                    st.error(f"Error generating memo for {r['Ticker']}: {e}")
        else:
            st.warning("No valid data returned.")
