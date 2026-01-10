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

# ======= INDUSTRY PRODUCTS =======
industry_products = {
    "Internet Content & Information": "provides search, digital advertising, cloud computing, and internet-based platforms.",
    "Technology": "develops software, hardware, and digital infrastructure.",
    "Consumer Defensive": "produces and distributes consumer staple products.",
    "Financial Services": "offers banking, insurance, and investment services.",
    "Healthcare": "develops pharmaceuticals, medical devices, and healthcare solutions.",
    "Energy": "produces and distributes oil, gas, and renewable energy.",
    "Industrials": "manufactures industrial equipment and machinery."
}

# ======= STRENGTH & RISK HELPERS =======

def get_strength_note(ca, cl, tl, wc, cr):
    if ca > tl and cr >= 1:
        return "Current Assets can pay all debt; balance sheet strength is strong."
    if wc >= 0 and cr >= 1:
        return "Working capital positive with acceptable liquidity."
    return None


def get_liquidity_risk(ca, cl, tl, wc, cr):
    if ca <= tl:
        return "Current Assets do not cover total liabilities; leverage risk."
    if wc < 0 and cr < 1:
        return "Working capital negative and current ratio below 1; liquidity may be tight."
    if wc >= 0 and cr < 1:
        return "Working capital positive but current ratio below 1; short-term liquidity risk."
    if wc < 0 and cr >= 1:
        return "Negative working capital suggests reliance on operating cash flows."
    return None


def get_screening_risk_notes(failed_criteria, criteria_risks):
    return [criteria_risks[c] for c in failed_criteria if c in criteria_risks]

# ======= FETCH FINANCIALS =======

def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        bs = stock.balance_sheet
        inc = stock.income_stmt

        col = bs.columns[0] if not bs.empty else None

        # ----- Current Assets -----
        current_assets = float(info.get("totalCurrentAssets", 0) or 0)

        # ----- Current Liabilities -----
        current_liabilities = float(info.get("currentLiabilities", 0) or 0)

        # ----- Total Liabilities -----
        total_liabilities = float(info.get("totalLiab", 0) or current_liabilities)

        working_capital = current_assets - current_liabilities

        # ----- EPS -----
        shares = info.get("sharesOutstanding", 0)
        eps_values = []

        if not inc.empty and "Net Income" in inc.index and shares:
            for ni in inc.loc["Net Income"].dropna():
                eps_values.append(ni / shares)

        eps_values = [e for e in eps_values if e > 0]

        if not eps_values:
            eps_values = [info.get("trailingEps", 0)] * 5

        eps_5 = np.mean(eps_values[-5:])
        eps_7 = np.mean(eps_values[-7:])

        eps_growth = 0
        if len(eps_values) >= 2 and eps_values[0] > 0:
            eps_growth = (eps_values[-1] - eps_values[0]) / eps_values[0]

        # ----- Graham -----
        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7 * bvps) if eps_7 > 0 and bvps > 0 else None
        graham_value = eps_5 * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5 > 0 else None

        # ----- Ratios -----
        current_ratio = info.get("currentRatio", 0) or (
            current_assets / current_liabilities if current_liabilities else 0
        )

        revenue = info.get("totalRevenue", 0)
        pb_ratio = info.get("priceToBook", 0)
        price = info.get("currentPrice", 0)
        dividend_rate = info.get("dividendRate", 0)
        price_ceiling = 15 * eps_5 if eps_5 > 0 else 0

        # ----- Screening Criteria -----
        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "CA - L > 0": current_assets > total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5Y": len(eps_values[-5:]) >= 4,
            "Price ≤ 15x3Y Avg EPS": price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }

        criteria_risks = {
            "Revenue > $100M": "Revenue scale is limited; business stability risk.",
            "Current Ratio > 2": "Liquidity below conservative threshold.",
            "CA - L > 0": "Assets do not cover total liabilities.",
            "Pays Dividends": "No dividend payout; return depends on price appreciation.",
            "Positive EPS for 5Y": "Earnings history inconsistent.",
            "Price ≤ 15x3Y Avg EPS": "Valuation exceeds earnings-based ceiling.",
            "P/B < 1.5": "High price-to-book; valuation risk."
        }

        passed = sum(criteria.values())

        mark = lambda x: "✅" if x else "❌"

        return {
            "Ticker": ticker,
            "Price": price,
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA - L > 0": f"{(current_assets - total_liabilities):,.0f} {mark(criteria['CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else "0.00 ❌",
            "Positive EPS for 5Y": f"Yes {mark(criteria['Positive EPS for 5Y'])}",
            "Price ≤ 15x3Y Avg EPS": f"${price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15x3Y Avg EPS'])}",
            "P/B": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f}" if graham_number else "N/A",
            "Graham Value": f"${graham_value:.2f}" if graham_value else "N/A",
            "Industry": info.get("industry", "N/A"),
            "Company Name": info.get("shortName", ticker),
            "Current Assets": current_assets,
            "Current Liabilities": current_liabilities,
            "Total Liabilities": total_liabilities,
            "Working Capital": working_capital,
            "Current Ratio Num": current_ratio,
            "Failed Criteria": [k for k, v in criteria.items() if not v],
            "Criteria Risks": criteria_risks,
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

# ======= INPUT =======
tickers = st.text_area("Enter tickers separated by commas").upper().split(",")

# ======= RUN =======
if st.button("🚀 Run Screener"):
    results = []
    for t in tickers:
        t = t.strip()
        if t:
            data = fetch_financials(t)
            if data:
                results.append(data)

    df = pd.DataFrame(results)
    st.dataframe(df)

    st.markdown("### Investment Memos")

    for _, r in df.iterrows():
        ca, cl, tl, wc, cr = r["Current Assets"], r["Current Liabilities"], r["Total Liabilities"], r["Working Capital"], r["Current Ratio Num"]

        strength = get_strength_note(ca, cl, tl, wc, cr) or "No balance sheet strength identified."
        risks = []

        liq_risk = get_liquidity_risk(ca, cl, tl, wc, cr)
        if liq_risk:
            risks.append(liq_risk)

        risks.extend(get_screening_risk_notes(r["Failed Criteria"], r["Criteria Risks"]))

        risk_note = "Potential risks: " + "; ".join(risks) if risks else "No major risks identified."

        st.markdown(f"""
**{r['Company Name']} ({r['Ticker']})**

**Strength Note:** {strength}

**Risk Note:** {risk_note}
""")
