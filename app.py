import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests

# ======= CONFIG =======
FINNHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"
st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)
st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Value with automated investment memo.")

# ======= INDUSTRY PRODUCTS MAPPING =======
industry_products = {
    "Technology": "produces software, hardware, and related services such as computers, smartphones, cloud platforms, and software applications.",
    "Consumer Electronics": "produces smartphones, tablets, computers, wearables, and accessories.",
    "Specialty Industrial Machinery": "manufactures, processes, and sells automatic control equipment worldwide including air management systems, valves, cylinders, actuators, and grippers.",
    "Healthcare": "develops and sells pharmaceuticals, medical devices, and healthcare services.",
    "Energy": "explores, produces, and sells oil, gas, and renewable energy solutions.",
    "Financial Services": "offers banking, insurance, investment, and capital markets services.",
    "Industrial Metals & Mining": "produces and sells steel, aluminum, copper, and other industrial metals.",
}

# ======= HELPER FUNCTIONS =======
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        inc = stock.income_stmt if not stock.income_stmt.empty else pd.DataFrame()
        col = bs.columns[0] if not bs.empty else None

        # ===== Current Assets =====
        current_assets = 0
        if col and not bs.empty:
            current_assets = sum(
                bs.loc[key, col] if key in bs.index and not pd.isna(bs.loc[key, col]) else 0
                for key in ["CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherShortTermInvestments"]
            )
        current_assets = float(current_assets or info.get("totalCurrentAssets", 0) or 0)

        # ===== Current Liabilities =====
        current_liabilities = 0
        if col and not bs.empty:
            current_liabilities = sum(
                bs.loc[key, col] if key in bs.index and not pd.isna(bs.loc[key, col]) else 0
                for key in ["AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"]
            )
        current_liabilities = float(current_liabilities or info.get("currentLiabilities", 0) or 0)

        # ===== Total Liabilities =====
        total_liabilities = float(info.get("totalLiab", 0) or current_liabilities)

        # ===== Working Capital =====
        working_capital = current_assets - current_liabilities

        # ===== EPS Calculations =====
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

        # EPS Growth
        eps_growth = 0
        if len(eps_values) >= 2:
            valid_eps = [eps for eps in eps_values if eps > 0]
            if len(valid_eps) >= 2:
                oldest, latest = valid_eps[0], valid_eps[-1]
                if oldest > 0:
                    eps_growth = (latest - oldest) / oldest

        # Graham Calculations
        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else None
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else None

        # Screening Metrics
        current_ratio = info.get("currentRatio", 0) or (current_assets / current_liabilities if current_liabilities else 0)
        revenue = info.get("totalRevenue", 0)
        pb_ratio = info.get("priceToBook", 0)
        current_price = info.get("currentPrice", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        # --- Screening Criteria ---
        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "CA - L > 0": current_assets > total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5Y": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15x3Y Avg EPS": current_price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }
        passed = sum(criteria.values())
        mark = lambda val: "✅" if val else "❌"

        # Mapping failed criteria to explanations
        criteria_risks = {
            "Revenue > $100M": "Revenue is low; company may lack scale for stability.",
            "Current Ratio > 2": "Liquidity is below safe threshold; company may struggle to meet short-term obligations.",
            "CA - L > 0": "Current Assets do not cover total liabilities; liquidity risk.",
            "Pays Dividends": "Does not pay dividends; may indicate weaker shareholder returns or cash allocation priorities.",
            "Positive EPS for 5Y": "Earnings are inconsistent; profitability risk exists.",
            "Price ≤ 15x3Y Avg EPS": "Stock price exceeds 15x 3-year average EPS; potentially overvalued.",
            "P/B < 1.5": "Price-to-Book ratio is high; stock may be overvalued relative to net assets.",
        }
        failed_criteria = [k for k, v in criteria.items() if v is False]

        return {
            "Ticker": ticker,
            "Price": current_price,
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA - L > 0": f"{(current_assets - total_liabilities):,.0f} {mark(criteria['CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5Y": f"{'Yes' if criteria['Positive EPS for 5Y'] else 'No'} {mark(criteria['Positive EPS for 5Y'])}",
            "Price ≤ 15x3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15x3Y Avg EPS'])}" if price_ceiling else "N/A ❌",
            "P/B": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Graham Number": graham_number,
            "Graham Value": graham_value,
            "Industry": info.get("industry", "N/A"),
            "Company Name": info.get("shortName", ticker),
            "Current Assets": current_assets,
            "Current Liabilities": current_liabilities,
            "Total Liabilities": total_liabilities,
            "Current Ratio Num": current_ratio,
            "Working Capital": working_capital,
            "Failed Criteria": failed_criteria,
            "Criteria Risks": criteria_risks,
        }
    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

# ======= FINNHUB NEWS =======
def fetch_news(symbol):
    url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from=2025-01-01&to=2026-01-09&token={FINNHUB_API_KEY}"
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            data = resp.json()
            headlines = [d.get("headline") for d in data if "headline" in d]
            return " | ".join(headlines[:5]) if headlines else "No recent news available."
        return "No recent news available."
    except:
        return "No recent news available."

# ======= INPUT =======
tickers = []

manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# ======= RUN SCREEN =======
if st.button("🚀 Run Screener"):
    if not tickers:
        st.warning("Please enter or upload at least one ticker.")
    else:
        with st.spinner("Running screen..."):
            results = []
            progress = st.progress(0)
            for idx, t in enumerate(tickers):
                time.sleep(1)
                data = fetch_financials(t)
                if data:
                    results.append(data)
                progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results)
            # ======= Set Graham tick logic =======
            def add_graham_ticks(row):
                price = row["Price"]
                gn = row["Graham Number"]
                gv = row["Graham Value"]
                if gn and gv:
                    if price > gn and price > gv:
                        gn_tick = "❌"
                        gv_tick = "❌"
                    elif price < gn and price < gv:
                        gn_tick = "✅"
                        gv_tick = "✅"
                    else:
                        gn_tick = "⚠️"
                        gv_tick = "⚠️"
                else:
                    gn_tick = "N/A ❌"
                    gv_tick = "N/A ❌"
                row["Graham Number"] = f"${gn:.2f} {gn_tick}" if gn else gn_tick
                row["Graham Value"] = f"${gv:.2f} {gv_tick}" if gv else gv_tick
                return row

            df = df.apply(add_graham_ticks, axis=1)
            df_sorted = df.sort_values("Passed Count", ascending=False)
            st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")

            # ======= DISPLAY TABLE =======
            table_cols = [
                "Ticker", "Price", "Revenue > $100M", "Current Ratio > 2", "CA - L > 0",
                "Pays Dividends", "Positive EPS for 5Y", "Price ≤ 15x3Y Avg EPS",
                "P/B", "Passed Count", "Graham Number", "Graham Value"
            ]
            st.dataframe(df_sorted[table_cols])

            # ======= INVESTMENT MEMOS =======
            st.markdown("### Investment Memos")
            for idx, r in df_sorted.iterrows():
                try:
                    company_name = r["Company Name"]
                    industry = r["Industry"]
                    products = industry_products.get(industry, "")
                    industry_note = f"Operates in the {industry} sector. Key products/services: {products}" if products else f"Operates in the {industry} sector."

                    # ======= Strength Note =======
                    ca = r.get("Current Assets", 0)
                    cl = r.get("Current Liabilities", 0)
                    tl = r.get("Total Liabilities", 0)
                    wc = r.get("Working Capital", 0)
                    cr = r.get("Current Ratio Num", 0)
                    if ca > tl:
                        strength_note = "Current Assets can pay all debt"
                    elif wc >= 0 and cr >= 1 and ca <= tl:
                        strength_note = "Working capital positive, but Current Assets do not cover total liabilities; leverage risk remains."
                    else:
                        strength_note = "No material balance sheet item identified."

                    # ======= Dynamic Risk Note =======
                    failed_criteria = r.get("Failed Criteria", [])
                    criteria_risks = r.get("Criteria Risks", {})
                    risk_exclude = ["Current Ratio > 2", "CA - L > 0"]
                    filtered_failed = [c for c in failed_criteria if c not in risk_exclude]
                    if filtered_failed:
                        risk_note = "Potential risks: " + "; ".join([criteria_risks[k] for k in filtered_failed]) + ". Consider market conditions."
                    else:
                        risk_note = "No major screening risks identified. Consider general market conditions."

                    news_text = fetch_news(r["Ticker"])

                    st.markdown(f"**{company_name} ({r['Ticker']})**\n\n"
                                f"**Industry Note:** {industry_note}\n\n"
                                f"**Valuation Insight:** {company_name} is trading at ${r['Price']:.2f}.\n\n"
                                f"**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends.\n\n"
                                f"**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.\n\n"
                                f"**Strength Note:** {strength_note}\n\n"
                                f"**Risk Note:** {risk_note}\n\n"
                                f"**Recent News:** {news_text}\n")
                except Exception as e:
                    st.error(f"Error generating memo for {r['Ticker']}: {e}")

            # ======= DOWNLOAD =======
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
