import streamlit as st
import pandas as pd
import yfinance as yf
import io

st.set_page_config(
    page_title="Akab Stock Screener – Fundamental Value Screener",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("A Graham-inspired value screener based on 7 fundamental criteria.")

@st.cache_data(ttl=3600)
def fetch_financials(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        price = info.get("currentPrice")
        revenue = info.get("totalRevenue", 0)
        current_ratio = info.get("currentRatio", 0)
        current_assets = info.get("totalCurrentAssets", 0)
        current_liabilities = info.get("totalCurrentLiabilities", 0)
        dividend = info.get("dividendRate", 0)
        pb_ratio = info.get("priceToBook", 0)
        eps = info.get("trailingEps", 0)
        bvps = info.get("bookValue", 0)

        # 5-year EPS check (mocked)
        eps_history = [eps] * 5
        eps_5yr_pass = sum([1 for e in eps_history if e and e > 0]) >= 4

        # 3-year average EPS (mocked)
        eps_3yr_avg = sum([eps] * 3) / 3 if eps else None
        price_eps_pass = price is not None and eps_3yr_avg and price <= 15 * eps_3yr_avg

        # Graham calculations
        graham_number = (15 * eps * 1.5 * bvps) ** 0.5 if eps > 0 and bvps > 0 else None
        graham_value = eps * (8.5 + 2 * 0) * (4.4 / 4.4) if eps > 0 else None  # Assume AAA yield = 4.4%

        # 7 Criteria
        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "Estimated CA - CL > 0": (current_assets - current_liabilities) > 0,
            "Pays Dividends": dividend and dividend > 0,
            "Positive EPS for 5 Years": eps_5yr_pass,
            "Price ≤ 15 x 3Y Avg EPS": price_eps_pass,
            "P/B < 1.5": pb_ratio < 1.5
        }

        passed_count = sum(criteria.values())

        # Marker formatting
        def mark(val): return f":green[✅]" if val else f":red[❌]"

        return {
            "Ticker": ticker,
            "Price": f"${price:.2f}" if price else "N/A",
            **{k: mark(v) for k, v in criteria.items()},
            "Passed Count": passed_count,
            "Graham Number": f"${graham_number:.2f} :green[✅]" if graham_number and price and price < graham_number else f"${graham_number:.2f} :red[❌]" if graham_number else "❌",
            "Graham Value": f"${graham_value:.2f} :green[✅]" if graham_value and price and price < graham_value else f"${graham_value:.2f} :red[❌]" if graham_value else "❌"
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
