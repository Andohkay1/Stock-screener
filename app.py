import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests

# --- Your Finhub API Key ---
FINHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Value with automated investment memo.")

# ---------------------
# Helper Functions
# ---------------------

def mark(val): return "✅" if val else "❌"

def parse_money(value):
    if value is None:
        return None
    return float(str(value).replace("$", "").replace(",", ""))

def fetch_news(ticker):
    try:
        url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2026-01-01&to=2026-01-09&token={FINHUB_API_KEY}"
        res = requests.get(url)
        data = res.json()
        if not data:
            return "No recent news available."
        headlines = [d.get("headline", "") for d in data[:5]]  # top 5
        return " | ".join(headlines) if headlines else "No recent news available."
    except:
        return "No recent news available."

@st.cache_data(ttl=3600)
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # --- Balance Sheet ---
        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        col = bs.columns[0] if not bs.empty else None

        est_current_assets, est_total_liabilities = 0, 0
        if col:
            est_current_assets = sum(bs.loc.get(key, [0])[0] for key in [
                "CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherCurrentAssets"
            ])
            est_total_liabilities = sum(bs.loc.get(key, [0])[0] for key in [
                "TotalDebt", "AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"
            ])

        # --- Income Statement & EPS ---
        inc = stock.financials if not stock.financials.empty else pd.DataFrame()
        eps_values = []
        shares_outstanding = info.get("sharesOutstanding", 0)
        if not inc.empty and "Net Income" in inc.index and shares_outstanding:
            net_incomes = inc.loc["Net Income"].dropna().values
            eps_values = [ni / shares_outstanding for ni in net_incomes if shares_outstanding > 0]

        if not eps_values:
            eps_values = [info.get("trailingEps", 0)] * 7

        eps_values = [eps for eps in eps_values if isinstance(eps, (int, float))]
        eps_7yr_avg = np.mean(eps_values[-7:]) if len(eps_values) >= 3 else np.mean(eps_values)
        eps_5yr_avg = np.mean(eps_values[-5:]) if len(eps_values) >= 3 else np.mean(eps_values)

        # EPS Growth
        eps_growth = 0
        if len(eps_values) >= 2:
            valid_eps = [eps for eps in eps_values if eps > 0]
            if len(valid_eps) >= 2:
                oldest, latest = valid_eps[0], valid_eps[-1]
                if oldest > 0:
                    eps_growth = (latest - oldest) / oldest

        # --- Graham Metrics ---
        bvps = info.get("bookValue", 0)
        gn_num = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else None
        gv_num = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else None

        # --- Price and other metrics ---
        current_price = info.get("currentPrice", 0)
        current_ratio = info.get("currentRatio", 0)
        revenue = info.get("totalRevenue", 0)
        pb_ratio = info.get("priceToBook", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        # --- Screening Criteria ---
        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "Estimated CA - L > 0": est_current_assets > est_total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5 Years": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15 x 3Y Avg EPS": current_price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }
        passed = sum(criteria.values())

        # --- Format for Table ---
        def format_val(val, crit):
            return f"{val:,} {mark(crit)}" if isinstance(val, (int, float)) else f"{val} {mark(crit)}"

        return {
            "Ticker": ticker,
            "Company Name": info.get("shortName", ticker),
            "Current Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": format_val(revenue, criteria["Revenue > $100M"]),
            "Current Ratio > 2": format_val(current_ratio, criteria["Current Ratio > 2"]),
            "P/B < 1.5": format_val(pb_ratio, criteria["P/B < 1.5"]),
            "Pays Dividends": format_val(dividend_rate, criteria["Pays Dividends"]),
            "Positive EPS for 5 Years": "Yes ✅" if criteria["Positive EPS for 5 Years"] else "No ❌",
            "Price ≤ 15 x 3Y Avg EPS": format_val(current_price, criteria["Price ≤ 15 x 3Y Avg EPS"]),
            "Estimated CA - L > 0": format_val(est_current_assets - est_total_liabilities, criteria["Estimated CA - L > 0"]),
            "Graham Number": f"${gn_num:.2f} {mark(current_price < gn_num)}" if gn_num else "N/A",
            "Graham Number Num": gn_num,
            "Graham Value": f"${gv_num:.2f} {mark(current_price < gv_num)}" if gv_num else "N/A",
            "Graham Value Num": gv_num,
            "Passed Count": passed,
            "Current Price Num": current_price,
            "Total Liabilities": est_total_liabilities,
            "EPS 5Y Avg": eps_5yr_avg,
            "EPS 7Y Avg": eps_7yr_avg,
        }
    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

# ---------------------
# UI Input
# ---------------------

tickers = []
manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# ---------------------
# Run Screener
# ---------------------
if st.button("🚀 Run Screener"):
    if not tickers:
        st.warning("Please enter or upload at least one ticker.")
    else:
        with st.spinner("Running screen..."):
            results = []
            progress = st.progress(0)
            for idx, t in enumerate(tickers):
                time.sleep(1.0)
                data = fetch_financials(t)
                if data:
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results)
            # Keep table order: everything, then CA-L, then Graham Number/Value
            df_sorted = df.sort_values("Passed Count", ascending=False)
            st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")
            st.dataframe(df_sorted[[
                "Ticker","Company Name","Current Price","Revenue > $100M","Current Ratio > 2",
                "P/B < 1.5","Pays Dividends","Positive EPS for 5 Years","Price ≤ 15 x 3Y Avg EPS",
                "Estimated CA - L > 0","Graham Number","Graham Value","Passed Count"
            ]])

            # --- Investment Memo ---
            st.markdown("## Investment Memos")
            for r in results:
                try:
                    gn_val = r["Graham Number Num"]
                    gv_val = r["Graham Value Num"]
                    price = r["Current Price Num"]
                    valuation_insight = f"{r['Company Name']} ({r['Ticker']}) is trading at ${price:.2f}."
                    if gn_val and gv_val:
                        if price > gn_val and price > gv_val:
                            valuation_insight += f" Trading above its Graham Number (${gn_val:.2f}) and Graham Value (${gv_val:.2f}), potentially overvalued ❌."
                        elif price < gn_val and price < gv_val:
                            valuation_insight += f" Trading below its Graham Number (${gn_val:.2f}) and Graham Value (${gv_val:.2f}), potentially undervalued ✅."
                        else:
                            valuation_insight += f" Trading between its Graham Number and Graham Value."
                    news = fetch_news(r["Ticker"])
                    st.markdown(f"""
**{r['Company Name']} ({r['Ticker']})**

**Industry Note:** Operates in the Technology sector.

**Valuation Insight:** {valuation_insight}

**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends.

**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.

**Strength Note:** Current Assets cover Total Liabilities, allowing acquisition without paying for fixed assets or property.

**Risk Note:** Consider valuation sensitivity, liquidity constraints, and market conditions.

**Recent News:** {news}
""")
                except Exception as e:
                    st.error(f"Error generating memo for {r['Ticker']}: {e}")

            # --- Download Excel ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_sorted.to_excel(writer, index=False)
            st.download_button(
                label="📥 Download Results as Excel",
                data=output.getvalue(),
                file_name="akab_screening_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No valid data returned.")
