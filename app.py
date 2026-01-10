import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time

st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Value.")

@st.cache_data(ttl=3600)
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        inc = stock.income_stmt if not stock.income_stmt.empty else pd.DataFrame()

        col = bs.columns[0] if not bs.empty else None

        est_current_assets, est_total_liabilities = 0, 0
        if col:
            if "Total Current Assets" in bs.index:
                est_current_assets = bs.loc["Total Current Assets", col]
            else:
                est_current_assets = sum(bs.loc[key, col] if key in bs.index else 0 for key in [
                    "CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherShortTermInvestments"
                ])
            est_total_liabilities = sum(bs.loc[key, col] if key in bs.index else 0 for key in [
                "TotalDebt", "AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"
            ])

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
        def mark(val): return "✅" if val else "❌"

        # Metrics object for investment summary
        metrics = {
            "price": current_price,
            "graham_number": graham_number if not np.isnan(graham_number) else float("inf"),
            "pb_ratio": pb_ratio,
            "current_ratio": current_ratio
        }

        return {
            "Ticker": ticker,
            "Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "Estimated CA - CL > 0": f"{(est_current_assets - est_total_liabilities):,.0f} {mark(criteria['Estimated Current Assets - Liabilities > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5 Years": f"{'Yes' if criteria['Positive EPS for 5 Years'] else 'No'} {mark(criteria['Positive EPS for 5 Years'])}",
            "Price ≤ 15 x 3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15 x 3Y Avg EPS'])}" if current_price and price_ceiling else f"N/A ❌",
            "P/B < 1.5": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f} {mark(current_price < graham_number)}" if not np.isnan(graham_number) and current_price else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(current_price < graham_value)}" if not np.isnan(graham_value) and current_price else "N/A",
            "metrics": metrics,  # For investment summary
            "criteria": criteria,
            "eps_values": eps_values,
            "eps_growth": eps_growth,
            "bvps": bvps
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None


# ---- NEW FUNCTION: Generate investment notes/memo ----
def generate_stock_notes(ticker, metrics, criteria, passed):
    stock = yf.Ticker(ticker)
    info = stock.info

    business = info.get("longBusinessSummary", "Business description not available.")
    sector = info.get("sector", "Unknown sector")
    industry = info.get("industry", "Unknown industry")
    short_business = business.split(".")[0] + "." if business else f"Company in {industry} sector."

    # Valuation insight
    valuation_notes = []
    if metrics["price"] < metrics["graham_number"]:
        valuation_notes.append("The stock trades below its estimated intrinsic value (Graham Number).")
    if metrics["pb_ratio"] < 1.5:
        valuation_notes.append("Price-to-book ratio is below 1.5, indicating potential undervaluation.")
    valuation_text = " ".join(valuation_notes) if valuation_notes else "Valuation metrics are neutral."

    # Financial strength
    fs_notes = []
    if metrics["current_ratio"] > 2:
        fs_notes.append("Strong liquidity position (Current Ratio > 2).")
    if criteria.get("Positive EPS for 5 Years", False):
        fs_notes.append("Earnings consistently positive for 5 years.")
    if criteria.get("Pays Dividends", False):
        fs_notes.append("Pays regular dividends.")
    fs_text = " ".join(fs_notes) if fs_notes else "Limited balance sheet/earnings data."

    # Screening rationale
    screening_text = f"Passed {passed} of 7 Akab screening criteria."

    # Risk note
    risk_notes = []
    if metrics["pb_ratio"] > 1.2:
        risk_notes.append("valuation sensitivity")
    if metrics["current_ratio"] < 2:
        risk_notes.append("liquidity constraints")
    if sector in ["Energy", "Materials", "Industrials"]:
        risk_notes.append("cyclical sector exposure")
    risk_text = "Key considerations include " + ", ".join(risk_notes) + "." if risk_notes else ""

    # Compile
    summary = f"{short_business}\n\nValuation Insight: {valuation_text}\n\nFinancial Strength: {fs_text}\n\nScreening Rationale: {screening_text}\n\nRisk Note: {risk_text}"
    return summary


# ---------------- STREAMLIT UI ----------------
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
                time.sleep(1.5)  # Delay to avoid rate limiting
                data = fetch_financials(t)
                if data:
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results)
            df_sorted = df.sort_values("Passed Count", ascending=False)
            st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")
            st.dataframe(df_sorted)

            # ---- INVESTMENT NOTES ----
            st.markdown("### 📌 Investment Notes (Akab Model)")
            if st.checkbox("Show Investment Memos"):
                for _, row in df_sorted.iterrows():
                    summary = generate_stock_notes(row["Ticker"], row["metrics"], row["criteria"], row["Passed Count"])
                    with st.expander(f"{row['Ticker']} – Investment Summary"):
                        st.write(summary)

            st.markdown("### Understanding Your Results – Akab Model")
            st.markdown("""
The results above reflect each company’s performance against the Akab Model’s 7 screening criteria, based on principles from Benjamin Graham’s value investing framework.

✅ A green check means the company meets that criterion.  
❌ A red X means it does not.  
**Passed Count** shows how many of the 7 criteria were met.

The **Graham Number** and **Graham Value** provide benchmarks for fair valuation. If the stock price is below these, the model flags it as potentially undervalued with a ✅. These two are shown for context but are not included in the 7-pass total.

Use this as a signal to explore further. The model highlights opportunities, but investment decisions should follow deeper analysis.
""")

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
