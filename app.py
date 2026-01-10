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
}

# ======= HELPER FUNCTIONS =======
def fetch_financials(ticker, current_bond_yield=4.4):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Balance sheet
        bs = stock.balance_sheet if not stock.balance_sheet.empty else pd.DataFrame()
        col = bs.columns[0] if not bs.empty else None

        ca_keys = ["CashAndCashEquivalents", "AccountsReceivable", "Inventory", "OtherShortTermInvestments"]
        cl_keys = ["AccountsPayable", "OtherCurrentLiabilities", "TaxPayable", "ShortLongTermDebt"]
        tl_keys = ["TotalLiab"]

        def safe_sum(keys):
            total = 0
            for key in keys:
                try:
                    val = bs.loc[key, col] if key in bs.index else 0
                    if pd.isna(val):
                        val = 0
                    total += val
                except:
                    total += 0
            return total

        # Force numeric values
        ca = float(safe_sum(ca_keys) if col else 0) or 0
        cl = float(safe_sum(cl_keys) if col else 0) or 0
        tl = float(safe_sum(tl_keys) if col else 0) or 0
        wc = ca - cl

        # EPS calculations
        eps_values = []
        shares_outstanding = info.get("sharesOutstanding", 0)
        inc = stock.financials if not stock.financials.empty else pd.DataFrame()
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
        if len(eps_values) >= 2:
            valid_eps = [eps for eps in eps_values if eps > 0]
            if len(valid_eps) >= 2:
                oldest, latest = valid_eps[0], valid_eps[-1]
                if oldest > 0:
                    eps_growth = (latest - oldest) / oldest

        bvps = info.get("bookValue", 0)
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else None
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else None

        # Screening metrics
        current_ratio = info.get("currentRatio", 0) or 0
        revenue = info.get("totalRevenue", 0) or 0
        pb_ratio = info.get("priceToBook", 0) or 0
        current_price = info.get("currentPrice", 0) or 0
        dividend_rate = info.get("dividendRate", 0) or 0
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        ca_vs_tl_flag = ca > tl

        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "CA − TL > 0": ca_vs_tl_flag,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5Y": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15x3Y Avg EPS": current_price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }
        passed = sum(criteria.values())
        mark = lambda val: "✅" if val else "❌"

        return {
            "Ticker": ticker,
            "Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA − TL > 0": f"{ca - tl:,.0f} {mark(criteria['CA − TL > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5Y": f"{'Yes' if criteria['Positive EPS for 5Y'] else 'No'} {mark(criteria['Positive EPS for 5Y'])}",
            "Price ≤ 15x3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15x3Y Avg EPS'])}" if price_ceiling else "N/A ❌",
            "P/B": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f} {mark(current_price <= graham_number)}" if graham_number else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(current_price <= graham_value)}" if graham_value else "N/A",
            # For memo only
            "Current Assets": ca,
            "Current Liabilities": cl,
            "Total Liabilities": tl,
            "Working Capital Num": wc,
            "Current Ratio Num": current_ratio,
            "Current Price Num": current_price,
            "Price Ceiling Num": price_ceiling,
            "Graham Number Num": graham_number,
            "Graham Value Num": graham_value,
            "Industry": info.get("industry", "N/A"),
            "Company Name": info.get("shortName", ticker),
        }
    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None
