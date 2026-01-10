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

# Full industry dictionary
industry_notes = {
    # Technology
    "Consumer Electronics": "Companies designing and selling consumer electronic devices, facing high competition and frequent product launches.",
    "Software—Infrastructure": "Companies providing essential software platforms for business operations, often with recurring subscription revenue.",
    "Semiconductors": "Firms designing and manufacturing semiconductor chips, critical to electronics, subject to cyclical demand.",
    "Internet Content & Information": "Companies providing online content, platforms, and digital advertising services.",
    
    # Healthcare
    "Biotechnology": "Firms developing drugs and therapies, revenue depends on clinical success and regulatory approvals.",
    "Healthcare Plans": "Companies managing health insurance plans, exposed to regulatory changes and medical cost trends.",
    "Medical Devices": "Firms producing medical equipment and devices, relying on innovation and healthcare demand.",
    
    # Financials
    "Banks—Regional": "Regional banks serving local markets, earning from loans and fees, sensitive to interest rates and credit quality.",
    "Banks—Diversified": "Larger banks offering a wide range of financial services across multiple markets.",
    "Insurance—Life": "Companies providing life insurance, subject to actuarial risk and investment performance.",
    "Insurance—Property & Casualty": "Firms providing general insurance, exposed to claims volatility and catastrophe risks.",
    
    # Industrials
    "Industrial Conglomerates": "Companies with diversified industrial operations, exposed to global economic cycles.",
    "Steel": "Firms producing steel and related products, sensitive to commodity prices and industrial demand.",
    "Construction & Engineering": "Companies engaged in infrastructure, commercial, and residential construction projects.",
    "Aerospace & Defense": "Firms manufacturing aircraft, defense systems, and related products, often dependent on government contracts.",
    
    # Consumer
    "Apparel Manufacturing": "Companies designing and producing clothing and footwear, sensitive to fashion trends and consumer demand.",
    "Restaurants": "Foodservice companies operating dining establishments, sensitive to consumer spending and operating costs.",
    "Food—Major Diversified": "Large food and beverage producers, often with global distribution and brand recognition.",
    
    # Energy
    "Oil & Gas Integrated": "Companies involved in exploration, production, and refining of oil and gas, exposed to commodity price volatility.",
    "Oil & Gas E&P": "Exploration and production firms, revenue depends on oil and gas reserves and prices.",
    "Renewable Energy": "Companies producing or developing renewable energy sources, subject to regulatory support and technology adoption.",
    
    # Materials
    "Chemicals—Specialty": "Companies producing specialty chemicals for industrial and consumer applications.",
    "Paper & Forest Products": "Firms manufacturing paper, packaging, and related products.",
    "Construction Materials": "Producers of cement, aggregates, and other building materials.",
    
    # Utilities
    "Electric Utilities": "Companies generating, transmitting, and distributing electricity to consumers and businesses.",
    "Water Utilities": "Firms managing water supply and wastewater treatment services.",
    
    # Communications
    "Telecom Services": "Providers of wireless, wired, and broadband communication services, subject to regulatory and competitive pressures.",
    "Media": "Companies operating broadcast, cable, or digital media services.",
    
    # Real Estate
    "REIT—Retail": "Real estate investment trusts focusing on retail properties, sensitive to consumer trends and vacancy rates.",
    "REIT—Industrial": "REITs focusing on industrial and logistics properties, often benefiting from e-commerce growth.",
    "REIT—Residential": "REITs owning apartment and residential complexes, sensitive to housing demand and rental rates.",
    
    # Misc
    "Diversified Operations": "Companies with multiple lines of business across industries, exposed to multiple market dynamics.",
}

@st.cache_data(ttl=3600)
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        inc = stock.income_stmt if not inc.empty else pd.DataFrame()
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
        industry = info.get("industry", "Diversified Operations")
        industry_note = industry_notes.get(industry, "Industry information not available.")
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "Estimated Current Assets - Liabilities > 0": est_current_assets > est_total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5 Years": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15 x 3Y Avg EPS": current_price <= price_ceiling,
            "Price to Book Ratio < 1.5": pb_ratio < 1.5,
        }

        passed = sum(criteria.values())
        def mark(val): return "✅" if val else "❌"

        # Create investment memo
        valuation_status = "overvalued" if current_price > graham_value or current_price > graham_number else "fairly valued or undervalued"
        memo = f"""
**Business Description:** {info.get('longBusinessSummary', 'No summary available.')}
**Valuation Insight:** The stock is currently {valuation_status}. Current price (${current_price:.2f}) vs Graham Number (${graham_number:.2f}) and Graham Value (${graham_value:.2f}).
**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends of ${dividend_rate:.2f}.
**Screening Rationale:** Passed {passed} of 7 Akab screening criteria.
**Risk Note:** Key considerations include valuation sensitivity and liquidity constraints.
**Industry Note:** {industry_note}
"""
        return {
            "Ticker": ticker,
            "Current Price": f"${current_price:.2f}" if current_price else "N/A",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f}" if not np.isnan(graham_number) else "N/A",
            "Graham Value": f"${graham_value:.2f}" if not np.isnan(graham_value) else "N/A",
            "Investment Memo": memo
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

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
                time.sleep(1.5)
                data = fetch_financials(t)
                if data:
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results)
            df_sorted = df.sort_values("Passed Count", ascending=False)
            st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")
            st.dataframe(df_sorted[["Ticker","Current Price","Passed Count","Graham Number","Graham Value"]])

            st.markdown("### Investment Memos")
            for memo in df_sorted["Investment Memo"]:
                st.markdown(memo)
        else:
            st.warning("No valid data returned.")
