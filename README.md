# UK Public Spend Explorer

A static website for exploring where UK public money goes, year by year, with automatic checks that point at unusual figures.

**All data comes from official files published on GOV.UK:**

- HM Treasury: <https://www.gov.uk/government/collections/national-statistics-release> (Public Spending Statistics) and <https://www.gov.uk/government/collections/public-expenditure-statistical-analyses-pesa> (PESA)
- HMRC: [tax receipts and NICs](https://www.gov.uk/government/statistics/hmrc-tax-and-nics-receipts-for-the-uk) (monthly from April 2017) and [Measuring tax gaps](https://www.gov.uk/government/collections/measuring-tax-gaps)
- DWP: [Fraud and error in the benefit system](https://www.gov.uk/government/collections/fraud-and-error-in-the-benefit-system) (annual estimates for Great Britain; the FYE 2024, 2025 and 2026 releases)
- Cabinet Office: [Find a Tender](https://www.find-tender.service.gov.uk/) award notices via its OCDS API (`pipeline/fetch_find_tender.py`: about 20 requests fetch two months; framework call-offs and exempt contracts are kept apart from true direct awards, whose stated reason is kept)
- Cabinet Office: [Contracts Finder](https://www.contractsfinder.service.gov.uk/) award notices, via its OCDS API (`pipeline/fetch_contracts.py`, polite and resumable; keeps organisation-level fields only and discards named contact people)
- MHCLG: [Local authority revenue expenditure and financing, England: revenue outturn](https://www.gov.uk/government/collections/local-authority-revenue-expenditure-and-financing) (time series CSV, every council, 2017-18 onward) with ONS [mid-year population estimates](https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates) by local authority and single year of age
- Defra: [local authority collected waste management](https://www.gov.uk/government/statistics/local-authority-collected-waste-management-annual-results); DfT: [road condition](https://www.gov.uk/government/statistical-data-sets/road-condition-statistics-data-tables-rdc) and [road length](https://www.gov.uk/government/statistical-data-sets/road-length-statistics-rdl) statistics; MHCLG: [capital outturn](https://www.gov.uk/government/statistics/local-authority-capital-expenditure-and-receipts-in-england-final-outturn-time-series) and [English indices of deprivation 2025](https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025)
- MHCLG: [planning application statistics](https://www.gov.uk/government/collections/planning-applications-statistics) (speed of decisions by authority) and [statutory homelessness](https://www.gov.uk/government/statistical-data-sets/live-tables-on-homelessness) (detailed local authority tables); Ofsted: [local authority inspection outcomes](https://www.gov.uk/government/collections/childrens-social-care-statistics)
- Debt Management Office: [gilt holdings by type of holder](https://www.dmo.gov.uk/data/gilt-market/) (quarterly since 1987) and [average gilt issuance yields](https://www.dmo.gov.uk/data/gilt-market/average-gilt-issuance-yields/) (since 1998-99); file links are discovered from the DMO pages because the addresses change on each update
- Bank of England: [daily gilt yields](https://www.bankofengland.co.uk/boeapps/database/) (5, 10 and 20 year nominal par yields, 5 year inflation-linked)
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
| Government contracts (Contracts Finder and Find a Tender): awards by month, procedure, sector, buyer and supplier; red flags (direct awards, late notices, estimate gaps, repeat awards, concentration, pile-ups below round values) | Contracts Finder award notices (last 60 days by default, extendable; Find a Tender takes under a minute, Contracts Finder is rate-limited to about 12 requests per 5 minutes) |
| Borrowing and debt: borrowing since 1946, net debt, who holds gilts, gilt yields, the price paid on new gilts, interest as a share of receipts | ONS annual and monthly series, DMO, Bank of England |
| Local councils (England): spending by service, per resident / child / person aged 65+, peer comparison, reserves, schools deficits, interest, league tables, council profiles | MHCLG revenue outturn, ONS population |
| What it buys: council waste and road spending against recycling rates and road condition, before and after allowing for deprivation | MHCLG, Defra, DfT, IoD2025 (`pipeline/outcomes.py`) |
| What it buys (council by council): waste, roads, planning decisions, homelessness, children's social care and Ofsted against spending, before and after allowing for deprivation and demand | MHCLG, Defra, DfT, DfE, Ofsted, IoD2025 (`pipeline/outcomes.py`, `outcomes2.py`) |
| What it buys (national): school results and NHS waiting lists against real spending over time | DfE explore-education-statistics API, NHS England RTT time series (found through its public REST API), HM Treasury |
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
17. Unusual months in government borrowing (year-on-year, in £ because borrowing crosses zero), and checks that gilt holders add up to the total and that borrowing equals spending minus receipts
18. Tax gap estimates that were later revised (HMRC's first estimates of recent years have been revised up in each of the last six editions)
19. Local councils: spending far from similar councils, sudden changes, thin reserves, schools (DSG) deficits, heavy interest, loss-making investment property, missing returns; checks that council returns add up to the published class totals and the 13 service lines to total service spending (`pipeline/councils.py`)

All thresholds are in [`pipeline/analysis.py`](pipeline/analysis.py) (`PARAMS`) and are shown on the site.

## Not included yet

**OBR forecasts vs outturn** (the Historical Official Forecasts Database). The OBR's download links redirect automated requests to a "No Access" page, so the pipeline cannot fetch it. If you download the spreadsheet yourself from <https://obr.uk/data/> and add it to the repo, a parser can be written against the real file.

## Design

- **Typeface:** [Inter](https://rsms.me/inter/) (variable weight, SIL Open Font License), self-hosted in `site/fonts/` so the site makes no third-party requests, with a system-font fallback. Numbers use tabular figures so columns line up.
- **Colour:** deep navy chrome, cool neutral surfaces and one blue accent, in light and dark mode (follows your device, with a toggle in the top bar that is remembered in your browser). Chart series use an eight-hue palette (blue, amber, teal, violet, rose, orange, cyan, green) in an order checked for colour-blind separation and 3:1 contrast on the card surface; every text and background pairing meets WCAG AA.
- **Layout:** a grouped sidebar on desktop that becomes a scrolling bar on small screens; summary tiles; cards for each chart or table, each with a "view as table" fallback.
- Everything is defined as CSS variables at the top of `site/style.css`.

## Run it

```bash
pip install openpyxl xlrd                 # openpyxl reads .xlsx; xlrd reads the DMO's older .xls files
python3 pipeline/fetch_contracts.py       # Contracts Finder award notices into ./raw, one day at a time: the last 60 days by default (about 45 minutes,
                                          # the API allows ~12 requests per 5 minutes). Incremental: later runs fetch only days not yet seen.
                                          # Extend further back with e.g. --from 2026-04-01 (roughly 15 minutes per month of history)
python3 pipeline/build.py                 # downloads the workbooks into ./raw and writes site/data/*.json
                                          # (add --skip-contracts while the Contracts Finder download is still running)
python3 -m unittest discover -s pipeline/tests
python3 -m http.server -d site 8000       # then open http://localhost:8000
```

`site/` is plain HTML/CSS/JS with no build step or external requests, so it can be hosted anywhere (e.g. GitHub Pages: publish the `site` folder). To pick up a new Treasury release, add its file URLs to `pipeline/sources.json` and re-run the build.

## Automatic monthly refresh

`.github/workflows/refresh-data.yml` runs on the 6th of each month (and on demand from the repository's Actions tab): it runs the tests, downloads the newest official files, rebuilds `site/data` and opens a pull request. Nothing goes live until you merge it and redeploy.

- Files that change during the year are found automatically: NHS England waiting times (through its public REST API), GOV.UK releases (through the GOV.UK content API: HMRC receipts, MHCLG revenue and capital outturn, planning, homelessness, Defra waste, DfT roads, Ofsted), the DMO and Bank of England pages, the ONS public finances file, and the Department for Education data sets.
- Contracts Finder is fetched day by day with a cache between runs, so each month only the new days are downloaded.
- Files published once a year are **not** refreshed automatically because they have a new file name and page each time: the Treasury Public Spending Statistics (July), HMRC tax gap (June), DWP fraud and error (May), the English indices of deprivation and the ONS population estimates. Update their entries in `pipeline/sources.json` when they appear.
- One-time setup: in the repository on GitHub, open Settings > Actions > General and tick "Allow GitHub Actions to create and approve pull requests".

## Deploy on Cloudflare Workers

`wrangler.jsonc` serves `site/` as static assets (no Worker script needed):

```bash
npx wrangler login      # first time only
npx wrangler deploy     # publishes to https://uk-public-spend.<your-subdomain>.workers.dev
npx wrangler dev        # local preview
```

The data in `site/data/` is committed, so it deploys as-is. To refresh it, run `python3 pipeline/build.py` first (Treasury and HMRC publish each release at a new file URL, so update `pipeline/sources.json` when a new release appears; the ONS URL is stable).
