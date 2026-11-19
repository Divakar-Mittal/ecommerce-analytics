"""
Interactive sales dashboard.

Run:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import cohort_matrix  # noqa: E402

DB_PATH = ROOT / "data" / "processed" / "warehouse.db"

st.set_page_config(page_title="Retail Analytics Dashboard", page_icon="📊", layout="wide")


@st.cache_data
def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(DB_PATH) as con:
        lines = pd.read_sql("SELECT * FROM v_order_lines", con, parse_dates=["order_date"])
        rfm = pd.read_sql((ROOT / "sql" / "04_rfm_segments.sql").read_text(), con)
    return lines, rfm


if not DB_PATH.exists():
    st.error("Warehouse not found. Run `python run_pipeline.py` first.")
    st.stop()

lines, rfm = load()

# ---------------------------------------------------------------- filters
st.sidebar.header("Filters")
d_min, d_max = lines["order_date"].min().date(), lines["order_date"].max().date()
date_range = st.sidebar.date_input("Order date", (d_min, d_max), min_value=d_min, max_value=d_max)
cats = st.sidebar.multiselect("Category", sorted(lines["category"].unique()))
regions = st.sidebar.multiselect("Region", sorted(lines["region"].unique()))
channels = st.sidebar.multiselect("Acquisition channel", sorted(lines["acquisition_channel"].unique()))

f = lines
if isinstance(date_range, tuple) and len(date_range) == 2:
    f = f[f["order_date"].between(pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1]))]
if cats:
    f = f[f["category"].isin(cats)]
if regions:
    f = f[f["region"].isin(regions)]
if channels:
    f = f[f["acquisition_channel"].isin(channels)]

if f.empty:
    st.warning("No orders match these filters.")
    st.stop()

# ---------------------------------------------------------------- KPIs
st.title("📊 Online Retail Performance")
st.caption("Net revenue = delivered orders only. Gross profit = net revenue − cost of goods.")

orders = f.groupby("order_id").agg(status=("status", "first"), rev=("net_revenue", "sum"))
delivered = orders[orders["status"] == "delivered"]
rev, profit = f["net_revenue"].sum(), f["gross_profit"].sum()
returned = f.loc[f["status"] == "returned", "line_total"].sum() / max(f["gmv"].sum(), 1)

def short(x: float) -> str:
    return f"${x / 1e6:.2f}M" if x >= 1e6 else f"${x / 1e3:.0f}K" if x >= 1e4 else f"${x:,.0f}"


row1, row2 = st.columns(3), st.columns(3)
row1[0].metric("Net revenue", short(rev))
row1[1].metric("Gross profit", short(profit))
row1[2].metric("Gross margin", f"{profit / rev:.1%}" if rev else "–")
row2[0].metric("Orders", f"{len(orders):,}")
row2[1].metric("Avg order value", f"${delivered['rev'].mean():,.0f}" if len(delivered) else "–")
row2[2].metric("Return rate (by value)", f"{returned:.1%}")

# ---------------------------------------------------------------- trend + category
left, right = st.columns([3, 2])
with left:
    st.subheader("Monthly trend")
    monthly = f.groupby("order_month")[["net_revenue", "gross_profit"]].sum()
    monthly.index = pd.to_datetime(monthly.index)
    st.line_chart(monthly, y_label="USD")
with right:
    st.subheader("By category")
    cat = f.groupby("category").agg(net_revenue=("net_revenue", "sum"), gross_profit=("gross_profit", "sum"))
    cat["margin"] = cat["gross_profit"] / cat["net_revenue"]
    st.bar_chart(cat[["net_revenue", "gross_profit"]].sort_values("net_revenue"), horizontal=True, stack=False)

# ---------------------------------------------------------------- channels + regions
left, right = st.columns(2)
with left:
    st.subheader("Acquisition channels")
    per_cust = (f[f["status"] != "cancelled"]
                .groupby(["acquisition_channel", "customer_id"])
                .agg(orders=("order_id", "nunique"), profit=("gross_profit", "sum")).reset_index())
    ch = per_cust.groupby("acquisition_channel").agg(
        customers=("customer_id", "size"),
        repeat_rate=("orders", lambda s: (s >= 2).mean()),
        profit_per_customer=("profit", "mean"),
    ).sort_values("profit_per_customer", ascending=False)
    st.dataframe(ch.style.format({"repeat_rate": "{:.1%}", "profit_per_customer": "${:,.2f}", "customers": "{:,}"}),
                 width="stretch")
with right:
    st.subheader("Regions")
    reg = f.groupby("region").agg(net_revenue=("net_revenue", "sum"), customers=("customer_id", "nunique"))
    reg["revenue_per_customer"] = reg["net_revenue"] / reg["customers"]
    st.dataframe(reg.sort_values("net_revenue", ascending=False)
                 .style.format({"net_revenue": "${:,.0f}", "revenue_per_customer": "${:,.2f}", "customers": "{:,}"}),
                 width="stretch")

# ---------------------------------------------------------------- customers
st.subheader("Customer segments (RFM, all-time)")
seg = rfm.groupby("segment").agg(customers=("customer_id", "size"), revenue=("monetary", "sum"),
                                 avg_recency_days=("recency_days", "mean"), avg_orders=("frequency", "mean"))
seg["revenue_share"] = seg["revenue"] / seg["revenue"].sum()
st.dataframe(seg.sort_values("revenue", ascending=False).style.format(
    {"revenue": "${:,.0f}", "revenue_share": "{:.1%}", "avg_recency_days": "{:.0f}", "avg_orders": "{:.2f}", "customers": "{:,}"}),
    width="stretch")

st.subheader("Cohort retention (filtered orders)")
o = f[f["status"] != "cancelled"].drop_duplicates("order_id")[["customer_id", "order_month"]]
first = o.groupby("customer_id")["order_month"].min().rename("cohort_month")
o = o.join(first, on="customer_id")
o["month_number"] = ((pd.to_datetime(o["order_month"]).dt.year - pd.to_datetime(o["cohort_month"]).dt.year) * 12
                     + pd.to_datetime(o["order_month"]).dt.month - pd.to_datetime(o["cohort_month"]).dt.month)
act = o.drop_duplicates(["customer_id", "month_number"]).groupby(["cohort_month", "month_number"]).size().rename("active").reset_index()
act = act.join(first.value_counts().rename("cohort_size"), on="cohort_month")
act["retention_rate"] = act["active"] / act["cohort_size"]
st.dataframe(cohort_matrix(act).style.format("{:.0%}", na_rep="").background_gradient(cmap="Blues", axis=None, vmin=0, vmax=0.25),
             width="stretch")

with st.expander("Download filtered data"):
    st.download_button("Download order lines (CSV)", f.to_csv(index=False), "order_lines_filtered.csv", "text/csv")
