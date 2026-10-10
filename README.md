# UK Public Spend Explorer

A static website for exploring where UK public money goes, year by year, with automatic checks that point at unusual figures.

**All data comes from official files published on GOV.UK:**

- HM Treasury: <https://www.gov.uk/government/collections/national-statistics-release> (Public Spending Statistics) and <https://www.gov.uk/government/collections/public-expenditure-statistical-analyses-pesa> (PESA)
- HMRC: [tax receipts and NICs](https://www.gov.uk/government/statistics/hmrc-tax-and-nics-receipts-for-the-uk) (monthly from April 2017) and [Measuring tax gaps](https://www.gov.uk/government/collections/measuring-tax-gaps)
- ONS: [Public sector finances](https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance/datasets/publicsectorfinances) (monthly spending, receipts, borrowing and debt since April 1997)

The exact files are listed in [`pipeline/sources.json`](pipeline/sources.json) and on the site's *Method & sources* page.

## What it shows

| View | Source tables |
|---|---|
| Totals since 1985-86 (cash, real terms, % of GDP) | PSS Table 4.1 |
| Ten functions, 2003-04 → 2025-26 (cash, real, % of GDP) | PSS Tables 4.2–4.4 |
| ~1,600 departmental spending lines, 2021-22 → 2025-26 | PSS database 2026 |
| Countries and regions, total and per head | PSS Chapter 9 |
| Revisions to past years | PSS databases 2024, 2025, 2026 compared |
| Table cross-checks | Tables 1.1, 4.1–4.3, 9.1a |
| Monthly and annual tax receipts by tax; benefits HMRC pays | HMRC receipts statistics table |
| Tax gap (£bn and %) by tax, behaviour and customer group; revisions between editions | HMRC Measuring tax gaps tables |

| Monthly spending, receipts, borrowing, debt interest, net debt | ONS Public sector finances (22 series, selected by CDID) |
| Agreement between ONS and Treasury totals | ONS monthly TME summed per financial year vs PESA Table 4.1 |

**Monthly data:** the Treasury's tables are annual, so monthly figures come from the ONS (public finances) and HMRC (tax receipts). ONS figures are not seasonally adjusted, and the latest months are provisional. ONS publishes borrowing as a negative number; the site shows it as positive.

## Unusual-figure tests

Screening tests, not accusations. Anything flagged is "worth a look"; most flags have innocent explanations (a new scheme, a one-off settlement, accounting valuation, a department reorganisation). The data are annual departmental totals, so they cannot reveal individual fraudulent payments.

1. Unusual year-on-year jumps (robust median/MAD z-score against comparable lines)
2. Figures restated between July releases (offsetting re-allocations and re-coded lines are down-weighted)
3. Lines that appear from, or vanish to, nothing
4. Net figures that flip between spend and income
5. Outturn identical to the £thousand in consecutive years
6. Exactly round outturn
7. Sustained rapid growth
8. Unusual function-level moves
9. Benford first-digit conformity (weak, flagged as indicative)
10. Share of spend in catch-all categories ("other", "unallocated", "provisions")
11. Cross-table integrity checks (do totals add up and agree between tables?), including HMRC's receipts and tax gap tables
12. Unusual months in HMRC tax receipts (year-on-year, scored per tax; a shock is reported once, not again as next year's rebound)
13. Unusual months in ONS public finance series since 2015 (same method; net borrowing and net investment excluded because they cross zero)
14. ONS identities (spending − receipts = borrowing; central government current + capital = total) and ONS vs Treasury annual totals
15. Tax gap estimates that were later revised (HMRC's first estimates of recent years have been revised up in each of the last six editions)

All thresholds are in [`pipeline/analysis.py`](pipeline/analysis.py) (`PARAMS`) and are shown on the site.

## Run it

```bash
pip install openpyxl                      # only dependency
python3 pipeline/build.py                 # downloads the workbooks into ./raw and writes site/data/*.json
python3 -m unittest discover -s pipeline/tests
python3 -m http.server -d site 8000       # then open http://localhost:8000
```

`site/` is plain HTML/CSS/JS with no build step or external requests, so it can be hosted anywhere (e.g. GitHub Pages: publish the `site` folder). To pick up a new Treasury release, add its file URLs to `pipeline/sources.json` and re-run the build.
