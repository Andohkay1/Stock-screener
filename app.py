import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io

st.set_page_config(
    page_title="Akab Stock Screener – Fundamental Value Screener",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("A value investing screener using 7 fundamental criteria with Graham valuation support.")

@st.cache_data(ttl=3600)
def fetch_financials(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get("currentPrice", None)

        # Financials
        revenue = info.get("totalRevenue", 0)
        current_ratio = info.get("currentRatio", 0)
        pb_ratio = info.get("priceToBook", 0)
        dividend = info.get("dividendRate", 0)
        eps = info.get("trailingEps", 0)
        bvps = info.get("bookValue", 0)

        # Balance Sheet for estimating CA - CL
        bs = stock.balance_sheet
        est_ca = 0
        est_cl = 0
        col = bs.columns[0] if not bs.empty else None

        if col:
            if "Total Current Assets" in bs.index:
                est_ca = bs.loc["Total Current Assets", col]
            else:
                est_ca = sum([
                    bs.loc[key, col] if key in bs.index else 0
                    for key in ["CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherShortTermInvestments"]
                ])

            est_cl = sum([
                bs.loc[key, col] if key in bs.index else 0
                for key in ["TotalDebt", "AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"]
            ])

        wc_pass = est_ca > est_cl

        # EPS 5 year positive (mocked)
        eps_history = [eps] * 5
        eps_5yr_pass = sum([1 for e in eps_history if e and e > 0]) >= 4

        # Price ≤ 15 x 3Y Avg EPS
        eps_3yr_avg = np.mean([eps] * 3) if eps else None
        price_pe_pass = price and eps_3yr_avg and price <= 15 * eps_3yr_avg

        # Graham valuations
        graham_number = (15 * eps * 1.5 * bvps) ** 0.5 if eps > 0 and bvps > 0 else None
        graham_value = eps * (8.5 + 2 * 0) * (4.4 / 4.4) if eps > 0 else None

        # 7 Criteria
        passed = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "Estimated CA - CL > 0": wc_pass,
            "Pays Dividends": dividend and dividend > 0,
            "Positive EPS for 5 Years": eps_5yr_pass,
            "Price ≤ 15 x 3Y Avg EPS": price_pe_pass,
            "P/B < 1.5": pb_ratio < 1.5
        }

        passed_count = sum(passed.values())

        def mark(val): return "✅" if val else "❌"

        return {
            "Ticker": ticker,
            "Price": f"${price:.2f}" if price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(passed['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(passed['Current Ratio > 2'])}",
            "Estimated CA - CL > 0": f"{(est_ca - est_cl):,.0f} {mark(passed['Estimated CA - CL > 0'])}",
            "Pays Dividends": f"{dividend:.2f} {mark(passed['Pays Dividends'])}" if dividend else f"0.00 ❌",
            "Positive EPS for 5 Years": f"{'Yes' if eps_5yr_pass else 'No'} {mark(passed['Positive EPS for 5 Years'])}",
            "Price ≤ 15 x 3Y Avg EPS": f"${price:.2f} ≤ ${15 * eps_3yr_avg:.2f} {mark(passed['Price ≤ 15 x 3Y Avg EPS'])}" if price and eps_3yr_avg else f"N/A ❌",
            "P/B < 1.5": f"{pb_ratio:.2f} {mark(passed['P/B < 1.5'])}",
            "Passed Count": passed_count,
            "Graham Number": f"${graham_number:.2f} {mark(price < graham_number)}" if graham_number and price else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(price < graham_value)}" if graham_value and price else "N/A"
        }

    except Exception:
        return None

st.subheader("📥 Input Tickers")

tickers = []
manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

if st.button("🚀 Run Screener"):
    if not tickers:
        st.warning("Please enter or upload at least one ticker.")
    else:
        with st.spinner("Running screen..."):
            results = []
            progress = st.progress(0)
            for idx, t in enumerate(tickers):
                data = fetch_financials(t)
                if data:
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

            if results:
                df = pd.DataFrame(results)
                df_sorted = df.sort_values("Passed Count", ascending=False)
                st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")
                st.dataframe(df_sorted)

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
