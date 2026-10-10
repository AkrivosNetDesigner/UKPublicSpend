# UK Public Spend Explorer

A static website for exploring where UK public money goes, year by year, with automatic checks that point at unusual figures.

**All data comes from official files published on GOV.UK:**

- HM Treasury: <https://www.gov.uk/government/collections/national-statistics-release> (Public Spending Statistics) and <https://www.gov.uk/government/collections/public-expenditure-statistical-analyses-pesa> (PESA)
- HMRC: [tax receipts and NICs](https://www.gov.uk/government/statistics/hmrc-tax-and-nics-receipts-for-the-uk) (monthly from April 2017) and [Measuring tax gaps](https://www.gov.uk/government/collections/measuring-tax-gaps)
- DWP: [Fraud and error in the benefit system](https://www.gov.uk/government/collections/fraud-and-error-in-the-benefit-system) (annual estimates for Great Britain; the FYE 2024, 2025 and 2026 releases)
- Cabinet Office: [Contracts Finder](https://www.contractsfinder.service.gov.uk/) award notices, via its OCDS API (`pipeline/fetch_contracts.py`, polite and resumable; keeps organisation-level fields only and discards named contact people)
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
| Benefit fraud and error: overpaid and underpaid by benefit, by type and by reason, how recently each was measured, recoveries, restatements | DWP fraud and error data tables (3 releases) |
| Government contracts: awards by month, procedure, sector, buyer and supplier; red flags (direct awards, late notices, estimate gaps, repeat awards, concentration, pile-ups below round values) | Contracts Finder award notices (last 60 days by default, extendable) |
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
15. DWP benefit screens: high overpayment rates, benefits whose rate was last measured more than three years ago (or never), and estimates restated between releases; DWP internal checks (components, percentages, recoveries, benefits sum to the total, reasons sum to each benefit) and a scope comparison with the Treasury's benefit spending
16. Contracts: large awards without competition, notices published long after the award, awards far from the advertised value, very long contracts, repeat awards to one supplier, buyers dominated by one supplier, buyers that rarely state their procedure, and pile-ups of awards just below round values
17. Tax gap estimates that were later revised (HMRC's first estimates of recent years have been revised up in each of the last six editions)

All thresholds are in [`pipeline/analysis.py`](pipeline/analysis.py) (`PARAMS`) and are shown on the site.

## Not included yet

**OBR forecasts vs outturn** (the Historical Official Forecasts Database). The OBR's download links redirect automated requests to a "No Access" page, so the pipeline cannot fetch it. If you download the spreadsheet yourself from <https://obr.uk/data/> and add it to the repo, a parser can be written against the real file.

## Colour scheme

The five brand colours (coral `#F78888`, yellow `#F3D250`, grey `#ECECEC`, sky `#90CCF4`, blue `#5DA2D5`) are used as-is for large surfaces: the header band, KPI tiles, notices and highlights. Pastels are too light for thin chart lines and small text, so chart series use deeper steps of the same hues (plus violet, green, orange and magenta). That eight-colour set was checked with a colour-blind-separation and contrast validator in both light and dark mode, and all text pairings meet WCAG AA. Everything is defined as CSS variables at the top of `site/style.css`.

## Run it

```bash
pip install openpyxl                      # only dependency
python3 pipeline/fetch_contracts.py       # Contracts Finder award notices into ./raw, one day at a time: the last 60 days by default (about 45 minutes,
                                          # the API allows ~12 requests per 5 minutes). Incremental: later runs fetch only days not yet seen.
                                          # Extend further back with e.g. --from 2026-04-01 (roughly 15 minutes per month of history)
python3 pipeline/build.py                 # downloads the workbooks into ./raw and writes site/data/*.json
python3 -m unittest discover -s pipeline/tests
python3 -m http.server -d site 8000       # then open http://localhost:8000
```

`site/` is plain HTML/CSS/JS with no build step or external requests, so it can be hosted anywhere (e.g. GitHub Pages: publish the `site` folder). To pick up a new Treasury release, add its file URLs to `pipeline/sources.json` and re-run the build.

## Deploy on Cloudflare Workers

`wrangler.jsonc` serves `site/` as static assets (no Worker script needed):

```bash
npx wrangler login      # first time only
npx wrangler deploy     # publishes to https://uk-public-spend.<your-subdomain>.workers.dev
npx wrangler dev        # local preview
```

The data in `site/data/` is committed, so it deploys as-is. To refresh it, run `python3 pipeline/build.py` first (Treasury and HMRC publish each release at a new file URL, so update `pipeline/sources.json` when a new release appears; the ONS URL is stable).
