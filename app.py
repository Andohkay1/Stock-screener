import streamlit as st
import pandas as pd
import yfinance as yf
import io

# Optional: replace this with your own function to fetch yield
def fetch_aaa_yield():
    return 4.4  # Default AAA bond yield

# Example placeholder logic for fetching financials
def fetch_financials(ticker, yield_value):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        eps = info.get("trailingEps", None)
        bvps = info.get("bookValue", None)
        revenue = info.get("totalRevenue", 0)
        current_ratio = info.get("currentRatio", 0)
        pb_ratio = info.get("priceToBook", 0)

        if not all([eps, bvps]):
            return None

        graham_number = (15 * eps * 1.5 * bvps) ** 0.5 if eps > 0 and bvps > 0 else None
        graham_value = eps * (8.5 + 2 * 0) * (4.4 / yield_value) if eps > 0 else None

        passed_count = sum([
            revenue > 100_000_000,
            current_ratio > 2,
            pb_ratio > 1.5,
            graham_number is not None,
            graham_value is not None
        ])

        return {
            "Ticker": ticker,
            "Revenue": revenue,
            "P/B Ratio": pb_ratio,
            "EPS": eps,
            "Book Value": bvps,
            "Current Ratio": current_ratio,
            "Graham Number": graham_number,
            "Graham Value": graham_value,
            "Passed Count": passed_count
        }
    except Exception as e:
        return None

# Page config and title
st.set_page_config(page_title="Akab Stock Screener", page_icon="📉")
st.title("Akab Stock Screener")
st.markdown("A value-based stock screener using Graham's investment principles.")
st.markdown("_Find value. Avoid noise. Invest wisely._")

# === Input Section ===
st.subheader("📥 Input Tickers")

tickers = []

# Manual input first
manual_input = st.text_area("Type ticker symbols separated by commas (e.g., AAPL, MSFT, GOOG)")
if manual_input:
    typed = [t.strip().upper() for t in manual_input.split(",") if t.strip()]
    tickers.extend(typed)

# Upload option
uploaded_file = st.file_uploader("Or upload a CSV file with ticker symbols", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    uploaded_tickers = df_upload.iloc[:, 0].dropna().tolist()
    tickers.extend(uploaded_tickers)

tickers = list(set([t for t in tickers if t]))  # Deduplicate + clean

# === Run Screening ===
if st.button("🚀 Run Screening"):
    if tickers:
        with st.spinner("Running screen..."):
            results = []
            yield_value = fetch_aaa_yield()
            for t in tickers:
                data = fetch_financials(t, yield_value)
                if data:
                    results.append(data)

            if results:
                df = pd.DataFrame(results)
                df_sorted = df.sort_values("Passed Count", ascending=False)
                st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")
                st.dataframe(df_sorted)

                # Export to Excel
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
                st.warning("No valid data returned from screen.")
    else:
        st.warning("Please enter or upload at least one ticker before running the screener.")
