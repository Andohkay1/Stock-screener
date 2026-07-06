import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import io
import time
import requests
import re

# ======= CONFIG =======
FINNHUB_API_KEY = "d5gqckpr01qll3dk0t60d5gqckpr01qll3dk0t6g"

st.set_page_config(
    page_title="Akab Stock Screener – Graham-Verified",
    page_icon="📉",
    layout="wide"
)

st.title("Akab Stock Screener")
st.markdown(
    "Manual ticker checker plus automatic undervalued finder using Yahoo Finance 52 Week Stock Losers."
)

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
def clean_symbol(symbol):
    """Clean ticker symbols pulled from Yahoo tables or APIs."""
    if pd.isna(symbol):
        return None

    symbol = str(symbol).strip().upper()
    symbol = re.sub(r"[^A-Z0-9.\-]", "", symbol)

    if not symbol or symbol in {"SYMBOL", "N/A", "NONE", "NAN"}:
        return None

    return symbol


@st.cache_data(ttl=60 * 30)
def get_yahoo_52_week_lows(max_tickers=100):
    """
    Pull tickers from Yahoo Finance 52 Week Stock Losers only.

    This function uses several methods because Yahoo Finance changes its pages
    often and sometimes blocks simple HTML table reads.

    Order used:
    1. Yahoo predefined screener API using multiple known screener IDs
    2. Yahoo market-list page embedded JSON symbols
    3. Yahoo market-list page HTML tables
    """
    list_type = "52-week-losers"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    yahoo_urls = {
        "52-week-losers": "https://finance.yahoo.com/markets/stocks/52-week-losers/",
    }

    # These names have changed over time, so keep several low-list candidates.
    fallback_scr_ids = {
        "52-week-losers": [
            "fifty_two_wk_losers",
            "fifty_two_wk_lows",
            "52_week_lows",
            "fifty_two_week_lows",
            "fifty_two_week_losers",
        ],
    }

    def dedupe(symbols):
        unique = []
        seen = set()
        for symbol in symbols:
            symbol = clean_symbol(symbol)
            if symbol and symbol not in seen:
                seen.add(symbol)
                unique.append(symbol)
        return unique[:max_tickers]

    def get_52w_change_percent(quote):
        """Return Yahoo's 52-week change percent when available, so biggest losers come first."""
        for key in [
            "fiftyTwoWeekChangePercent",
            "52WeekChangePercent",
            "fiftyTwoWeekChange",
            "52 Week Change %",
            "52 Wk Change %",
        ]:
            value = quote.get(key) if isinstance(quote, dict) else None
            if isinstance(value, dict):
                value = value.get("raw", value.get("fmt"))
            if value is not None:
                try:
                    return float(str(value).replace("%", "").replace(",", ""))
                except Exception:
                    continue
        return None

    def symbols_from_quotes(quotes):
        clean_quotes = [q for q in quotes if isinstance(q, dict) and q.get("symbol")]

        # Yahoo's page is normally already ordered by the biggest negative 52 Wk Change %.
        # This sort keeps Akab aligned with that purpose whenever the API supplies the field.
        if any(get_52w_change_percent(q) is not None for q in clean_quotes):
            clean_quotes = sorted(
                clean_quotes,
                key=lambda q: get_52w_change_percent(q)
                if get_52w_change_percent(q) is not None
                else 999999,
            )

        return dedupe([q.get("symbol") for q in clean_quotes])

    # Method 1: Yahoo Finance predefined screener API.
    # Try query2 first, then query1. Some networks prefer one over the other.
    for domain in ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]:
        for scr_id in fallback_scr_ids[list_type]:
            try:
                api_url = (
                    f"https://{domain}/v1/finance/screener/predefined/saved"
                    f"?formatted=false&lang=en-US&region=US&count={int(max_tickers)}&scrIds={scr_id}"
                )
                resp = requests.get(api_url, headers=headers, timeout=20)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                result = data.get("finance", {}).get("result", [])
                if not result:
                    continue

                quotes = result[0].get("quotes", [])
                tickers = symbols_from_quotes(quotes)
                if tickers:
                    return tickers
            except Exception:
                continue

    # Method 2: Yahoo market page embedded JSON. This works when Yahoo renders
    # data in script tags instead of plain HTML tables.
    try:
        page_url = yahoo_urls[list_type]
        response = requests.get(page_url, headers=headers, timeout=20)
        if response.status_code == 200:
            html = response.text

            # Pull ticker-looking values from embedded JSON: "symbol":"AAPL"
            symbols = re.findall(r'"symbol"\s*:\s*"([A-Z0-9.\-]{1,12})"', html)
            tickers = dedupe(symbols)
            if tickers:
                return tickers

            # Some pages encode quotes differently.
            symbols = re.findall(r'"ticker"\s*:\s*"([A-Z0-9.\-]{1,12})"', html)
            tickers = dedupe(symbols)
            if tickers:
                return tickers
    except Exception:
        pass

    # Method 3: HTML table read. Kept as a final fallback because the new Yahoo
    # market pages often do not include normal static tables.
    try:
        page_url = yahoo_urls[list_type]
        response = requests.get(page_url, headers=headers, timeout=20)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))

        for table in tables:
            table.columns = [str(c).strip() for c in table.columns]
            symbol_col = None

            for col in table.columns:
                if str(col).lower() in {"symbol", "ticker"}:
                    symbol_col = col
                    break

            if symbol_col is not None:
                tickers = dedupe(table[symbol_col].tolist())
                if tickers:
                    return tickers
    except Exception:
        pass

    return []


@st.cache_data(ttl=60 * 60 * 24)
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
                for key in [
                    "CashAndCashEquivalents",
                    "AccountsReceivable",
                    "Inventory",
                    "OtherShortTermInvestments",
                ]
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

        eps_values = [eps for eps in eps_values if isinstance(eps, (int, float)) and not pd.isna(eps)]
        if not eps_values:
            eps_values = [info.get("trailingEps", 0) or 0] * 7

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
        bvps = info.get("bookValue", 0) or 0
        graham_number = np.sqrt(22.5 * eps_7yr_avg * bvps) if eps_7yr_avg > 0 and bvps > 0 else None
        graham_value = eps_5yr_avg * (8.5 + 2 * eps_growth) * (4.4 / current_bond_yield) if eps_5yr_avg > 0 else None

        # Screening Metrics
        current_ratio = info.get("currentRatio", 0) or (current_assets / current_liabilities if current_liabilities else 0)
        revenue = info.get("totalRevenue", 0) or 0
        pb_ratio = info.get("priceToBook", 0) or 0
        current_price = info.get("currentPrice", 0) or info.get("regularMarketPrice", 0) or 0
        dividend_rate = info.get("dividendRate", 0) or 0
        price_ceiling = 15 * eps_5yr_avg if eps_5yr_avg > 0 else 0

        fifty_two_week_low = info.get("fiftyTwoWeekLow", None)
        fifty_two_week_high = info.get("fiftyTwoWeekHigh", None)

        percent_below_52w_high = None
        if current_price and fifty_two_week_high:
            percent_below_52w_high = ((fifty_two_week_high - current_price) / fifty_two_week_high) * 100

        percent_above_52w_low = None
        if current_price and fifty_two_week_low:
            percent_above_52w_low = ((current_price - fifty_two_week_low) / fifty_two_week_low) * 100

        # --- Screening Criteria ---
        criteria = {
            "Revenue > $100M": revenue > 100_000_000,
            "Current Ratio > 2": current_ratio > 2,
            "CA - L > 0": current_assets > total_liabilities,
            "Pays Dividends": dividend_rate > 0,
            "Positive EPS for 5Y": sum(eps > 0 for eps in eps_values[-5:]) >= 4,
            "Price ≤ 15x3Y Avg EPS": current_price <= price_ceiling if current_price and price_ceiling else False,
            "P/B < 1.5": pb_ratio < 1.5 if pb_ratio else False,
        }
        passed = sum(criteria.values())
        mark = lambda val: "✅" if val else "❌"

        criteria_risks = {
            "Revenue > $100M": "Revenue is low; company may lack scale for stability.",
            "Current Ratio > 2": "Liquidity is below safe threshold; company may struggle to meet short-term obligations.",
            "CA - L > 0": "Current Assets do not cover total liabilities; liquidity risk.",
            "Pays Dividends": "Does not pay dividends; may indicate weaker shareholder returns or cash allocation priorities.",
            "Positive EPS for 5Y": "Earnings are inconsistent; profitability risk exists.",
            "Price ≤ 15x3Y Avg EPS": "Stock price exceeds 15x 3-year average EPS; potentially overvalued.",
            "P/B < 1.5": "Price-to-Book ratio is high; stock may be overvalued relative to net assets.",
        }
        failed_criteria = [k for k, v in criteria.items() if not v]

        return {
            "Ticker": ticker,
            "Company Name": info.get("shortName", ticker),
            "Price": current_price,
            "52W Low": fifty_two_week_low,
            "52W High": fifty_two_week_high,
            "% Below 52W High": percent_below_52w_high,
            "% Above 52W Low": percent_above_52w_low,
            "Revenue > $100M": f"{revenue:,} {mark(criteria['Revenue > $100M'])}",
            "Current Ratio > 2": f"{current_ratio:.2f} {mark(criteria['Current Ratio > 2'])}",
            "CA - L > 0": f"{(current_assets - total_liabilities):,.0f} {mark(criteria['CA - L > 0'])}",
            "Pays Dividends": f"{dividend_rate:.2f} {mark(criteria['Pays Dividends'])}" if dividend_rate else "0.00 ❌",
            "Positive EPS for 5Y": f"{'Yes' if criteria['Positive EPS for 5Y'] else 'No'} {mark(criteria['Positive EPS for 5Y'])}",
            "Price ≤ 15x3Y Avg EPS": f"${current_price:.2f} ≤ ${price_ceiling:.2f} {mark(criteria['Price ≤ 15x3Y Avg EPS'])}" if price_ceiling else "N/A ❌",
            "P/B": f"{pb_ratio:.2f} {mark(criteria['P/B < 1.5'])}" if pb_ratio else "N/A ❌",
            "Passed Count": passed,
            "Akab Status": "Strong Candidate" if passed == 7 else "Watchlist" if passed >= 5 else "Does Not Pass",
            "Graham Number": (
                f"${graham_number:.2f} ✅" if graham_number and current_price <= graham_number
                else f"${graham_number:.2f} ❌" if graham_number
                else "N/A ❌"
            ),
            "Graham Value": (
                f"${graham_value:.2f} ✅" if graham_value and current_price <= graham_value
                else f"${graham_value:.2f} ❌" if graham_value
                else "N/A ❌"
            ),
            "Industry": info.get("industry", "N/A"),
            "Current Assets": current_assets,
            "Current Liabilities": current_liabilities,
            "Total Liabilities": total_liabilities,
            "Current Ratio Num": current_ratio,
            "Working Capital": working_capital,
            "Failed Criteria": failed_criteria,
            "Criteria Risks": criteria_risks,
        }

    except Exception as e:
        # Return None so a single failed ticker does not stop the full scanner.
        return None


# ======= FINNHUB NEWS =======
def fetch_news(symbol):
    url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from=2025-01-01&to=2026-01-09&token={FINNHUB_API_KEY}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            headlines = [d.get("headline") for d in data if "headline" in d]
            return " | ".join(headlines[:5]) if headlines else "No recent news available."
        return "No recent news available."
    except Exception:
        return "No recent news available."


def display_screen_results(results, source_label="Manual Screener", passed_only_default=False):
    """Shared display for manual mode and automatic Yahoo 52-week-loser mode.

    passed_only_default=True is used for the automatic undervalued finder:
    show passed stocks first and keep watchlist/full scan hidden in expanders.
    """
    if not results:
        st.warning("No valid data returned.")
        return

    df = pd.DataFrame(results)
    df_sorted = df.sort_values("Passed Count", ascending=False)

    st.success(f"✅ Screening complete for {len(df_sorted)} tickers from {source_label}.")

    table_cols = [
        "Ticker",
        "Company Name",
        "Price",
        "52W Low",
        "52W High",
        "% Below 52W High",
        "% Above 52W Low",
        "Revenue > $100M",
        "Current Ratio > 2",
        "CA - L > 0",
        "Pays Dividends",
        "Positive EPS for 5Y",
        "Price ≤ 15x3Y Avg EPS",
        "P/B",
        "Passed Count",
        "Akab Status",
        "Graham Number",
        "Graham Value",
    ]

    existing_cols = [col for col in table_cols if col in df_sorted.columns]

    strong_candidates = df_sorted[df_sorted["Passed Count"] == 7]
    watchlist = df_sorted[df_sorted["Passed Count"].between(5, 6)]

    st.markdown("### Strong Akab Candidates")
    st.caption("Default view: top Yahoo 52-week losers that passed all 7 Akab criteria.")
    if strong_candidates.empty:
        st.info("No stocks passed all 7 Akab criteria in this scan.")
    else:
        st.dataframe(strong_candidates[existing_cols], use_container_width=True)

    if passed_only_default:
        with st.expander("Akab Watchlist — passed 5 or 6 of 7", expanded=False):
            if watchlist.empty:
                st.info("No watchlist stocks found in this scan.")
            else:
                st.dataframe(watchlist[existing_cols], use_container_width=True)

        with st.expander("Full 52-week-loser scan details", expanded=False):
            st.caption("These are all scanned stocks. They are hidden by default because Akab should surface passed candidates first.")
            st.dataframe(df_sorted[existing_cols], use_container_width=True)
    else:
        st.markdown("### Akab Watchlist")
        st.caption("Passed 5 or 6 of the 7 criteria.")
        if watchlist.empty:
            st.info("No watchlist stocks found in this scan.")
        else:
            st.dataframe(watchlist[existing_cols], use_container_width=True)

        st.markdown("### Full Scan Results")
        st.dataframe(df_sorted[existing_cols], use_container_width=True)

    # ======= INVESTMENT MEMOS =======
    st.markdown("### Investment Memos")
    memo_count = st.slider(
        "Number of memos to generate",
        min_value=0,
        max_value=min(20, len(df_sorted)),
        value=min(5, len(df_sorted)),
        key=f"memo_count_{source_label}",
    )

    for idx, r in df_sorted.head(memo_count).iterrows():
        try:
            company_name = r["Company Name"]
            industry = r["Industry"]
            products = industry_products.get(industry, "")
            industry_note = (
                f"Operates in the {industry} sector. Key products/services: {products}"
                if products
                else f"Operates in the {industry} sector."
            )

            try:
                gn_val = float(str(r["Graham Number"]).split()[0].replace("$", ""))
            except Exception:
                gn_val = None
            try:
                gv_val = float(str(r["Graham Value"]).split()[0].replace("$", ""))
            except Exception:
                gv_val = None

            current_price = r["Price"]

            if gn_val and gv_val:
                if current_price > gn_val and current_price > gv_val:
                    valuation_insight = "potentially overvalued as price above Graham Number and Graham Value"
                elif current_price < gn_val and current_price < gv_val:
                    valuation_insight = "potentially undervalued as price below Graham Number and Graham Value"
                else:
                    valuation_insight = "mixed valuation as price is between Graham Number and Graham Value"
            else:
                valuation_insight = "valuation data insufficient"

            ca = r.get("Current Assets", 0)
            cl = r.get("Current Liabilities", 0)
            tl = r.get("Total Liabilities", 0)
            wc = r.get("Working Capital", 0)
            cr = r.get("Current Ratio Num", 0)

            if ca > 0 or cl > 0 or tl > 0:
                if ca > tl:
                    strength_note = "Current Assets can pay all debt"
                elif wc >= 0 and cr >= 1 and ca <= tl:
                    strength_note = "Working capital positive, but Current Assets do not cover total liabilities; leverage risk remains."
                else:
                    strength_note = "No material balance sheet item identified"
            else:
                strength_note = "No material balance sheet item identified"

            failed_criteria = r.get("Failed Criteria", [])
            criteria_risks = r.get("Criteria Risks", {})
            risk_exclude = ["Current Ratio > 2", "CA - L > 0"]
            filtered_failed = [c for c in failed_criteria if c not in risk_exclude]

            if filtered_failed:
                risk_note = "Potential risks: " + "; ".join(
                    [criteria_risks[k] for k in filtered_failed if k in criteria_risks]
                ) + ". Consider market conditions."
            else:
                risk_note = "No major screening risks identified. Consider general market conditions."

            news_text = fetch_news(r["Ticker"])

            st.markdown(
                f"**{company_name} ({r['Ticker']})**\n\n"
                f"**Source:** {source_label}\n\n"
                f"**Industry Note:** {industry_note}\n\n"
                f"**Valuation Insight:** {company_name} is trading at ${current_price:.2f}, {valuation_insight}.\n\n"
                f"**52-Week Context:** Low: {r.get('52W Low', 'N/A')}, High: {r.get('52W High', 'N/A')}, "
                f"Below 52W High: {r.get('% Below 52W High', 'N/A')}.\n\n"
                f"**Screening Rationale:** Passed {r['Passed Count']} of 7 Akab screening criteria.\n\n"
                f"**Strength Note:** {strength_note}\n\n"
                f"**Risk Note:** {risk_note}\n\n"
                f"**Recent News:** {news_text}\n"
            )
        except Exception as e:
            st.error(f"Error generating memo for {r.get('Ticker', 'Unknown')}: {e}")

    # ======= DOWNLOAD =======
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_sorted.to_excel(writer, index=False)

    safe_source = source_label.lower().replace(" ", "_").replace("-", "_")
    st.download_button(
        label="📥 Download Results as Excel",
        data=output.getvalue(),
        file_name=f"akab_{safe_source}_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def collect_akab_results(tickers):
    """Return Akab results for a list of tickers without displaying them."""
    tickers = list(dict.fromkeys([clean_symbol(t) for t in tickers if clean_symbol(t)]))
    results = []
    for ticker in tickers:
        data = fetch_financials(ticker)
        if data:
            results.append(data)
    return results


@st.cache_data(ttl=60 * 60)
def cached_auto_52_week_low_results(max_tickers):
    """Pull Yahoo 52 Week Stock Losers and run Akab automatically. Cached for one hour."""
    yahoo_tickers = get_yahoo_52_week_lows(max_tickers=max_tickers)
    if not yahoo_tickers:
        return [], []
    return yahoo_tickers, collect_akab_results(yahoo_tickers)


def run_akab_scan(tickers, source_label, passed_only_default=False):
    """Run the Akab model against a list of tickers."""
    tickers = list(dict.fromkeys([clean_symbol(t) for t in tickers if clean_symbol(t)]))

    if not tickers:
        st.warning("Please provide at least one valid ticker.")
        return

    results = []
    progress = st.progress(0)
    status = st.empty()

    for idx, ticker in enumerate(tickers):
        status.write(f"Checking {ticker} ({idx + 1} of {len(tickers)})...")
        data = fetch_financials(ticker)
        if data:
            results.append(data)
        progress.progress((idx + 1) / len(tickers))
        time.sleep(0.25)

    status.empty()
    display_screen_results(results, source_label=source_label, passed_only_default=passed_only_default)


# ======= APP LAYOUT =======
tab1, tab2 = st.tabs([
    "Manual Akab Checker",
    "Automatic Undervalued Finder",
])

with tab1:
    st.subheader("Manual Akab Checker")
    st.caption("This keeps your original version: enter tickers manually or upload a CSV.")

    tickers = []

    manual_input = st.text_area(
        "Enter tickers separated by commas (e.g., AAPL, MSFT, TSLA)",
        key="manual_input",
    )
    if manual_input:
        tickers.extend([t.strip().upper() for t in manual_input.split(",") if t.strip()])

    uploaded_file = st.file_uploader("Or upload CSV with tickers", type="csv", key="manual_csv")
    if uploaded_file is not None:
        df_upload = pd.read_csv(uploaded_file)
        tickers.extend(df_upload.iloc[:, 0].dropna().astype(str).tolist())

    if st.button("🚀 Run Manual Screener", key="run_manual"):
        run_akab_scan(tickers, source_label="Manual Screener")


with tab2:
    st.subheader("Automatic Akab Undervalued Finder")
    st.caption(
        "Source: Yahoo Finance 52 Week Stock Losers only. Akab checks the biggest 52-week percentage losers for financial strength and value."
    )

    st.markdown("**Yahoo Finance source:** 52 Week Stock Losers only")

    max_tickers = st.number_input(
        "Number of top Yahoo 52-week losers to check automatically",
        min_value=10,
        max_value=250,
        value=100,
        step=10,
    )

    st.info(
        "This tab runs automatically and shows Strong Akab Candidates first. "
        "The watchlist and full scan are still available, but hidden in expanders."
    )

    if st.button("🔄 Refresh Yahoo 52-Week Losers Scan", key="refresh_auto"):
        cached_auto_52_week_low_results.clear()
        st.rerun()

    with st.spinner("Automatically checking top Yahoo Finance 52-week losers..."):
        yahoo_tickers, auto_results = cached_auto_52_week_low_results(max_tickers)

    if not yahoo_tickers:
        st.error(
            "Could not pull tickers from Yahoo Finance right now. "
            "Try again later, reduce the ticker count, or use the Manual Akab Checker tab."
        )
    elif not auto_results:
        st.warning("Yahoo tickers were found, but no valid Akab financial data was returned.")
    else:
        st.write(f"Automatically checked the top {len(auto_results)} stocks from Yahoo Finance 52 Week Stock Losers.")
        display_screen_results(
            auto_results,
            source_label="Yahoo Finance 52 Week Stock Losers",
            passed_only_default=True,
        )
