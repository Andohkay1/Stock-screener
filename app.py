import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# Set Streamlit page config (🟢 Add this at the very top)
st.set_page_config(
    page_title="Akab Stock Screener",
    page_icon="📉",
    layout="centered"
)

# Title and description
st.title("Akab Stock Screener")
st.markdown("A value-based screener inspired by Graham’s investing principles.")
st.markdown("_Find value. Avoid noise. Invest wisely._")

st.subheader("📥 Input Tickers")

tickers = []

# 🔹 Manual Input First
manual_input = st.text_area("Type ticker symbols separated by commas (e.g., AAPL, MSFT, GOOG)")
if manual_input:
    typed_tickers = [t.strip().upper() for t in manual_input.split(",") if t.strip()]
    tickers.extend(typed_tickers)

# 🔹 Upload Option Second
uploaded_file = st.file_uploader("Or upload a CSV file with ticker symbols", type="csv")
if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    uploaded_tickers = df.iloc[:, 0].dropna().tolist()
    tickers.extend(uploaded_tickers)

# 🔄 Remove duplicates and empty
tickers = list(set([t for t in tickers if t]))

# 🔘 Button to trigger screening
if st.button("Run Screener"):
    if tickers:
        st.success(f"{len(tickers)} tickers received. Running screen...")
        # 🔁 Your screening logic goes here
    else:
        st.warning("Please enter or upload at least one ticker.")
import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io

st.set_page_config(page_title="Graham Screener", layout="wide")

st.title("📈 Graham Value Stock Screener")

# === Utility Functions ===
def fetch_aaa_yield():
    try:
        bond = yf.Ticker("^DAAA")
        history = bond.history(period="1mo")
        latest_yield = history["Close"].dropna().iloc[-1]
        return latest_yield
    except Exception:
        return 4.4

def fetch_financials(ticker, current_bond_yield):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        bs = stock.get_balance_sheet(freq="yearly")
        inc = stock.income_stmt
        col = bs.columns[0] if len(bs.columns) > 0 else None
        if not col:
            return None

        if "Total Current Assets" in bs.index:
            est_current_assets = bs.loc["Total Current Assets", col]
        else:
            est_current_assets = sum([
                bs.loc[key, col] if key in bs.index else 0
                for key in ["CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherShortTermInvestments"]
            ])

        est_total_liabilities = sum([
            bs.loc[key, col] if key in bs.index else 0
            for key in ["TotalDebt", "AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"]
        ])

        eps_values = []
        shares_outstanding = info.get("sharesOutstanding", 0)
        if "Net Income" in inc.index and shares_outstanding:
            net_incomes = inc.loc["Net Income"].dropna().values
            eps_values = [ni / shares_outstanding for ni in net_incomes if shares_outstanding > 0]
        eps_values = [eps for eps in eps_values if isinstance(eps, (int, float))]

        eps_7yr_avg = np.mean(eps_values[-7:]) if len(eps_values) >= 3 else np.mean(eps_values)
        eps_5yr_avg = np.mean(eps_values[-5:]) if len(eps_values) >= 3 else np.mean(eps_values)

        eps_growth = 0
        if len(eps_values) >= 2:
            valid_eps = [eps for eps in eps_values if eps > 0]
            if len(valid_eps) >= 2:
                oldest = valid_eps[0]
                latest = valid_eps[-1]
                if oldest > 0:
                    eps_growth = (latest - oldest) / oldest

        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else np.nan
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else np.nan

        current_ratio = info.get("currentRatio", 0)
        revenue = info.get("totalRevenue", 0)
        pb_ratio = info.get("priceToBook", 0)
        current_price = info.get("currentPrice", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "Estimated Current Assets - Liabilities > 0": est_current_assets > est_total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5 Years": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15 x 3Y Avg EPS": current_price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }

        passed = sum(criteria.values())

        return {
            "Ticker": ticker,
            "Passed Count": passed,
            "EPS Growth": eps_growth,
            "BVPS": bvps,
            "Current Price": current_price,
            "Graham Number": graham_number,
            "Graham Value": graham_value,
            **criteria
        }

    except Exception as e:
        return None

# === Input Section ===
st.subheader("Enter tickers manually or upload CSV")

manual_input = st.text_area("🔤 Enter tickers (comma or space separated)", height=100)
uploaded_file = st.file_uploader("📤 Or upload a CSV with a 'Ticker' column", type=["csv"])

tickers = []

if uploaded_file:
    df_upload = pd.read_csv(uploaded_file)
    if "Ticker" in df_upload.columns:
        tickers = df_upload["Ticker"].dropna().astype(str).tolist()
    else:
        st.error("CSV must contain a 'Ticker' column.")
elif manual_input:
    tickers = [t.strip().upper() for t in manual_input.replace(",", " ").split() if t.strip()]

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

                # Export
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df_sorted.to_excel(writer, index=False)
                st.download_button(
                    label="📥 Download Results as Excel",
                    data=output.getvalue(),
                    file_name="graham_screening_results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("No valid data returned from screen.")
    else:
        st.warning("Please enter or upload at least one ticker before running the screener.")
