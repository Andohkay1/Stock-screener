import streamlit as st
import pandas as pd
import yfinance as yf
import io

# Page configuration with improved visibility
st.set_page_config(
    page_title="Akab Stock Screener – Fundamental Value Screener",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("A fundamental screener that applies 7 rigorous value criteria to identify strong candidates.")

@st.cache_data(ttl=3600)
def fetch_financials(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="3y")

        price = info.get("currentPrice", None)
        revenue = info.get("totalRevenue", 0)
        current_ratio = info.get("currentRatio", 0)
        current_assets = info.get("totalCurrentAssets", 0)
        current_liabilities = info.get("totalCurrentLiabilities", 0)
        dividend = info.get("dividendRate", 0)
        pb_ratio = info.get("priceToBook", 0)

        # EPS history check (mocked by checking if trailing EPS exists and is > 0)
        eps_history = []
        for i in range(5):
            eps_history.append(info.get("trailingEps", 0))

        eps_5yr_pass = sum([1 for e in eps_history if e and e > 0]) >= 4

        # 3-year average EPS estimation
        eps_values = []
        for i in range(3):
            eps_values.append(info.get("trailingEps", 0))
        eps_3yr_avg = sum(eps_values) / len(eps_values) if eps_values else None

        pe_cutoff = 15 * eps_3yr_avg if eps_3yr_avg else None

        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "Estimated Current Assets - Liabilities > 0": (current_assets - current_liabilities) > 0,
            "Pays Dividends": dividend is not None and dividend > 0,
            "Positive EPS for 5 Years": eps_5yr_pass,
            "Price ≤ 15 x 3Y Avg EPS": price is not None and pe_cutoff is not None and price <= pe_cutoff,
            "P/B < 1.5": pb_ratio < 1.5
        }

        passed_count = sum(criteria.values())

        return {
            "Ticker": ticker,
            "Price": price,
            "Revenue": revenue,
            "Current Ratio": current_ratio,
            "Working Capital": current_assets - current_liabilities,
            "Dividend": dividend,
            "P/B Ratio": pb_ratio,
            "3Y Avg EPS": eps_3yr_avg,
            "PE Cutoff": pe_cutoff,
            "Passed Count": passed_count,
            **criteria
        }
    except Exception as e:
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
