# Task 4 – Data Cleaning & Reporting Automation

A reusable Python pipeline that takes **messy monthly sales exports**, cleans and validates them automatically, and **generates a business report**, all with a single command.

📄 **[View the generated report](output/REPORT.md)**

## The problem
The raw data in `raw_data/` (10 monthly exports, Jan–Oct 2026, **1,622 rows**) has typical real-world issues:
- Column names that differ between files (`Order Date` / `order_date` / `OrderDate`)
- Dates in three different formats, plus impossible dates like `31/02/2026`
- Numbers stored as text (`₹8,528.40`, `10%`)
- Inconsistent labels (`S`, `north`, `Tech`, `Corp.`, `office-supplies`, `MUMBAI`)
- Missing values, duplicate rows, negative quantities and prices with extra zeros

## What the pipeline does
| Stage | What happens |
|---|---|
| **Load** | Reads every CSV in the folder and maps different column names to one standard schema |
| **Clean** | Removes blank rows, standardises text labels, parses all date formats, converts text to numbers |
| **De-duplicate** | Removes exact duplicate rows and repeated Order IDs |
| **Fix invalid values** | Corrects negative quantities and replaces prices more than 5× the product's median |
| **Handle missing values** | Recovers them from other columns wherever possible (e.g. Region from State, Sales from Qty × Price × (1 − Discount)), estimates missing Profit and flags it, and removes rows only if nothing can be recovered |
| **Validate** | 8 automatic checks (unique IDs, valid categories, Sales = Qty × Price × (1 − Discount), etc.); the run stops if any check fails |
| **Report** | Generates KPIs, monthly trends, category/region breakdowns, top products, auto-written highlights and a full data-quality log |

## Results
- **1,622 raw rows → 1,561 clean rows**. Only blank rows, duplicates and 3 rows with impossible dates were removed.
- **Over 2,700 individual fixes** applied automatically (see the data-quality log in the report).
- All 8 validation checks **pass**.

## Outputs (`output/`)
| File | Contents |
|---|---|
| `REPORT.md` | Readable report with KPIs, highlights, charts, data-quality log and before → after examples |
| `sales_report.xlsx` | Excel workbook: Summary, Monthly, By Region/Category/Sub-Category, Top 10 Products, Data Quality Log, Validation, Clean Data |
| `clean_sales_data.csv` | The cleaned dataset |
| `*.png` | Charts used in the report |

## How to run
```bash
pip install pandas numpy matplotlib openpyxl
python clean_and_report.py                          # raw_data/ -> output/
python clean_and_report.py --input raw_data --output output
```
**Automation:** to process a new month, drop its CSV into `raw_data/` and run the script again. All outputs regenerate in seconds.

`generate_raw_data.py` shows how the messy exports were created from the base dataset (`../retail_sales_data.csv`) by injecting realistic data errors, so the pipeline can be tested on known problems.
