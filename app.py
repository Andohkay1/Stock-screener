import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io

st.set_page_config(
    page_title="Akab Stock Screener – Graham-Enhanced",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Includes 7 value criteria and Graham Value logic using estimated EPS growth.")

@st.cache_data(ttl=3600)
def fetch_financials(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get("currentPrice", None)
        bvps = info.get("bookValue", 0)
        pb_ratio = info.get("priceToBook", 0)
        dividend = info.get("dividendRate", 0)
        revenue = info.get("totalRevenue", 0)
        current_ratio = info.get("currentRatio", 0)
        eps_ttm = info.get("trailingEps", 0)

        # EPS history
        hist = stock.earnings
        eps_growth = 0
        eps_5yr = []
        eps_7yr = []

        if not hist.empty and len(hist) >= 7:
            eps_series = hist["Earnings"].values[-7:]
            oldest = eps_series[0]
            latest = eps_series[-1]
            eps_growth = (latest - oldest) / oldest if oldest else 0
            eps_5yr = eps_series[-5:]
            eps_7yr = eps_series
        else:
            eps_5yr = [eps_ttm] * 5
            eps_7yr = [eps_ttm] * 7

        eps_5yr_avg = np.mean(eps_5yr)
        eps_7yr_avg = np.mean(eps_7yr)
        eps_3yr_avg = np.mean([eps_ttm] * 3) if eps_ttm else 0
        price_pe_pass = price is not None and eps_3yr_avg and price <= 15 * eps_3yr_avg

        # Working capital from balance sheet
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
        eps_5yr_pass = sum([1 for e in eps_5yr if e > 0]) >= 4

        # Graham formulas
        bond_yield = 4.4
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else np.nan
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / bond_yield) if eps_5yr_avg > 0 else np.nan

        passed = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "Estimated CA - CL > 0": wc_pass,
            "Pays Dividends": dividend and dividend > 0,
            "Positive EPS for 5 Years": eps_5yr_pass,
            "Price ≤ 15 x 3Y Avg EPS": price_pe_pass,
            "P/B < 1.5": pb_ratio < 1.5
        }

        def mark(val): return "✅" if val else "❌"
        passed_count = sum(passed.values())

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
            "Graham Number": f"${graham_number:.2f} {mark(price < graham_number)}" if not np.isnan(graham_number) and price else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(price < graham_value)}" if not np.isnan(graham_value) and price else "N/A"
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
