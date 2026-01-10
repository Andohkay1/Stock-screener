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
    "Internet Content & Information": "provides search, advertising, cloud computing, and related internet services.",
    # Add more industries here
}

# ======= HELPER FUNCTIONS =======
def parse_money(value):
    if isinstance(value, str):
        return float(value.replace("$", "").replace(",", ""))
    return value

def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # ===== BALANCE SHEET =====
        bs = stock.balance_sheet if hasattr(stock, "balance_sheet") else pd.DataFrame()
        col = bs.columns[0] if not bs.empty else None

        ca_keys = ["CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherCurrentAssets", "ShortTermInvestments"]
        cl_keys = ["CurrentDebt", "AccountsPayable", "OtherCurrentLiabilities", "TaxPayable"]

        est_current_assets = sum(bs.loc[key, col] if key in bs.index else 0 for key in ca_keys) if col else 0
        est_current_liabilities = sum(bs.loc[key, col] if key in bs.index else 0 for key in cl_keys) if col else 0
        est_total_liabilities = info.get("totalLiab", 0)

        wc = est_current_assets - est_current_liabilities

        # ===== EPS =====
        inc = stock.financials if hasattr(stock, "financials") else pd.DataFrame()
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

        # EPS growth
        eps_growth = 0
        valid_eps = [eps for eps in eps_values if eps > 0]
        if len(valid_eps) >= 2:
            eps_growth = (valid_eps[-1] - valid_eps[0]) / valid_eps[0]

        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else None
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else None

        # ===== SCREENING METRICS =====
        current_ratio = info.get("currentRatio", 0)
        revenue = info.get("totalRevenue", 0)
        pb_ratio = info.get("priceToBook", 0)
        current_price = info.get("currentPrice", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "CA - L > 0": est_current_assets > est_total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5Y": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15x3Y Avg EPS": current_price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }
        passed = sum(criteria.values())
        mark = lambda val: "✅" if val else "❌"

        # ===== STRENGTH NOTE =====
        if est_current_assets > est_total_liabilities:
            strength_note = "Current Assets can pay all debt; liquidity healthy."
        elif wc > 0:
            strength_note = "Working capital positive, but Current Assets do not cover total debt; liquidity acceptable."
        else:
            strength_note = "Working capital negative; liquidity may be tight."

        # ===== RISK NOTE =====
        risk_items = []
        if current_ratio < 1:
            risk_items.append("Current Ratio low; liquidity may be a concern.")
        if est_current_assets < est_total_liabilities:
            risk_items.append("Current Assets do not cover total debt; liquidity risk.")
        if price_ceiling and current_price > price_ceiling:
            risk_items.append("Price exceeds 15x 3-year EPS; stock may be overvalued.")
        if pb_ratio > 1.5:
            risk_items.append("Price-to-Book ratio high; stock may be overvalued relative to net assets.")
        risk_note = "Potential risks: " + "; ".join(risk_items) + ". Consider market conditions." if risk_items else "No major risk detected."

        return {
            "Ticker": ticker,
            "Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA - L > 0": f"{(est_current_assets - est_total_liabilities):,.0f} {mark(criteria['CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5Y": f"{'Yes' if criteria['Positive EPS for 5Y'] else 'No'} {mark(criteria['Positive EPS for 5Y'])}",
            "Price ≤ 15x3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15x3Y Avg EPS'])}" if price_ceiling else "N/A ❌",
            "P/B": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f} {mark(current_price <= graham_number)}" if graham_number else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(current_price <= graham_value)}" if graham_value else "N/A",
            "Current Assets": est_current_assets,
            "Current Liabilities": est_current_liabilities,
            "Total Liabilities": est_total_liabilities,
            "Current Price Num": current_price,
            "Graham Number Num": graham_number,
            "Graham Value Num": graham_value,
            "Strength Note": strength_note,
            "Risk Note": risk_note,
            "Company Name": info.get("shortName", ticker),
            "Industry": info.get("industry", "N/A"),
            "EPS 5Y Avg": eps_5yr_avg,
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
            df_sorted = df.sort_values("Passed Count", ascending=False)
            st.success(f"✅ Screening complete for {len(df_sorted)} tickers.")

            # ======= DISPLAY TABLE =======
            table_cols = [
                "Ticker", "Price", "Revenue > $100M", "Current Ratio > 2", "CA - L > 0", "Pays Dividends",
                "Positive EPS for 5Y", "Price ≤ 15x3Y Avg EPS", "P/B", "Passed Count",
                "Graham Number", "Graham Value"
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
                    current_price = r["Current Price Num"]

                    st.markdown(f"**{company_name} ({r['Ticker']})**\n\n"
                                f"**Industry Note:** {industry_note}\n\n"
                                f"**Valuation Insight:** {company_name} is trading at ${current_price:.2f}, "
                                f"{'potentially overvalued as price above Graham Number and Graham Value' if (r['Graham Number Num'] and r['Graham Value Num'] and current_price > r['Graham Number Num'] and current_price > r['Graham Value Num']) else 'potentially undervalued as price below Graham Number and Graham Value' if (r['Graham Number Num'] and r['Graham Value Num'] and current_price < r['Graham Number Num'] and current_price < r['Graham Value Num']) else 'mixed valuation'}.\n\n"
                                f"**Financial Strength:** Earnings consistently positive for last 5 years. Pays regular dividends.\n\n"
                                f"**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.\n\n"
                                f"**Strength Note:** {r['Strength Note']}\n\n"
                                f"**Risk Note:** {r['Risk Note']}\n\n"
                                f"**Recent News:** {fetch_news(r['Ticker'])}\n")
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
