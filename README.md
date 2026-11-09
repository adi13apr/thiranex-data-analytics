# Data Analytics Internship Projects – Thiranex EduTech

Projects completed during my remote **Data Analytics Internship at Thiranex EduTech LLP** (Nov–Dec 2026).
All three tasks use the same retail sales dataset, so together they tell one end-to-end story:
**describe the business → understand the customers → forecast the future.**

| # | Project | Tools | Status |
|---|---------|-------|--------|
| 1 | [Sales & Revenue Analysis Dashboard](Task1-Sales-Dashboard) | Excel | ✅ Done |
| 2 | Customer Segmentation (RFM + K-Means) | Python, pandas, scikit-learn | 🔄 In progress |
| 3 | Predictive Analytics – Sales Forecasting | Python, statsmodels | 🔄 In progress |

## Dataset
`retail_sales_data.csv` has **5,947 order lines** from **662 customers**, covering Jan 2023 – Oct 2026 (16 columns: order, customer, segment, city/state/region, category, sub-category, product, quantity, unit price, discount, sales, profit).
It is a synthetic dataset modelled on the classic *Superstore* structure and adapted to Indian regions, with realistic growth, festive seasonality and discount effects.

---

## Task 1 – Sales & Revenue Analysis Dashboard

An interactive Excel dashboard for tracking KPIs and finding what drives revenue and profit.

![Dashboard](Task1-Sales-Dashboard/dashboard_all.png)

**Features**
- Dropdown filters for **Region, Category and Year** that update every KPI and chart
- KPI cards: Total Sales, Total Profit, Profit Margin, Orders, Average Order Value, Units Sold
- Charts: monthly revenue & profit trend, sales/profit by category and region, top 10 products, profit by sub-category

**How it works**
- KPIs are built with `SUMIFS` / `COUNTIFS`; choosing "All" passes a `*` wildcard as the criteria
- The Year filter is converted into a start/end date range
- The Top 10 ranking is dynamic, using `LARGE` + `INDEX/MATCH` on a helper table

**Key insights**
- **₹3.61 Cr sales and ₹79.3 L profit** overall, a **22.0% margin**
- Sales grew **19.9% in 2024** and **8.0% in 2025**
- **Oct–Nov (festive season) contributes 24.6%** of yearly sales, versus 16.7% if sales were spread evenly
- **Technology** is the largest category (₹1.54 Cr); **Office Supplies** has the best margin (29.1%)
- **Tables is the only loss-making sub-category** (₹-1.92 L) because of heavy discounting
- Orders with **no discount earn a 30.3% margin**, while orders discounted **30% or more lose 26.7%**
- **West** leads on sales; **East** has the lowest margin (15.8%) due to higher discounts

**Recommendations:** stock up and plan campaigns ahead of Oct–Nov, review pricing on Tables and Bookcases, and cap discounts, especially in the East region.

![Filtered view](Task1-Sales-Dashboard/dashboard_filtered.png)

---

## Author
**Aditya Chauhan** – B.Tech CSE, IIIT Kota
