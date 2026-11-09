"""
Creates realistic *messy* monthly export files (Jan–Oct 2026) from the clean retail dataset,
so the cleaning pipeline has real-world problems to fix. Run once: python generate_raw_data.py
"""
import numpy as np, pandas as pd
from pathlib import Path

rng = np.random.default_rng(7)
df = pd.read_csv("../retail_sales_data.csv", parse_dates=["Order Date"])
df = df[df["Order Date"] >= "2026-01-01"].copy()
out = Path("raw_data"); out.mkdir(exist_ok=True)

region_variants = {"North": ["North", "north", "NORTH ", " N"], "South": ["South", "south ", "S"],
                   "East": ["East", "east", "E "], "West": ["West", "WEST", "w"]}
category_variants = {"Technology": ["Technology", "Tech", "technology "], "Furniture": ["Furniture", "furniture", "FURNITURE"],
                     "Office Supplies": ["Office Supplies", "Office supplies", "office-supplies", "OfficeSupplies"]}
segment_variants = {"Consumer": ["Consumer", "consumer"], "Corporate": ["Corporate", "Corp.", "corporate"],
                    "Home Office": ["Home Office", "home office", "HomeOffice"]}
column_styles = [  # different exports use different column naming conventions
    None,
    {"Order Date": "order_date", "Customer ID": "customer_id", "Sub-Category": "sub_category", "Unit Price": "unit_price"},
    {"Order Date": "OrderDate", "Customer Name": "CustomerName", "Sub-Category": "Sub Category", "Product Name": "Product"},
]

def mess(row):
    r = row.copy()
    p = rng.random
    if p() < .30: r["Region"] = rng.choice(region_variants[r["Region"]])
    if p() < .30: r["Category"] = rng.choice(category_variants[r["Category"]])
    if p() < .25: r["Segment"] = rng.choice(segment_variants[r["Segment"]])
    if p() < .15: r["City"] = rng.choice([r["City"].upper(), r["City"].lower(), f"  {r['City']} "])
    d = r["Order Date"]
    r["Order Date"] = rng.choice([d.strftime("%Y-%m-%d"), d.strftime("%d/%m/%Y"), d.strftime("%b %d, %Y")], p=[.6, .3, .1])
    if p() < .35: r["Sales"] = f"₹{r['Sales']:,.2f}"
    if p() < .30: r["Discount"] = f"{r['Discount']*100:.0f}%"
    if p() < .05: r["Order ID"] = f" {r['Order ID']} "
    # missing values
    if p() < .03: r["Customer Name"] = np.nan
    if p() < .03: r["Region"] = np.nan
    if p() < .02: r["Quantity"] = np.nan
    if p() < .02: r["Sales"] = np.nan
    if p() < .02: r["Profit"] = np.nan
    if p() < .02: r["Discount"] = np.nan
    # invalid values / typos
    if p() < .01: r["Quantity"] = -abs(r["Quantity"]) if pd.notna(r["Quantity"]) else r["Quantity"]
    if p() < .008: r["Unit Price"] = r["Unit Price"] * 100          # extra zeros typed
    if p() < .004: r["Order Date"] = "31/02/2026"                     # impossible date
    return r

for month, g in df.groupby(df["Order Date"].dt.to_period("M")):
    messy = pd.DataFrame([mess(r) for _, r in g.iterrows()])
    dups = messy.sample(frac=.03, random_state=int(month.month))      # ~3% duplicated rows
    messy = pd.concat([messy, dups]).sample(frac=1, random_state=1)
    blank = pd.DataFrame([[np.nan] * messy.shape[1]], columns=messy.columns)
    messy = pd.concat([messy, blank]).reset_index(drop=True)          # stray blank row
    style = column_styles[month.month % 3]
    if style: messy = messy.rename(columns=style)
    messy.to_csv(out / f"sales_export_{month.strftime('%Y_%m')}.csv", index=False)
    print(f"{month}: {len(messy)} rows")
