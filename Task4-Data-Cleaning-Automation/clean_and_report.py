"""
Automated Data Cleaning & Reporting Pipeline
--------------------------------------------
Reads every monthly sales export in an input folder, cleans the data, validates it,
and generates a report (Excel workbook + Markdown report with charts).

Usage:
    python clean_and_report.py                       # defaults: raw_data/ -> output/
    python clean_and_report.py --input raw_data --output output

To process a new month, drop its CSV into raw_data/ and run the script again.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # so ₹ prints correctly in Windows terminals

# ----------------------------------------------------------------------------- config
CANONICAL_COLUMNS = {  # normalised raw name -> clean column name
    "orderid": "Order ID", "orderdate": "Order Date", "customerid": "Customer ID",
    "customername": "Customer Name", "segment": "Segment", "city": "City", "state": "State",
    "region": "Region", "category": "Category", "subcategory": "Sub-Category",
    "productname": "Product Name", "product": "Product Name", "quantity": "Quantity",
    "unitprice": "Unit Price", "discount": "Discount", "sales": "Sales", "profit": "Profit",
}
REGION_MAP = {"n": "North", "s": "South", "e": "East", "w": "West"}
CATEGORY_MAP = {"technology": "Technology", "tech": "Technology", "furniture": "Furniture",
                "officesupplies": "Office Supplies"}
SEGMENT_MAP = {"consumer": "Consumer", "corporate": "Corporate", "corp": "Corporate", "homeoffice": "Home Office"}
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y"]
TEXT_COLS = ["Order ID", "Customer ID", "Customer Name", "Segment", "City", "State", "Region",
             "Category", "Sub-Category", "Product Name"]
NUM_COLS = ["Quantity", "Unit Price", "Discount", "Sales", "Profit"]

log = []  # data-quality log: one entry per cleaning step


def record(step, issue, rows, action):
    log.append({"Step": step, "Issue found": issue, "Rows affected": int(rows), "Action taken": action})
    print(f"  [{step}] {issue}: {int(rows)} rows -> {action}")


def key(text):
    """Lower-case and strip everything except letters, e.g. ' Office-supplies ' -> 'officesupplies'."""
    return re.sub(r"[^a-z]", "", str(text).lower())


# ----------------------------------------------------------------------------- 1. load
def load_raw_files(folder):
    files = sorted(Path(folder).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files found in {folder}/")
    frames = []
    for f in files:
        raw = pd.read_csv(f, dtype=str)                     # read everything as text first
        raw = raw.rename(columns=lambda c: CANONICAL_COLUMNS.get(key(c), c))
        raw["Source File"] = f.name
        frames.append(raw)
    df = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(files)} files, {len(df):,} rows")
    return df, [f.name for f in files]


# ----------------------------------------------------------------------------- 2. clean
def clean(df):
    n_start = len(df)

    # 2.1 blank rows
    blank = df[TEXT_COLS + NUM_COLS].isna().all(axis=1)
    record("Blank rows", "Completely empty rows", blank.sum(), "Removed")
    df = df[~blank].copy()

    # 2.2 whitespace + inconsistent text labels
    for c in TEXT_COLS:
        df[c] = df[c].str.strip()
    before = df[["Region", "Category", "Segment", "City"]].copy()
    df["Region"] = df["Region"].map(lambda v: REGION_MAP.get(key(v)[:1]) if pd.notna(v) else np.nan)
    df["Category"] = df["Category"].map(lambda v: CATEGORY_MAP.get(key(v), v))
    df["Segment"] = df["Segment"].map(lambda v: SEGMENT_MAP.get(key(v), v))
    df["City"] = df["City"].str.title()
    changed = (before.fillna("") != df[["Region", "Category", "Segment", "City"]].fillna("")).any(axis=1)
    record("Standardise text", "Inconsistent labels (e.g. 'S', 'Tech', 'Corp.', 'MUMBAI')", changed.sum(),
           "Mapped to standard values")

    # 2.3 dates in mixed formats
    parsed = pd.Series(pd.NaT, index=df.index)
    for fmt in DATE_FORMATS:
        parsed = parsed.fillna(pd.to_datetime(df["Order Date"], format=fmt, errors="coerce"))
    non_iso = ~df["Order Date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)
    record("Parse dates", "Dates not in YYYY-MM-DD format", (non_iso & parsed.notna()).sum(), "Converted to a proper date")
    record("Parse dates", "Impossible / unreadable dates (e.g. 31/02/2026)", parsed.isna().sum(), "Removed")
    df["Order Date"] = parsed
    df = df[df["Order Date"].notna()].copy()

    # 2.4 numbers stored as text ("₹1,234.50", "10%")
    texty = df["Sales"].str.contains(r"[₹,]", na=False) | df["Discount"].str.contains("%", na=False)
    pct = df["Discount"].str.contains("%", na=False)
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c].str.replace(r"[₹,%\s]", "", regex=True), errors="coerce")
    df.loc[pct, "Discount"] = df.loc[pct, "Discount"] / 100
    record("Fix numbers", "Numbers stored as text ('₹' symbols, commas, '%')", texty.sum(), "Converted to numeric")

    # 2.5 duplicates
    dup = df.drop(columns="Source File").duplicated()
    record("Duplicates", "Exact duplicate rows", dup.sum(), "Removed (kept first)")
    df = df[~dup].copy()
    dup_id = df["Order ID"].duplicated()
    record("Duplicates", "Repeated Order IDs", dup_id.sum(), "Removed (kept first)")
    df = df[~dup_id].copy()

    # 2.6 invalid values
    neg = df["Quantity"] < 0
    record("Invalid values", "Negative quantities (sign typo)", neg.sum(), "Converted to positive")
    df.loc[neg, "Quantity"] = df.loc[neg, "Quantity"].abs()
    median_price = df.groupby("Product Name")["Unit Price"].transform("median")
    outlier = (df["Unit Price"] / median_price) > 5
    record("Invalid values", "Unit price > 5x the product's median (extra zeros)", outlier.sum(),
           "Replaced with product median price")
    df.loc[outlier, "Unit Price"] = median_price[outlier]

    # 2.7 missing values: recover from other information wherever possible
    miss = df["Customer Name"].isna()
    name_lookup = df.dropna(subset=["Customer Name"]).groupby("Customer ID")["Customer Name"].agg(lambda s: s.mode()[0])
    df.loc[miss, "Customer Name"] = df.loc[miss, "Customer ID"].map(name_lookup).fillna("Unknown")
    record("Missing values", "Missing Customer Name", miss.sum(), "Filled from the same Customer ID's other orders")

    miss = df["Region"].isna()
    region_lookup = df.dropna(subset=["Region"]).groupby("State")["Region"].agg(lambda s: s.mode()[0])
    df.loc[miss, "Region"] = df.loc[miss, "State"].map(region_lookup)
    record("Missing values", "Missing Region", miss.sum(), "Filled from the State")

    gross = df["Quantity"] * df["Unit Price"]
    miss = df["Discount"].isna()
    df.loc[miss, "Discount"] = (1 - df["Sales"] / gross)[miss].round(2)
    record("Missing values", "Missing Discount", miss.sum(), "Calculated as 1 − Sales ÷ (Quantity × Price)")

    miss = df["Quantity"].isna()
    df.loc[miss, "Quantity"] = (df["Sales"] / (df["Unit Price"] * (1 - df["Discount"])))[miss].round()
    record("Missing values", "Missing Quantity", miss.sum(), "Calculated as Sales ÷ (Price × (1 − Discount))")

    miss = df["Sales"].isna()
    df.loc[miss, "Sales"] = (df["Quantity"] * df["Unit Price"] * (1 - df["Discount"]))[miss].round(2)
    record("Missing values", "Missing Sales", miss.sum(), "Calculated as Quantity × Price × (1 − Discount)")

    miss = df["Profit"].isna()
    margin = (df["Profit"] / df["Sales"]).groupby(df["Sub-Category"]).transform("median")
    df.loc[miss, "Profit"] = (df["Sales"] * margin)[miss].round(2)
    df["Profit Imputed"] = miss
    record("Missing values", "Missing Profit", miss.sum(), "Estimated from the sub-category's median margin (flagged)")

    unrecoverable = df[NUM_COLS + ["Region"]].isna().any(axis=1)
    record("Missing values", "Rows that could not be recovered", unrecoverable.sum(), "Removed")
    df = df[~unrecoverable].copy()

    df["Quantity"] = df["Quantity"].astype(int)
    df["Month"] = df["Order Date"].dt.to_period("M").astype(str)
    df = df.sort_values(["Order Date", "Order ID"]).reset_index(drop=True)
    print(f"Cleaning done: {n_start:,} raw rows -> {len(df):,} clean rows")
    return df


# ----------------------------------------------------------------------------- 3. validate
def validate(df):
    checks = {
        "No missing values in key columns": df[TEXT_COLS + NUM_COLS].notna().all().all(),
        "Order IDs are unique": df["Order ID"].is_unique,
        "Only valid regions": df["Region"].isin(REGION_MAP.values()).all(),
        "Only valid categories": df["Category"].isin(set(CATEGORY_MAP.values())).all(),
        "Only valid segments": df["Segment"].isin(set(SEGMENT_MAP.values())).all(),
        "Quantities are positive": (df["Quantity"] > 0).all(),
        "Discounts between 0 and 1": df["Discount"].between(0, 1).all(),
        "Sales = Qty × Price × (1 − Discount) (±2%)":
            (abs(df["Sales"] - df["Quantity"] * df["Unit Price"] * (1 - df["Discount"])) <= df["Sales"] * .02 + 1).mean() > .99,
    }
    print("Validation:")
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not all(checks.values()):
        raise ValueError("Validation failed - check the data quality log")
    return pd.DataFrame({"Check": list(checks), "Result": ["PASS" if v else "FAIL" for v in checks.values()]})


# ----------------------------------------------------------------------------- 4. report tables
def build_tables(df):
    kpi = {
        "Total Sales (₹)": df["Sales"].sum(), "Total Profit (₹)": df["Profit"].sum(),
        "Profit Margin (%)": df["Profit"].sum() / df["Sales"].sum() * 100, "Orders": df["Order ID"].nunique(),
        "Customers": df["Customer ID"].nunique(), "Avg Order Value (₹)": df["Sales"].mean(),
    }
    monthly = df.groupby("Month").agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"), Orders=("Order ID", "nunique"))
    monthly["Margin (%)"] = monthly["Profit"] / monthly["Sales"] * 100
    monthly["MoM Sales Change (%)"] = monthly["Sales"].pct_change() * 100

    def by(col):
        t = df.groupby(col).agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"), Orders=("Order ID", "nunique"))
        t["Margin (%)"] = t["Profit"] / t["Sales"] * 100
        t["Share of Sales (%)"] = t["Sales"] / t["Sales"].sum() * 100
        return t.sort_values("Sales", ascending=False)

    top = df.groupby(["Product Name", "Category"]).agg(Sales=("Sales", "sum"), Units=("Quantity", "sum")) \
            .sort_values("Sales", ascending=False).head(10).reset_index()
    return {"kpi": kpi, "monthly": monthly, "region": by("Region"), "category": by("Category"),
            "subcat": by("Sub-Category"), "top": top}


def observations(t):
    m, sub = t["monthly"], t["subcat"]
    last, prev = m.index[-1], m.index[-2]
    obs = [
        f"Best month: **{m['Sales'].idxmax()}** with ₹{m['Sales'].max():,.0f} in sales.",
        f"Latest month ({last}) sales were **₹{m.loc[last, 'Sales']:,.0f}**, "
        f"{'up' if m.loc[last, 'MoM Sales Change (%)'] >= 0 else 'down'} "
        f"**{abs(m.loc[last, 'MoM Sales Change (%)']):.1f}%** from {prev}.",
        f"Top region: **{t['region'].index[0]}** ({t['region']['Share of Sales (%)'].iloc[0]:.1f}% of sales). "
        f"Top category: **{t['category'].index[0]}** ({t['category']['Share of Sales (%)'].iloc[0]:.1f}%).",
        f"Best product: **{t['top'].loc[0, 'Product Name']}** (₹{t['top'].loc[0, 'Sales']:,.0f}).",
    ]
    losses = sub[sub["Profit"] < 0]
    if len(losses):
        obs.append("⚠️ Loss-making sub-categories: " + ", ".join(f"**{i}** (₹{p:,.0f})" for i, p in losses["Profit"].items()) + ".")
    return obs


# ----------------------------------------------------------------------------- 5. charts
def make_charts(t, dq, folder):
    folder.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10})

    m = t["monthly"]
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.bar(m.index, m["Sales"] / 1e5, color="#1F3A93", label="Sales")
    ax.plot(m.index, m["Profit"] / 1e5, color="#2E9E6B", marker="o", lw=2.5, label="Profit")
    for i, v in enumerate(m["Sales"] / 1e5):
        ax.text(i, v + .2, f"{v:.1f}", ha="center", fontsize=8)
    ax.set_ylabel("₹ lakh"); ax.set_title("Monthly sales and profit (₹ lakh)", fontweight="bold"); ax.legend()
    fig.savefig(folder / "monthly_sales.png", dpi=110, bbox_inches="tight"); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, name, color in [(axes[0], "category", "#E07B39"), (axes[1], "region", "#1F3A93")]:
        d = t[name]
        ax.barh(d.index, d["Sales"] / 1e5, color=color); ax.invert_yaxis()
        for i, (s, mg) in enumerate(zip(d["Sales"] / 1e5, d["Margin (%)"])):
            ax.text(s, i, f"  ₹{s:.1f}L | {mg:.0f}% margin", va="center", fontsize=8)
        ax.set_title(f"Sales by {name}", fontweight="bold"); ax.set_xlim(0, d["Sales"].max() / 1e5 * 1.45)
    fig.tight_layout(); fig.savefig(folder / "category_region.png", dpi=110, bbox_inches="tight"); plt.close(fig)

    d = dq[dq["Rows affected"] > 0].copy()
    d["Label"] = d["Issue found"].str.replace(r" \(.*\)", "", regex=True)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.barh(d["Label"], d["Rows affected"], color="#C0392B"); ax.invert_yaxis()
    for i, v in enumerate(d["Rows affected"]):
        ax.text(v, i, f" {v}", va="center", fontsize=8)
    ax.set_title("Data quality issues fixed automatically", fontweight="bold"); ax.set_xlabel("Rows")
    fig.savefig(folder / "data_quality.png", dpi=110, bbox_inches="tight"); plt.close(fig)


# ----------------------------------------------------------------------------- 6. outputs
def write_excel(df, t, dq, checks, run_info, path):
    from openpyxl.styles import Alignment, Font, PatternFill
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        summary = pd.DataFrame(list(run_info.items()) + [("", "")] + [(k, round(v, 2)) for k, v in t["kpi"].items()],
                               columns=["Item", "Value"])
        sheets = {"Summary": summary, "Monthly": t["monthly"].round(2).reset_index(),
                  "By Region": t["region"].round(2).reset_index(), "By Category": t["category"].round(2).reset_index(),
                  "By Sub-Category": t["subcat"].round(2).reset_index(), "Top 10 Products": t["top"].round(2),
                  "Data Quality Log": dq, "Validation": checks,
                  "Clean Data": df.assign(**{"Order Date": df["Order Date"].dt.date})}
        for name, data in sheets.items():
            data.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            for cell in ws[1]:
                cell.font = Font(name="Arial", bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1F3A93")
                cell.alignment = Alignment(horizontal="center", wrap_text=True)
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 60)
                for c in col[1:]:
                    c.font = Font(name="Arial", size=10)
                    if isinstance(c.value, float):
                        c.number_format = "#,##0.00"
            ws.freeze_panes = "A2"


def md_table(frame, money=(), pct=()):
    frame = frame.copy()
    for c in frame.columns:
        if c in money:
            frame[c] = frame[c].map(lambda v: f"₹{v:,.0f}")
        elif c in pct:
            frame[c] = frame[c].map(lambda v: "–" if pd.isna(v) else f"{v:+.1f}%" if "Change" in c else f"{v:.1f}%")
    rows = ["| " + " | ".join(map(str, frame.columns)) + " |", "|" + "---|" * len(frame.columns)]
    rows += ["| " + " | ".join(map(str, r)) + " |" for r in frame.itertuples(index=False)]
    return "\n".join(rows)


def write_markdown(t, dq, checks, run_info, raw_sample, clean_sample, path):
    k = t["kpi"]
    pct_cols = ("Margin (%)", "Share of Sales (%)", "MoM Sales Change (%)")
    text = f"""# Automated Sales Report

*Generated automatically by `clean_and_report.py` on {run_info['Generated on']}*

**Files processed:** {run_info['Files processed']} ({run_info['Period']}) · **Raw rows:** {run_info['Raw rows']} · **Clean rows:** {run_info['Clean rows']}

## Key metrics
| Total Sales | Total Profit | Margin | Orders | Customers | Avg Order Value |
|---|---|---|---|---|---|
| ₹{k['Total Sales (₹)']:,.0f} | ₹{k['Total Profit (₹)']:,.0f} | {k['Profit Margin (%)']:.1f}% | {k['Orders']:,} | {k['Customers']:,} | ₹{k['Avg Order Value (₹)']:,.0f} |

## Highlights
""" + "\n".join(f"- {o}" for o in observations(t)) + f"""

## Monthly performance
![Monthly sales](monthly_sales.png)

{md_table(t['monthly'].reset_index(), money=('Sales', 'Profit'), pct=pct_cols)}

## Category and region
![Category and region](category_region.png)

{md_table(t['category'].reset_index(), money=('Sales', 'Profit'), pct=pct_cols)}

{md_table(t['region'].reset_index(), money=('Sales', 'Profit'), pct=pct_cols)}

## Top 10 products
{md_table(t['top'], money=('Sales',))}

---

## Data quality report
![Data quality](data_quality.png)

{md_table(dq)}

### Before → after (sample rows)
**Raw**

{md_table(raw_sample)}

**Cleaned**

{md_table(clean_sample)}

### Validation checks
{md_table(checks)}
"""
    Path(path).write_text(text, encoding="utf-8")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Clean monthly sales exports and generate a report.")
    ap.add_argument("--input", default="raw_data", help="folder containing raw CSV exports")
    ap.add_argument("--output", default="output", help="folder for cleaned data and reports")
    args = ap.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)

    raw, files = load_raw_files(args.input)
    print("Cleaning:")
    clean_df = clean(raw.copy())
    checks = validate(clean_df)
    dq = pd.DataFrame(log)
    tables = build_tables(clean_df)

    run_info = {"Generated on": datetime.now().strftime("%d %b %Y, %H:%M"), "Files processed": len(files),
                "Period": f"{clean_df['Month'].min()} to {clean_df['Month'].max()}",
                "Raw rows": f"{len(raw):,}", "Clean rows": f"{len(clean_df):,}",
                "Rows removed": f"{len(raw) - len(clean_df):,}"}

    # before/after sample: rows that needed several fixes
    sample_cols = ["Order ID", "Order Date", "Region", "Category", "Segment", "Discount", "Sales"]
    messy_ids = raw[raw["Sales"].str.contains("₹", na=False) & raw["Discount"].str.contains("%", na=False)
                    & ~raw["Region"].isin(REGION_MAP.values())]["Order ID"].str.strip().drop_duplicates().head(4)
    raw_sample = raw[raw["Order ID"].str.strip().isin(messy_ids)].drop_duplicates("Order ID")[sample_cols].fillna("(missing)").sort_values("Order ID")
    clean_sample = clean_df[clean_df["Order ID"].isin(messy_ids)][sample_cols].assign(
        **{"Order Date": lambda d: d["Order Date"].dt.date, "Sales": lambda d: d["Sales"].round(2)}).sort_values("Order ID")

    clean_df.to_csv(out / "clean_sales_data.csv", index=False)
    make_charts(tables, dq, out)
    write_excel(clean_df, tables, dq, checks, run_info, out / "sales_report.xlsx")
    write_markdown(tables, dq, checks, run_info, raw_sample, clean_sample, out / "REPORT.md")
    print(f"Done. Outputs saved in {out}/: clean_sales_data.csv, sales_report.xlsx, REPORT.md + 3 charts")


if __name__ == "__main__":
    main()
