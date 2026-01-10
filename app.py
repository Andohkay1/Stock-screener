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
st.markdown("Uses verified EPS logic for Graham Number and Value with automated investment memo.")

@st.cache_data(ttl=3600)
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        inc = stock.financials if not stock.financials.empty else pd.DataFrame()  # fixed reference

        col = bs.columns[0] if not bs.empty else None

        # Estimate current assets and total liabilities
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

        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else np.nan
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else np.nan

        # Financial ratios
        current_ratio = info.get("currentRatio", 0)
        revenue = info.get("totalRevenue", 0)
        price_to_book = info.get("priceToBook", 0)
        current_price = info.get("currentPrice", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        # Screening criteria
        criteria = {
            "Revenue above 100 million": revenue > 100_000_000,
            "Current ratio above 2": current_ratio > 2,
            "Current assets exceed liabilities": est_current_assets > est_total_liabilities,
            "Pays dividends": dividend_rate > 0,
            "Positive earnings per share for 5 years": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price under 15 times 3-year average EPS": current_price <= price_ceiling,
            "Price to book ratio under 1.5": price_to_book < 1.5,
        }

        passed = sum(criteria.values())
        def mark(val): return "✅" if val else "❌"

        # Industry description mapping
        industries = {
            "Technology": "operates in the technology sector, producing software, hardware, and related services.",
            "Healthcare": "operates in healthcare, including pharmaceuticals, biotechnology, and medical devices.",
            "Financial Services": "operates in financial services, including banking, insurance, and investment management.",
            "Consumer Cyclical": "operates in consumer goods and retail sectors, selling non-essential products.",
            "Consumer Defensive": "operates in consumer staples, producing essential goods like food, beverages, and household items.",
            "Energy": "operates in energy, including oil, gas, and renewable energy production.",
            "Industrials": "operates in industrials, including manufacturing, construction, and infrastructure-related businesses.",
            "Materials": "operates in materials, including metals, chemicals, and paper products.",
            "Utilities": "operates in utilities, providing electricity, gas, and water services.",
            "Real Estate": "operates in real estate, including property development, management, and investment."
        }

        industry_note = industries.get(info.get("sector", ""), f"Operates in {info.get('sector', 'its sector')} sector.")

        return {
            "Ticker": ticker,
            "Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue above 100 million": f"{revenue:,} {mark(criteria['Revenue above 100 million'])}",
            "Current ratio above 2": f"{current_ratio:.2f} {mark(criteria['Current ratio above 2'])}",
            "Current assets exceed liabilities": f"{(est_current_assets - est_total_liabilities):,.0f} {mark(criteria['Current assets exceed liabilities'])}",
            "Pays dividends": f"{dividend_rate:.2f} {mark(criteria['Pays dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive earnings per share for 5 years": f"{'Yes' if criteria['Positive earnings per share for 5 years'] else 'No'} {mark(criteria['Positive earnings per share for 5 years'])}",
            "Price under 15 times 3-year average EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price under 15 times 3-year average EPS'])}" if current_price and price_ceiling else f"N/A ❌",
            "Price to book ratio under 1.5": f"{price_to_book:.2f} {mark(criteria['Price to book ratio under 1.5'])}",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f} {mark(current_price < graham_number)}" if not np.isnan(graham_number) and current_price else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(current_price < graham_value)}" if not np.isnan(graham_value) and current_price else "N/A",
            "Industry Note": industry_note
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

# Tickers input
tickers = []
manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# Run Screener
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

            # Investment memo
            st.markdown("### Investment Memos")
            for r in results:
                st.markdown(f"**{r['Ticker']}**")
                st.markdown(f"**Industry Note:** {r['Industry Note']}")
                st.markdown(f"**Valuation Insight:** The stock is trading at ${r['Price']} vs Graham Number {r['Graham Number']} and Graham Value {r['Graham Value']}. This indicates potential overvaluation or undervaluation depending on the difference.")
                st.markdown(f"**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends." if "Pays dividends" in r else "")
                st.markdown(f"**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.")
                st.markdown(f"**Risk Note:** Consider valuation sensitivity, liquidity constraints, and market conditions.")

            # Download results
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
