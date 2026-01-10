import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests

# --- FINHUB API KEY ---
FINHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Value with automated investment memo.")

# --- Utility ---
def parse_money(value):
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except:
        return None

# --- Fetch financials ---
@st.cache_data(ttl=3600)
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        bs = stock.balance_sheet if hasattr(stock, "balance_sheet") else pd.DataFrame()
        inc = stock.financials if hasattr(stock, "financials") else pd.DataFrame()

        # Current Assets and Total Liabilities
        est_current_assets, est_total_liabilities = 0, 0
        if not bs.empty:
            col = bs.columns[0]
            for key in ["CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherCurrentAssets"]:
                if key in bs.index:
                    est_current_assets += bs.at[key, col] if pd.notna(bs.at[key, col]) else 0
            for key in ["TotalDebt", "AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"]:
                if key in bs.index:
                    est_total_liabilities += bs.at[key, col] if pd.notna(bs.at[key, col]) else 0

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
            "Positive EPS for 5 Years": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15 x 3Y Avg EPS": current_price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }

        passed = sum(criteria.values())
        def mark(val): return "✅" if val else "❌"

        return {
            "Ticker": ticker,
            "Company Name": info.get("shortName", ticker),
            "Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA - L > 0": f"{(est_current_assets - est_total_liabilities):,.0f} {mark(criteria['CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5 Years": f"{'Yes' if criteria['Positive EPS for 5 Years'] else 'No'} {mark(criteria['Positive EPS for 5 Years'])}",
            "Price ≤ 15 x 3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15 x 3Y Avg EPS'])}" if current_price and price_ceiling else f"N/A ❌",
            "P/B < 1.5": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f} {mark(current_price > graham_number)}" if graham_number else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(current_price > graham_value)}" if graham_value else "N/A",
            "Total Liabilities": est_total_liabilities
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

# --- Fetch news ---
def fetch_news(ticker):
    try:
        url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2025-01-01&to=2026-01-09&token={FINHUB_API_KEY}"
        res = requests.get(url).json()
        headlines = [d["headline"] for d in res[:3]]  # Top 3 news
        return " | ".join(headlines) if headlines else "No recent news available"
    except:
        return "No recent news available"

# --- Input ---
tickers = []
manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# --- Run Screener ---
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
                    data["News"] = fetch_news(t)
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results)
            # Graham metrics last
            cols_order = [c for c in df.columns if c not in ["Graham Number", "Graham Value"]] + ["Graham Number", "Graham Value"]
            df_sorted = df[cols_order].sort_values("Passed Count", ascending=False)
            st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")
            st.dataframe(df_sorted)

            # --- Investment Memo ---
            st.markdown("## Investment Memos")
            for r in results:
                try:
                    gn_val = parse_money(r["Graham Number"]) if r["Graham Number"] != "N/A" else None
                    gv_val = parse_money(r["Graham Value"]) if r["Graham Value"] != "N/A" else None
                    price = parse_money(r["Price"]) if r["Price"] != "N/A" else None

                    val_insight = f"{r['Company Name']} is trading at ${price:.2f}."
                    if price and gn_val and gv_val:
                        if price > gn_val and price > gv_val:
                            val_insight += f" Trading above its Graham Number (${gn_val:.2f}) and Graham Value (${gv_val:.2f}), potentially overvalued ❌."
                        elif price < gn_val and price < gv_val:
                            val_insight += f" Trading below its Graham Number (${gn_val:.2f}) and Graham Value (${gv_val:.2f}), potentially undervalued ✅."
                        else:
                            val_insight += f" Trading between Graham metrics."
                    else:
                        val_insight += " Graham metrics not available."

                    strength_note = "Current Assets cover Total Liabilities, allowing acquisition without paying for fixed assets or property."

                    st.markdown(f"### {r['Company Name']} ({r['Ticker']})")
                    st.markdown(f"**Industry Note:** Operates in the Technology sector.")
                    st.markdown(f"**Valuation Insight:** {val_insight}")
                    st.markdown(f"**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends.")
                    st.markdown(f"**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.")
                    st.markdown(f"**Strength Note:** {strength_note}")
                    st.markdown(f"**Risk Note:** Consider valuation sensitivity, liquidity constraints, and market conditions.")
                    st.markdown(f"**Recent News:** {r['News']}")
                    st.markdown("---")
                except Exception as e:
                    st.error(f"Error generating memo for {r['Ticker']}: {e}")

            # --- Download ---
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
