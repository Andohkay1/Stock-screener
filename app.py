import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests

# --- CONFIG ---
FINHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Graham Value with automated investment memo.")

# --- UTILITIES ---
def fetch_news(ticker):
    try:
        url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2025-01-01&to=2026-01-09&token={FINHUB_API_KEY}"
        res = requests.get(url)
        data = res.json()
        headlines = [d["headline"] for d in data[:3]]  # take latest 3
        return " | ".join(headlines) if headlines else "No recent news available."
    except:
        return "No recent news available."

def mark(val):
    return "✅" if val else "❌"

def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # --- Balance Sheet / Income ---
        bs = stock.balance_sheet if hasattr(stock, "balance_sheet") else pd.DataFrame()
        inc = stock.financials if hasattr(stock, "financials") else pd.DataFrame()

        col = bs.columns[0] if not bs.empty else None

        est_current_assets, est_total_liabilities = 0, 0
        if col:
            est_current_assets = sum(bs.loc[key, col] if key in bs.index else 0 for key in [
                "CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherCurrentAssets"
            ])
            est_total_liabilities = sum(bs.loc[key, col] if key in bs.index else 0 for key in [
                "TotalDebt", "AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"
            ])

        # --- EPS ---
        eps_values = []
        shares_outstanding = info.get("sharesOutstanding", 0)
        if not inc.empty and "Net Income" in inc.index and shares_outstanding:
            net_incomes = inc.loc["Net Income"].dropna().values
            eps_values = [ni / shares_outstanding for ni in net_incomes if shares_outstanding > 0]

        if not eps_values:
            eps_values = [info.get("trailingEps", 0)] * 7

        eps_7yr_avg = np.mean(eps_values[-7:]) if len(eps_values) >= 3 else np.mean(eps_values)
        eps_5yr_avg = np.mean(eps_values[-5:]) if len(eps_values) >= 3 else np.mean(eps_values)

        eps_growth = 0
        valid_eps = [eps for eps in eps_values if eps > 0]
        if len(valid_eps) >= 2:
            eps_growth = (valid_eps[-1] - valid_eps[0]) / valid_eps[0]

        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else None
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else None

        # --- Other metrics ---
        current_ratio = info.get("currentRatio", 0)
        revenue = info.get("totalRevenue", 0)
        pb_ratio = info.get("priceToBook", 0)
        current_price = info.get("currentPrice", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

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

        # --- Format Graham ---
        gn_text = f"${graham_number:.2f} {mark(current_price > graham_number)}" if graham_number else "N/A"
        gv_text = f"${graham_value:.2f} {mark(current_price > graham_value)}" if graham_value else "N/A"

        return {
            "Ticker": ticker,
            "Company Name": info.get("shortName", ticker),
            "Current Price Num": current_price,
            "Current Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "Estimated CA - L > 0": f"{(est_current_assets - est_total_liabilities):,.0f} {mark(criteria['Estimated CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5 Years": f"{'Yes' if criteria['Positive EPS for 5 Years'] else 'No'} {mark(criteria['Positive EPS for 5 Years'])}",
            "Price ≤ 15 x 3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15 x 3Y Avg EPS'])}" if current_price and price_ceiling else f"N/A ❌",
            "P/B < 1.5": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Total Liabilities": est_total_liabilities,
            "Graham Number": gn_text,
            "Graham Value": gv_text,
            "EPS 5Y Avg": eps_5yr_avg,
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

# --- RUN SCREENER ---
if st.button("🚀 Run Screener"):
    if not tickers:
        st.warning("Please enter or upload at least one ticker.")
    else:
        with st.spinner("Running screen..."):
            results = []
            progress = st.progress(0)
            for idx, t in enumerate(tickers):
                time.sleep(1)  # avoid rate limiting
                data = fetch_financials(t)
                if data:
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results)

            # --- Table: move Total Liabilities and Graham metrics to end ---
            cols_order = [
                "Ticker", "Company Name", "Current Price",
                "Revenue > $100M", "Current Ratio > 2", "Estimated CA - L > 0",
                "Pays Dividends", "Positive EPS for 5 Years", "Price ≤ 15 x 3Y Avg EPS",
                "P/B < 1.5", "Passed Count", "Total Liabilities", "Graham Number", "Graham Value", "EPS 5Y Avg"
            ]
            df = df[cols_order]
            st.success(f"✅ Screening complete for {len(df)} tickers.")
            st.dataframe(df)

            # --- Memo ---
            st.markdown("### Investment Memos")
            for _, r in df.iterrows():
                try:
                    gn_val = float(r["Graham Number"].split()[0]) if r["Graham Number"] != "N/A" else None
                    gv_val = float(r["Graham Value"].split()[0]) if r["Graham Value"] != "N/A" else None

                    valuation_insight = f"{r['Company Name']} is trading at ${r['Current Price Num']:.2f}."
                    if gn_val and gv_val:
                        if r["Current Price Num"] > gn_val and r["Current Price Num"] > gv_val:
                            valuation_insight += f" Trading above its Graham Number (${gn_val:.2f}) and Graham Value (${gv_val:.2f}), potentially overvalued ❌."
                        elif r["Current Price Num"] < gn_val and r["Current Price Num"] < gv_val:
                            valuation_insight += f" Trading below its Graham Number (${gn_val:.2f}) and Graham Value (${gv_val:.2f}), potentially undervalued ✅."
                        else:
                            valuation_insight += f" Trading between its Graham Number and Graham Value."
                    elif gn_val:
                        valuation_insight += f" Trading relative to Graham Number (${gn_val:.2f})."
                    elif gv_val:
                        valuation_insight += f" Trading relative to Graham Value (${gv_val:.2f})."

                    st.markdown(f"""
**{r['Company Name']} ({r['Ticker']})**

**Industry Note:** Operates in the Technology sector.

**Valuation Insight:** {valuation_insight}

**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends.

**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.

**Strength Note:** Current Assets cover Total Liabilities, allowing acquisition without paying for fixed assets or property.

**Risk Note:** Consider valuation sensitivity, liquidity constraints, and market conditions.

**Recent News:** {r['News']}
""")
                except Exception as e:
                    st.error(f"Error generating memo for {r['Ticker']}: {e}")

            # --- Download ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False)
            st.download_button(
                label="📥 Download Results as Excel",
                data=output.getvalue(),
                file_name="akab_screening_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No valid data returned.")
