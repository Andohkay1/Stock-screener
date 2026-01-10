import streamlit as st
import pandas as pd
import requests

# --- Helper Functions ---
def parse_money(value):
    """Convert a string like '$1,234.56 ✅' to float 1234.56"""
    if value in [None, "N/A"]:
        return None
    return float("".join(c for c in str(value) if c.isdigit() or c == "."))

def mark(condition):
    return "✅" if condition else "❌"

# --- Dummy Data / Replace with your screening logic ---
results = [
    {
        "Ticker": "AAPL",
        "Company Name": "Apple Inc.",
        "Industry": "Technology",
        "Price": "$259.37",
        "Revenue > $100M": True,
        "Current Ratio > 2": False,
        "CA - L > 0": True,
        "Pays Dividends": True,
        "Positive EPS for 5Y": True,
        "Price ≤ 15x3Y Avg EPS": False,
        "P/B": 51.97,
        "Passed Count": 4,
        "Graham Number": "$27.73 ❌",
        "Graham Value": "$56.71 ❌",
        "Strength Note": "Current Assets pay all Total Liabilities.",
        "Recent News": "Jamie Dimon's Grip On US Credit Card Dominance Grows..."
    },
    {
        "Ticker": "SMCAY",
        "Company Name": "SMC Corporation",
        "Industry": "Specialty Industrial Machinery",
        "Price": "$18.87",
        "Revenue > $100M": True,
        "Current Ratio > 2": True,
        "CA - L > 0": True,
        "Pays Dividends": True,
        "Positive EPS for 5Y": True,
        "Price ≤ 15x3Y Avg EPS": True,
        "P/B": 0.09,
        "Passed Count": 7,
        "Graham Number": "$815.86 ❌",
        "Graham Value": "$1335.40 ❌",
        "Strength Note": "Current Assets pay all Total Liabilities.",
        "Recent News": "Touchstone Sands Capital International Growth Equity Fund Q3 2025 Portfolio Update..."
    }
]

# --- Products Dictionary (or fetch from Yahoo Finance API) ---
products_dict = {
    "AAPL": "iPhone, Mac, iPad, Apple Watch, AirPods, Services",
    "SMCAY": "Air management systems, directional control valves, air cylinders, actuators, grippers"
}

# --- Streamlit App ---
st.title("Akab Stock Screener")
st.write("### Screening Results")

# --- Display Table ---
table_cols = ["Ticker", "Price", "Revenue > $100M", "Current Ratio > 2", "CA - L > 0",
              "Pays Dividends", "Positive EPS for 5Y", "Price ≤ 15x3Y Avg EPS",
              "P/B", "Passed Count", "Graham Number", "Graham Value"]

df_table = pd.DataFrame([{col: r[col] for col in table_cols} for r in results])
st.dataframe(df_table)

# --- Investment Memos ---
st.markdown("### Investment Memos")
for r in results:
    ticker = r["Ticker"]
    company_name = r["Company Name"]
    industry = r["Industry"]
    products = products_dict.get(ticker, "N/A")
    current_price = parse_money(r["Price"])

    # --- Clean Graham Values ---
    def clean_money(value):
        if value == "N/A" or value is None:
            return None
        return float("".join(c for c in str(value) if c.isdigit() or c == "."))

    gn_val = clean_money(r["Graham Number"])
    gv_val = clean_money(r["Graham Value"])

    # --- Valuation Insight ---
    if gn_val is not None and gv_val is not None:
        if current_price > gn_val and current_price > gv_val:
            insight = "potentially overvalued"
        elif current_price < gn_val and current_price < gv_val:
            insight = "potentially undervalued"
        else:
            insight = "fairly valued"
    else:
        insight = "Graham metrics not available"

    memo = f"""
**{company_name} ({ticker})**

Industry Note: Operates in the {industry} sector.
Key products/services: {products}

Valuation Insight: {company_name} is trading at ${current_price:.2f}, {insight}.

Financial Strength: Earnings consistently positive for last 5 years. Pays regular dividends.

Screening Rationale: Passed {r['Passed Count']} of 7 Akab screening criteria.

Strength Note: {r['Strength Note']}

Risk Note: Consider valuation sensitivity, liquidity constraints, and market conditions.

Recent News: {r['Recent News']}
"""
    st.markdown(memo)
