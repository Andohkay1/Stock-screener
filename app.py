def fetch_financials(ticker, yield_value):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        eps = info.get("trailingEps", None)
        bvps = info.get("bookValue", None)
        revenue = info.get("totalRevenue", 0)
        current_ratio = info.get("currentRatio", 0)
        pb_ratio = info.get("priceToBook", 0)
        price = info.get("currentPrice", None)

        # Graham metrics
        graham_number = (15 * eps * 1.5 * bvps) ** 0.5 if eps and bvps and eps > 0 and bvps > 0 else None
        graham_value = eps * (8.5 + 2 * 0) * (4.4 / yield_value) if eps and eps > 0 else None

        # Display formatting + pass/fail marks
        revenue_display = f"{revenue:,} ✅" if revenue > 100_000_000 else f"{revenue:,} ❌"
        current_ratio_display = f"{current_ratio:.2f} ✅" if current_ratio > 2 else f"{current_ratio:.2f} ❌"
        pb_display = f"{pb_ratio:.2f} ✅" if pb_ratio > 1.5 else f"{pb_ratio:.2f} ❌"
        graham_number_display = f"{graham_number:.2f} ✅" if graham_number else "❌"
        graham_value_display = f"{graham_value:.2f} ✅" if graham_value else "❌"
        eps_display = f"{eps:.2f}" if eps is not None else "N/A"
        bvps_display = f"{bvps:.2f}" if bvps is not None else "N/A"

        # Share price check
        price_display = f"{price:.2f}" if price is not None else "N/A"
        if price is not None and graham_value is not None:
            price_vs_gv = f"{price:.2f} ✅" if price < graham_value else f"{price:.2f} ❌"
        else:
            price_vs_gv = "N/A"

        # Count of passed criteria
        passed_count = sum([
            revenue > 100_000_000,
            current_ratio > 2,
            pb_ratio > 1.5,
            graham_number is not None,
            graham_value is not None
        ])

        return {
            "Ticker": ticker,
            "Price": price_display,
            "Revenue": revenue_display,
            "Current Ratio": current_ratio_display,
            "P/B Ratio": pb_display,
            "EPS": eps_display,
            "Book Value": bvps_display,
            "Graham Number": graham_number_display,
            "Graham Value": graham_value_display,
            "Price vs Graham Value": price_vs_gv,
            "Passed Count": passed_count
        }
    except Exception as e:
        return None
