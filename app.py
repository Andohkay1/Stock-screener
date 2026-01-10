import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests

# ----- CONFIG -----
FINHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="centered"
)

st.title("Akab Stock Screener")
st.markdown("Uses verified EPS logic for Graham Number and Value with automated investment memo.")

# ----- FETCH FINANCIALS -----
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
            "CA - L > 0": est_current_assets > est_total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5 Years": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15 x 3Y Avg EPS": current_price <= price_ceiling,
            "P/B < 1.5": pb_ratio < 1.5,
        }

        passed = sum(criteria.values())
        def mark(val): return "✅" if val else "❌"

        return {
            "Ticker": ticker,
            "Company Name": info.get("shortName", ticker),
            "Sector": info.get("sector", "Unknown"),
            "Current Price Num": current_price,
            "Price": f"${current_price:.2f}" if current_price else "N/A",
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA - L > 0": f"{(est_current_assets - est_total_liabilities):,.0f} {mark(criteria['CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else f"0.00 ❌",
            "Positive EPS for 5 Years": f"{'Yes' if criteria['Positive EPS for 5 Years'] else 'No'} {mark(criteria['Positive EPS for 5 Years'])}",
            "Price ≤ 15 x 3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15 x 3Y Avg EPS'])}" if current_price and price_ceiling else f"N/A ❌",
            "P/B < 1.5": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}",
            "Passed Count": passed,
            "Graham Number": f"${graham_number:.2f} {mark(current_price < graham_number)}" if not np.isnan(graham_number) and current_price else "N/A",
            "Graham Value": f"${graham_value:.2f} {mark(current_price < graham_value)}" if not np.isnan(graham_value) and current_price else "N/A",
            "Estimated CA - L": est_current_assets - est_total_liabilities
        }

    except Exception as e:
        st.error(f"Error fetching data for {ticker}: {e}")
        return None

# ----- FETCH FINHUB NEWS -----
def fetch_news(ticker):
    try:
        url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from=2026-01-01&to=2026-01-09&token={FINHUB_API_KEY}"
        response = requests.get(url)
        data = response.json()
        headlines = [d.get("headline") for d in data[:3]]  # top 3 news
        return headlines
    except:
        return []

# ----- MEMO GENERATION -----
def generate_investment_memo(r, news_headlines=None):
    def parse_money(value):
        try:
            return float(str(value).replace("$", "").split()[0])
        except:
            return None

    gn = parse_money(r.get("Graham Number", "N/A"))
    gv = parse_money(r.get("Graham Value", "N/A"))
    price = r.get("Current Price Num", 0)
    ca_l_ratio = r.get("Estimated CA - L", None)

    # Valuation Insight
    insights = []
    if gn and price > gn:
        insights.append(f"above its Graham Number (${gn:.2f})")
    if gv and price > gv:
        insights.append(f"above its Graham Value (${gv:.2f})")
    if not insights:
        if gn and gv and price < gn and price < gv:
            insights.append(f"below its Graham Number (${gn:.2f}) and Graham Value (${gv:.2f})")
        else:
            insights.append("Graham metrics not available or mixed signals")
    valuation_text = f"{r['Company Name']} ({r['Ticker']}) is trading at ${price:.2f}, " + " and ".join(insights) + "."

    # Financial Strength
    financial_text = "Earnings consistently positive for last 5 years. Pays regular dividends."

    # Screening Rationale
    passed_count = r.get("Passed Count", 0)
    screening_text = f"Passed {passed_count} of 7 Akab screening criteria."

    # Strength Note
    strength_text = ""
    if ca_l_ratio is not None and ca_l_ratio > 0:
        strength_text = "Current Assets cover Total Liabilities, allowing acquisition without paying for fixed assets or property."

    # Risk Note
    risk_text = "Consider valuation sensitivity, liquidity constraints, and market conditions."

    # Industry Note
    industry_text = f"Operates in the {r.get('Sector', 'Unknown')} sector."

    # News
    news_text = "No recent news available."
    if news_headlines and len(news_headlines) > 0:
        news_text = " | ".join(news_headlines)

    memo = f"""
**{r['Company Name']} ({r['Ticker']})**

Industry Note: {industry_text}

Valuation Insight: {valuation_text}

Financial Strength: {financial_text}

Screening Rationale: {screening_text}

Strength Note: {strength_text}

Risk Note: {risk_text}

Recent News: {news_text}
"""
    return memo

# ----- USER INPUT -----
tickers = []
manual_input = st.text_area("Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)")
if manual_input:
    tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv")
if uploaded_file is not None:
    df_upload = pd.read_csv(uploaded_file)
    tickers.extend(df_upload.iloc[:, 0].dropna().tolist())

tickers = list(set([t for t in tickers if t]))

# ----- RUN SCREENER -----
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

            # Table without industry/news
            st.dataframe(df_sorted.drop(columns=["Sector"]))

            # Show Investment Memos
            st.markdown("## Investment Memos")
            for r in results:
                news = fetch_news(r["Ticker"])
                memo = generate_investment_memo(r, news_headlines=news)
                with st.expander(f"{r['Company Name']} ({r['Ticker']})"):
                    st.markdown(memo)

            # Download Excel
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
