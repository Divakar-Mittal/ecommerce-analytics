"""
Run every SQL analysis, export result tables, draw charts and write an
insights report whose numbers come straight from the data.

Usage:  python -m src.analysis
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "warehouse.db"
SQL_DIR = ROOT / "sql"
TABLE_DIR = ROOT / "reports" / "tables"
FIG_DIR = ROOT / "reports" / "figures"
INSIGHTS = ROOT / "reports" / "insights.md"

QUERIES = {
    "monthly_kpis": "01_monthly_kpis.sql",
    "category": "02_category_performance.sql",
    "cohorts": "03_cohort_retention.sql",
    "rfm": "04_rfm_segments.sql",
    "channel": "05_channel_ltv.sql",
    "discount": "06_discount_impact.sql",
    "region": "07_region_yoy.sql",
}

BLUE, ORANGE, GREY, RED = "#2563eb", "#f59e0b", "#9ca3af", "#dc2626"
plt.rcParams.update({
    "figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "axes.titleweight": "bold", "font.size": 10,
})


def run_queries(db_path: Path = DB_PATH) -> dict[str, pd.DataFrame]:
    with sqlite3.connect(db_path) as con:
        return {k: pd.read_sql((SQL_DIR / f).read_text(), con) for k, f in QUERIES.items()}


def money(x: float) -> str:
    return f"${x / 1e6:.2f}M" if abs(x) >= 1e6 else f"${x / 1e3:,.0f}K" if abs(x) >= 1e4 else f"${x:,.0f}"


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def cohort_matrix(cohorts: pd.DataFrame, max_month: int = 12) -> pd.DataFrame:
    m = cohorts.pivot(index="cohort_month", columns="month_number", values="retention_rate")
    return m.reindex(columns=range(0, max_month + 1))


# ---------------------------------------------------------------- charts
def chart_revenue_trend(df):
    fig, ax = plt.subplots(figsize=(10, 4))
    x = pd.to_datetime(df["order_month"])
    ax.bar(x, df["net_revenue"], width=20, color=BLUE, label="Net revenue")
    ax2 = ax.twinx()
    ax2.plot(x, df["gross_margin"], color=ORANGE, marker="o", lw=2, label="Gross margin")
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax2.set_ylim(0, 0.45)
    ax2.grid(False)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"${v / 1e3:.0f}K"))
    ax.set_title("Monthly net revenue and gross margin")
    fig.legend(loc="upper left", bbox_to_anchor=(0.07, 0.88), frameon=False)
    fig.tight_layout()
    return fig


def chart_category(df):
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(df))
    ax.barh(y - 0.2, df["revenue_share"], height=0.4, color=BLUE, label="Share of revenue")
    ax.barh(y + 0.2, df["profit_share"], height=0.4, color=ORANGE, label="Share of gross profit")
    ax.set_yticks(y, df["category"])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_title("Revenue share vs profit share by category")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    return fig


def chart_cohorts(cohorts):
    m = cohort_matrix(cohorts).iloc[:, 1:]  # month 0 is always 100%
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(m.values, cmap="Blues", aspect="auto", vmin=0, vmax=0.25)
    ax.set_xticks(range(m.shape[1]), m.columns)
    ax.set_yticks(range(m.shape[0]), m.index)
    ax.set_xlabel("Months since first purchase")
    ax.set_title("Cohort retention (share of cohort ordering again)")
    ax.grid(False)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v * 100:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if v > 0.15 else "#1f2937")
    fig.colorbar(im, ax=ax, format=mtick.PercentFormatter(1.0), shrink=0.8)
    fig.tight_layout()
    return fig


def chart_rfm(rfm):
    seg = rfm.groupby("segment").agg(customers=("customer_id", "size"), revenue=("monetary", "sum"))
    seg = (seg / seg.sum()).sort_values("revenue", ascending=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(seg))
    ax.barh(y - 0.2, seg["customers"], height=0.4, color=GREY, label="Share of customers")
    ax.barh(y + 0.2, seg["revenue"], height=0.4, color=BLUE, label="Share of revenue")
    ax.set_yticks(y, seg.index)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.set_title("RFM segments: customers vs revenue")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    return fig


def chart_channel(df):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df["acquisition_channel"], df["avg_profit_per_customer"], color=BLUE)
    for i, (v, r) in enumerate(zip(df["avg_profit_per_customer"], df["repeat_purchase_rate"])):
        ax.text(i, v + 1.5, f"${v:.0f}\nrepeat {r * 100:.0f}%", ha="center", fontsize=9)
    ax.set_ylabel("Gross profit per customer")
    ax.set_ylim(0, df["avg_profit_per_customer"].max() * 1.25)
    ax.set_title("Customer value by acquisition channel")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------- insights
def build_insights(r: dict[str, pd.DataFrame]) -> str:
    k, cat, ch, disc, reg, rfm = r["monthly_kpis"], r["category"], r["channel"], r["discount"], r["region"], r["rfm"]
    k = k.assign(year=k["order_month"].str[:4])
    yr = k.groupby("year").agg(revenue=("net_revenue", "sum"), profit=("gross_profit", "sum"), orders=("orders", "sum"))
    growth = yr.loc["2025", "revenue"] / yr.loc["2024", "revenue"] - 1
    total_rev, total_profit = k["net_revenue"].sum(), k["gross_profit"].sum()

    holiday = k[k["order_month"].str[5:].isin(["11", "12"])]
    holiday_share = holiday["net_revenue"].sum() / total_rev
    nov = k[k["order_month"].str.endswith("-11")]["gross_margin"].mean()
    other = k[~k["order_month"].str[5:].isin(["11"])]["gross_margin"].mean()

    top = cat.iloc[0]
    worst_return = cat.sort_values("return_rate_by_value", ascending=False).iloc[0]
    best_margin = cat.sort_values("gross_margin", ascending=False).iloc[0]

    best_ch, worst_ch = ch.iloc[0], ch.iloc[-1]
    ch_gap = best_ch["avg_profit_per_customer"] / worst_ch["avg_profit_per_customer"] - 1

    d = disc.set_index("order_type")
    m30 = cohort_matrix(r["cohorts"])
    m1_ret = m30[1].dropna().median()
    m3_ret = m30[3].dropna().median()
    first_purchase_only = (rfm["frequency"] == 1).mean()

    seg = rfm.groupby("segment").agg(n=("customer_id", "size"), rev=("monetary", "sum"))
    seg["n_share"], seg["rev_share"] = seg["n"] / seg["n"].sum(), seg["rev"] / seg["rev"].sum()
    at_risk = seg.loc["At Risk"]
    champs = seg.loc["Champions"]

    fastest = reg.sort_values("yoy_growth", ascending=False).iloc[0]
    slowest = reg.sort_values("yoy_growth").iloc[0]

    lines = [
        "# Insights Report: Online Retail Performance 2024-2025",
        "",
        "_All figures are generated by `src/analysis.py` from the cleaned warehouse._",
        "",
        "## Headline numbers",
        "",
        "| Metric | 2024 | 2025 |",
        "|---|---:|---:|",
        f"| Net revenue | {money(yr.loc['2024', 'revenue'])} | {money(yr.loc['2025', 'revenue'])} |",
        f"| Gross profit | {money(yr.loc['2024', 'profit'])} | {money(yr.loc['2025', 'profit'])} |",
        f"| Orders | {yr.loc['2024', 'orders']:,} | {yr.loc['2025', 'orders']:,} |",
        "",
        f"Net revenue grew **{pct(growth)}** year on year. Over both years the business made "
        f"{money(total_rev)} in net revenue at a {pct(total_profit / total_rev)} gross margin.",
        "",
        "## Key findings",
        "",
        f"1. **Electronics drives revenue, not profit.** {top['category']} is {pct(top['revenue_share'], 0)} of revenue "
        f"but only {pct(top['profit_share'], 0)} of gross profit (margin {pct(top['gross_margin'])}). "
        f"{best_margin['category']} has the best margin at {pct(best_margin['gross_margin'])}.",
        f"2. **{worst_return['category']} has a returns problem.** {pct(worst_return['return_rate_by_value'])} of "
        f"{worst_return['category']} order value is returned ({money(worst_return['returned_value'])} over two years), "
        f"the highest of any category.",
        f"3. **Discounts cost margin and don't grow baskets.** Discounted orders have a {pct(d.loc['Discounted', 'gross_margin'])} "
        f"gross margin vs {pct(d.loc['Full price', 'gross_margin'])} at full price, and a lower average order value "
        f"(${d.loc['Discounted', 'aov']:.0f} vs ${d.loc['Full price', 'aov']:.0f}). Return rates are about the same.",
        f"4. **Holidays are the business.** November and December bring {pct(holiday_share, 0)} of revenue, but November margin "
        f"falls to {pct(nov)} (vs {pct(other)} in other months) because of Black Friday codes.",
        f"5. **Channel quality varies a lot.** {best_ch['acquisition_channel']} customers are worth "
        f"${best_ch['avg_profit_per_customer']:.0f} gross profit each, {pct(ch_gap, 0)} more than "
        f"{worst_ch['acquisition_channel']} (${worst_ch['avg_profit_per_customer']:.0f}). Repeat rates: "
        f"{pct(best_ch['repeat_purchase_rate'], 0)} vs {pct(worst_ch['repeat_purchase_rate'], 0)}.",
        f"6. **Most customers buy once.** {pct(first_purchase_only, 0)} of customers have a single order. "
        f"In the median cohort only {pct(m1_ret)} of customers order again the next month, and {pct(m3_ret)} in month 3.",
        f"7. **Revenue is concentrated.** Champions are {pct(champs['n_share'], 0)} of customers but "
        f"{pct(champs['rev_share'], 0)} of revenue. 'At Risk' customers ({at_risk['n']:,.0f} people, "
        f"{pct(at_risk['rev_share'], 0)} of historic revenue) used to buy often and have gone quiet.",
        f"8. **Every region grew**, fastest in {fastest['region']} ({pct(fastest['yoy_growth'], 0)}) and slowest in "
        f"{slowest['region']} ({pct(slowest['yoy_growth'], 0)}).",
        "",
        "## Recommendations",
        "",
        "| # | Recommendation | Why | How to measure |",
        "|---|---|---|---|",
        f"| 1 | Shift paid budget from Social toward Referral and Email programmes | {best_ch['acquisition_channel']} customers are worth {pct(ch_gap, 0)} more | Profit per acquired customer, by channel |",
        f"| 2 | Run a win-back campaign for the {at_risk['n']:,.0f} At Risk customers | They hold {pct(at_risk['rev_share'], 0)} of historic revenue | Reactivation rate within 60 days |",
        "| 3 | Replace blanket discount codes with targeted offers (e.g. second-order coupon) | Codes cut margin with no basket uplift | Margin and repeat rate of coupon users vs control |",
        f"| 4 | Investigate {worst_return['category']} returns: size guides, better photos, fit reviews | Highest return rate | Return rate by product |",
        f"| 5 | Bundle high-margin accessories with {top['category']} | Lifts margin on the biggest category | {top['category']} attach rate and margin |",
        "",
        "## Charts",
        "",
        "![Revenue trend](figures/revenue_trend.png)",
        "![Category](figures/category_revenue_vs_profit.png)",
        "![Cohorts](figures/cohort_retention.png)",
        "![RFM](figures/rfm_segments.png)",
        "![Channels](figures/channel_value.png)",
        "",
        "## Caveats",
        "",
        "- Lifetime value is *to date*: customers acquired late in 2025 have had less time to return.",
        "- Discount analysis is observational; a controlled A/B test is needed to prove causality.",
        "- The dataset is synthetic (see `src/generate_data.py`), built to mimic real e-commerce patterns.",
    ]
    return "\n".join(lines) + "\n"


def main() -> dict[str, pd.DataFrame]:
    results = run_queries()
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in results.items():
        df.to_csv(TABLE_DIR / f"{name}.csv", index=False)

    charts = {
        "revenue_trend": chart_revenue_trend(results["monthly_kpis"]),
        "category_revenue_vs_profit": chart_category(results["category"]),
        "cohort_retention": chart_cohorts(results["cohorts"]),
        "rfm_segments": chart_rfm(results["rfm"]),
        "channel_value": chart_channel(results["channel"]),
    }
    for name, fig in charts.items():
        fig.savefig(FIG_DIR / f"{name}.png", bbox_inches="tight")
        plt.close(fig)

    INSIGHTS.write_text(build_insights(results))
    print(f"Tables -> {TABLE_DIR}\nFigures -> {FIG_DIR}\nInsights -> {INSIGHTS}")
    return results


if __name__ == "__main__":
    main()
