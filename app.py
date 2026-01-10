import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests

# ================= CONFIG =================
FINNHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Value with automated investment memo.")

# ================= INDUSTRY MAP =================
industry_products = {
    "Technology": "produces software, hardware, and related digital services.",
    "Consumer Electronics": "produces smartphones, computers, and consumer devices.",
    "Healthcare": "develops pharmaceuticals, medical devices, and healthcare services.",
    "Energy": "explores and produces oil, gas, and renewable energy.",
    "Financial Services": "offers banking, insurance, and investment services.",
    "Industrial Metals & Mining": "produces steel, aluminum, and industrial metals."
}

# ================= DATA FETCH =================
def fetch_financials(ticker, bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        inc = stock.income_stmt if not stock.income_stmt.empty else pd.DataFrame()
        col = bs.columns[0] if not bs.empty else None

        # ---- Assets & Liabilities ----
        current_assets = float(info.get("totalCurrentAssets", 0) or 0)
        current_liabilities = float(info.get("currentLiabilities", 0) or 0)
        total_liabilities = float(info.get("totalLiab", 0) or current_liabilities)

        working_capital = current_assets - current_liabilities
        current_ratio = info.get("currentRatio", 0) or (
            current_assets / current_liabilities if current_liabilities else 0
        )

        # ---- EPS ----
        shares = info.get("sharesOutstanding", 0)
        eps_values = []

        if not inc.empty and "Net Income" in inc.index and shares:
            for ni in inc.loc["Net Income"].dropna():
                eps_values.append(ni / shares)

        if not eps_values:
            eps_values = [info.get("trailingEps", 0)] * 7

        eps_5 = np.mean(eps_values[-5:])
        eps_7 = np.mean(eps_values[-7:])

        eps_growth = 0
        if eps_values[0] > 0:
            eps_growth = (eps_values[-1] - eps_values[0]) / eps_values[0]

        # ---- Graham ----
        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7 * bvps) if eps_7 > 0 and bvps > 0 else None
        graham_value = eps_5 * (8.5 + 2 * eps_growth) * (4.4 / bond_yield) if eps_5 > 0 else None

        # ---- Screening ----
        price = float(info.get("currentPrice", 0))
        revenue = info.get("totalRevenue", 0)
        pb = info.get("priceToBook", 0)
        dividend = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5 if eps_5 > 0 else 0

        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "CA - L > 0": current_assets > total_liabilities,
            "Pays Dividends": dividend > 0,
            "Positive EPS for 5Y": sum(e > 0 for e in eps_values[-5:]) >= 4,
            "Price ≤ 15x3Y Avg EPS": price <= price_ceiling,
            "P/B < 1.5": pb < 1.5
        }

        risks_map = {
            "Revenue > $100M": "Revenue is low; scale risk.",
            "Current Ratio > 2": "Low liquidity buffer.",
            "CA - L > 0": "Current Assets do not cover total liabilities.",
            "Pays Dividends": "No dividends paid.",
            "Positive EPS for 5Y": "Earnings inconsistency risk.",
            "Price ≤ 15x3Y Avg EPS": "Stock trades above earnings-based ceiling.",
            "P/B < 1.5": "High valuation relative to book value."
        }

        return {
            "Ticker": ticker,
            "Company Name": info.get("shortName", ticker),
            "Industry": info.get("industry", "N/A"),
            "Price": price,
            "Passed Count": sum(criteria.values()),
            "Criteria": criteria,
            "Criteria Risks": risks_map,
            "Failed Criteria": [k for k, v in criteria.items() if not v],
            "Current Assets": current_assets,
            "Current Liabilities": current_liabilities,
            "Total Liabilities": total_liabilities,
            "Working Capital": working_capital,
            "Current Ratio Num": current_ratio,
            "Graham Number": graham_number,
            "Graham Value": graham_value
        }

    except Exception as e:
        st.error(f"{ticker}: {e}")
        return None

# ================= NEWS =================
def fetch_news(symbol):
    try:
        url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from=2025-01-01&to=2026-01-09&token={FINNHUB_API_KEY}"
        r = requests.get(url)
        if r.status_code == 200:
            headlines = [x["headline"] for x in r.json() if "headline" in x]
            return " | ".join(headlines[:5]) if headlines else "No recent news."
    except:
        pass
    return "No recent news."

# ================= INPUT =================
tickers = []

manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# ================= RUN SCREEN =================
if st.button("🚀 Run Screener"):
    if not tickers:
        st.warning("Please enter or upload at least one ticker.")
    else:
        results = []
        progress = st.progress(0)
        for idx, t in enumerate(tickers):
            time.sleep(0.5)
            data = fetch_financials(t)
            if data:
                results.append(data)
            progress.progress((idx + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results).sort_values("Passed Count", ascending=False)

            # ===== DISPLAY TABLE =====
            table_cols = [
                "Ticker", "Price", "Passed Count", "Graham Number", "Graham Value",
                "Current Assets", "Current Liabilities", "Total Liabilities", "Working Capital", "Current Ratio Num"
            ]
            st.dataframe(df[table_cols])

            # ===== DOWNLOAD BUTTON =====
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False)
            st.download_button(
                label="📥 Download Results as Excel",
                data=output.getvalue(),
                file_name="akab_screening_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # ===== MEMOS =====
            st.markdown("## Investment Memos")
            for _, r in df.iterrows():
                ca = r["Current Assets"]
                tl = r["Total Liabilities"]
                wc = r["Working Capital"]
                cr = r["Current Ratio Num"]

                # ---- Strength ----
                strength_note = "No material balance sheet strength identified."
                if ca > tl:
                    strength_note = "Current Assets fully cover total liabilities; strong balance sheet."

                # ---- Risk ----
                risk_notes = []
                if wc < 0:
                    risk_notes.append("Working capital negative; liquidity may be tight.")
                elif ca <= tl and wc >= 0 and cr >= 1:
                    risk_notes.append("Working capital positive, but assets do not cover liabilities.")
                for f in r["Failed Criteria"]:
                    risk_notes.append(r["Criteria Risks"][f])
                risk_note = "; ".join(set(risk_notes)) if risk_notes else "No major risks identified."

                st.markdown(
                    f"""
**{r['Company Name']} ({r['Ticker']})**

**Industry:** {r['Industry']}

**Strength:** {strength_note}

**Risk:** {risk_note}

**Recent News:** {fetch_news(r['Ticker'])}
"""
                )
        else:
            st.warning("No valid data returned.")
