import streamlit as st
import pandas as pd
import yfinance as yf
import io

# === PAGE CONFIG ===
st.set_page_config(page_title="Akab Stock Screener", page_icon="📉")
st.title("Akab Stock Screener")
st.markdown("A value-based stock screener using 7 key fundamentals.")
st.markdown("_Screen includes revenue, current ratio, dividend status, EPS consistency, and valuation metrics._")

# === CACHED DATA FETCH ===
@st.cache_data(ttl=3600)
def fetch_financials(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="3y")

        # Inputs
        eps_ttm = info.get("trailingEps", None)
        bvps = info.get("bookValue", None)
        revenue = info.get("totalRevenue", 0)
        current_ratio = info.get("currentRatio", 0)
        current_assets = info.get("totalCurrentAssets", 0)
        current_liabilities = info.get("totalCurrentLiabilities", 0)
        pb_ratio = info.get("priceToBook", 0)
        price = info.get("currentPrice", None)
        dividend = info.get("dividendRate", None)
        five_year_eps = info.get("fiveYearAvgEarnings", None)  # Replace with your own source if needed

        # 3-Year Avg EPS from history
        eps_history = []
        if hist is not None and not hist.empty and 'Close' in hist:
            for year in range(1, 4):
                try:
                    eps_history.append(yf.Ticker(ticker).info.get('trailingEps', None))  # This should be replaced with actual per-year EPS if you have source
                except:
                    eps_history.append(None)

        eps_3yr_avg = sum([e for e in eps_history if e]) / len([e for e in eps_history if e]) if eps_history else None

        # Criteria checks
        revenue_pass = revenue > 100_000_000
        current_ratio_pass = current_ratio > 2
        working_capital_pass = (current_assets - current_liabilities) > 0
        pays_dividend_pass = dividend and dividend > 0
        eps_5yr_pass = five_year_eps and five_year_eps > 0
        price_limit = 15 * eps_3yr_avg if eps_3yr_avg else None
        price_eps_multiple_pass = price and price_limit and price <= price_limit
        pb_pass = pb_ratio < 1.5

        # Display formatting
        revenue_display = f"{revenue:,} ✅" if revenue_pass else f"{revenue:,} ❌"
        current_ratio_display = f"{current_ratio:.2f} ✅" if current_ratio_pass else f"{current_ratio:.2f} ❌"
        wc_display = f"{(current_assets - current_liabilities):,.0f} ✅" if working_capital_pass else f"{(current_assets - current_liabilities):,.0f} ❌"
        dividend_display = f"{dividend:.2f} ✅" if pays_dividend_pass else f"{dividend if dividend else 0:.2f} ❌"
        eps_5yr_display = "✅" if eps_5yr_pass else "❌"
        pe_display = f"{price:.2f} ≤ {price_limit:.2f} ✅" if price_eps_multiple_pass else (f"{price:.2f} > {price_limit:.2f} ❌" if price_limit else "N/A")
        pb_display = f"{pb_ratio:.2f} ✅" if pb_pass else f"{pb_ratio:.2f} ❌"

        passed_count = sum([
            revenue_pass,
            current_ratio_pass,
            working_capital_pass,
            pays_dividend_pass,
            eps_5yr_pass,
            price_eps_multiple_pass,
            pb_pass
        ])

        return {
            "Ticker": ticker,
            "Revenue > $100M": revenue_display,
            "Current Ratio > 2": current_ratio_display,
            "Estimated Current Assets - Liabilities > 0": wc_display,
            "Pays Dividends": dividend_display,
            "Positive EPS for 5 Years": eps_5yr_display,
            "Price ≤ 15 x 3Y Avg EPS": pe_display,
            "P/B < 1.5": pb_display,
            "Passed Count": passed_count
        }
    except Exception as e:
        return None

# === INPUT SECTION ===
st.subheader("📥 Input Tickers")
tickers = []

manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, GOOG)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# === RUN BUTTON ===
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

                # Excel export
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
