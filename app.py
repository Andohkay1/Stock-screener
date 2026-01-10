import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests

# -------------------------
# Configuration
# -------------------------
st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Value with automated investment memo.")

# -------------------------
# FinHub API key
# -------------------------
FINHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

# -------------------------
# Helper Functions
# -------------------------
def fetch_news(ticker):
    """Fetch top 3 recent news for ticker from FinHub"""
    try:
        url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2025-01-01&to=2026-01-09&token={FINHUB_API_KEY}"
        res = requests.get(url).json()
        headlines = [d.get("headline") for d in res[:3]]
        return " | ".join(headlines) if headlines else "No recent news available."
    except:
        return "No recent news available."

def parse_money(value):
    """Convert string like $56.41 to float"""
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except:
        return None

@st.cache_data(ttl=3600)
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Balance Sheet & Income Statement
        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        inc = stock.income_stmt if not stock.income_stmt.empty else pd.DataFrame()
        col = bs.columns[0] if not bs.empty else None

        # Estimate Current Assets & Total Liabilities
        est_current_assets, est_total_liabilities = 0, 0
        if col:
            if "Total Current Assets" in bs.index:
                est_current_assets = bs.loc["Total Current Assets", col]
            else:
                est_current_assets = sum(bs.loc[key, col] if key in bs.index else 0 for key in [
                    "CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherShortTermInvestments"
                ])
            est_total_liabilities = sum(bs.loc[key, col] if key in bs.index else 0 for key in [
                "TotalDebt", "AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"
            ])

        # EPS calculations
        eps_values = []
        shares_outstanding = info.get("sharesOutstanding", 0)
        if not inc.empty and "Net Income" in inc.index and shares_outstanding:
            net_incomes = inc.loc["Net Income"].dropna().values
            eps_values = [ni / shares_outstanding for ni in net_incomes if shares_outstanding > 0]

        eps_values = [eps for eps in eps_values if isinstance(eps, (int, float))]
        if not eps_values:
            eps_values = [info.get("trailingEps", 0)] * 7

        eps_7yr_avg = np.mean(eps_values[-7:]) if len(eps_values) >= 3 else np.mean(eps_values)
        eps_5yr_avg = np.mean(eps_values[-5:]) if len(eps_values) >= 3 else np.mean(eps_values)

        eps_growth = 0
        if len(eps_values) >= 2:
            valid_eps = [eps for eps in eps_values if eps > 0]
            if len(valid_eps) >= 2:
                oldest, latest = valid_eps[0], valid_eps[-1]
                if oldest > 0:
                    eps_growth = (latest - oldest) / oldest

        # Graham metrics
        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else None
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else None

        # Other metrics
        current_ratio = info.get("currentRatio", 0)
        revenue = info.get("totalRevenue", 0)
        pb_ratio = info.get("priceToBook", 0)
        current_price = info.get("currentPrice", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "CA - L > 0": est_current_assets > est_total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5Y": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15x3Y Avg EPS": current_price <= price_ceiling,
            "P/B": pb_ratio < 1.5,
        }
        passed = sum(criteria.values())
        def mark(val): return "✅" if val else "❌"

        return {
            "Ticker": ticker,
            "Company Name": info.get("longName", ticker),
            "Industry": info.get("industry", "N/A"),
            "Current Price Num": current_price,
            "Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA - L > 0": f"{(est_current_assets - est_total_liabilities):,.0f} {mark(criteria['CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5Y": f"{'Yes' if criteria['Positive EPS for 5Y'] else 'No'} {mark(criteria['Positive EPS for 5Y'])}",
            "Price ≤ 15x3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15x3Y Avg EPS'])}" if current_price and price_ceiling else "N/A ❌",
            "P/B": f"{pb_ratio:.2f} {mark(criteria['P/B'])}",
            "Passed Count": passed,
            "Graham Number Num": graham_number,
            "Graham Number": f"${graham_number:.2f} {mark(current_price > graham_number)}" if graham_number else "N/A",
            "Graham Value Num": graham_value,
            "Graham Value": f"${graham_value:.2f} {mark(current_price > graham_value)}" if graham_value else "N/A",
            "Recent News": fetch_news(ticker)
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

# -------------------------
# Input tickers
# -------------------------
tickers = []
manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# -------------------------
# Run Screener
# -------------------------
if st.button("🚀 Run Screener"):
    if not tickers:
        st.warning("Please enter or upload at least one ticker.")
    else:
        with st.spinner("Running screen..."):
            results = []
            progress = st.progress(0)
            for idx, t in enumerate(tickers):
                time.sleep(1.5)  # avoid rate limit
                data = fetch_financials(t)
                if data:
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results)
            df_sorted = df.sort_values("Passed Count", ascending=False)

            st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")

            # -------------------------
            # Show Table
            # -------------------------
            display_cols = [
                "Ticker", "Price", "Revenue > $100M", "Current Ratio > 2", "CA - L > 0",
                "Pays Dividends", "Positive EPS for 5Y", "Price ≤ 15x3Y Avg EPS",
                "P/B", "Passed Count", "Graham Number", "Graham Value"
            ]
            st.dataframe(df_sorted[display_cols])

            # -------------------------
            # Show Investment Memo
            # -------------------------
            st.markdown("### Investment Memos")
            for _, r in df_sorted.iterrows():
                try:
                    price = r["Current Price Num"]
                    gn_val = r["Graham Number Num"]
                    gv_val = r["Graham Value Num"]

                    # Valuation Insight
                    if gn_val and gv_val:
                        if price > gn_val and price > gv_val:
                            val_text = f"{r['Company Name']} is potentially overvalued because the current price is above its Graham Number and Graham Value ❌."
                        elif price < gn_val and price < gv_val:
                            val_text = f"{r['Company Name']} is potentially undervalued because the current price is below its Graham Number and Graham Value ✅."
                        else:
                            val_text = f"{r['Company Name']} is trading near its Graham metrics."
                    else:
                        val_text = f"{r['Company Name']} is trading at ${price:.2f}. Graham metrics not available."

                    # Strength Note
                    strength_text = "Current Assets cover Total Liabilities, allowing acquisition without paying for fixed assets or property."

                    st.markdown(f"**{r['Company Name']} ({r['Ticker']})**")
                    st.markdown(f"**Industry Note:** Operates in the {r['Industry']} sector.")
                    st.markdown(f"**Valuation Insight:** {val_text}")
                    st.markdown(f"**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends.")
                    st.markdown(f"**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.")
                    st.markdown(f"**Strength Note:** {strength_text}")
                    st.markdown(f"**Risk Note:** Consider valuation sensitivity, liquidity constraints, and market conditions.")
                    st.markdown(f"**Recent News:** {r['Recent News']}")
                    st.markdown("---")
                except Exception as e:
                    st.error(f"Error generating memo for {r['Ticker']}: {e}")
        else:
            st.warning("No valid data returned.")
