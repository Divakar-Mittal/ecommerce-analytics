"""Unit tests for cleaning rules + integrity checks on the built warehouse."""
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import clean  # noqa: E402

DB = ROOT / "data" / "processed" / "warehouse.db"


# ---------------------------------------------------------------- helpers
def test_normalize_text():
    s = pd.Series([" north ", "NORTH", "north", "paid  search"])
    assert clean.normalize_text(s).tolist() == ["North", "North", "North", "Paid Search"]


def test_parse_mixed_dates():
    out = clean.parse_mixed_dates(pd.Series(["2025-03-01", "01/03/2025", "not a date"]))
    assert out[0] == out[1] == pd.Timestamp("2025-03-01")
    assert pd.isna(out[2])


def test_parse_price():
    out = clean.parse_price(pd.Series(["$1,234.50", "19.99", "abc"]))
    assert out[0] == 1234.5 and out[1] == 19.99 and np.isnan(out[2])


# ---------------------------------------------------------------- table rules
def test_clean_orders_keeps_orders_without_discount_code():
    """Regression: NA discount codes must not be treated as 'drop this row'."""
    df = pd.DataFrame({
        "order_id": [1, 2, 3, 4],
        "customer_id": [10, 10, 11, 99],
        "order_date": ["2025-01-01", "02/01/2025", "2025-01-03", "2025-01-04"],
        "status": ["Delivered", "returned", "DELIVERED", "delivered"],
        "discount_code": [pd.NA, "save10", "TEST", pd.NA],
        "shipping_fee": [0, 0, 0, 0],
    })
    out = clean.clean_orders(df, {10, 11}, clean.CleaningLog())
    assert out["order_id"].tolist() == [1, 2]          # 3 = test order, 4 = unknown customer
    assert out["status"].tolist() == ["delivered", "returned"]
    assert out["discount_code"].tolist() == ["", "SAVE10"]
    assert out["order_date"].tolist() == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02")]


def test_clean_customers_dedupes_and_nulls_bad_ages():
    df = pd.DataFrame({
        "customer_id": [1, 1, 2, 3],
        "signup_date": ["2024-01-01"] * 4,
        "region": [" west", " west", "EAST", "North"],
        "acquisition_channel": ["social", "social", "Email", "Referral"],
        "age": [30, 30, 999, np.nan],
    })
    out = clean.clean_customers(df, clean.CleaningLog())
    assert out["customer_id"].tolist() == [1, 2, 3]
    assert out["region"].tolist() == ["West", "East", "North"]
    assert out["age"].isna().tolist() == [False, True, True]


def test_clean_items_drops_invalid_rows():
    df = pd.DataFrame({
        "order_item_id": [1, 2, 3, 4, 5],
        "order_id": [100, 100, 100, 100, 200],
        "product_id": pd.array([1, 1, pd.NA, 1, 1], dtype="Int64"),
        "quantity": [2, -1, 1, 1, 1],
        "unit_price": ["$1,000.00", "5", "5", "abc", "5"],
    })
    out = clean.clean_items(df, valid_orders={100}, valid_products={1}, log=clean.CleaningLog())
    assert out["order_item_id"].tolist() == [1]
    assert out["line_total"].iloc[0] == 2000.0


# ---------------------------------------------------------------- warehouse integrity
@pytest.fixture(scope="module")
def con():
    if not DB.exists():
        pytest.skip("warehouse not built; run `python run_pipeline.py` first")
    with sqlite3.connect(DB) as c:
        yield c


def q(con, sql):
    return con.execute(sql).fetchone()[0]


def test_primary_keys_unique(con):
    for table, key in [("customers", "customer_id"), ("orders", "order_id"),
                       ("order_items", "order_item_id"), ("products", "product_id")]:
        assert q(con, f"SELECT COUNT(*) - COUNT(DISTINCT {key}) FROM {table}") == 0, table


def test_no_orphans(con):
    assert q(con, "SELECT COUNT(*) FROM orders WHERE customer_id NOT IN (SELECT customer_id FROM customers)") == 0
    assert q(con, "SELECT COUNT(*) FROM order_items WHERE order_id NOT IN (SELECT order_id FROM orders)") == 0
    assert q(con, "SELECT COUNT(*) FROM order_items WHERE product_id NOT IN (SELECT product_id FROM products)") == 0


def test_values_valid(con):
    assert q(con, "SELECT COUNT(*) FROM order_items WHERE quantity <= 0 OR unit_price <= 0") == 0
    assert q(con, "SELECT COUNT(*) FROM orders WHERE status NOT IN ('delivered','returned','cancelled')") == 0


def test_views_reconcile_with_base_tables(con):
    base = q(con, """SELECT SUM(oi.quantity * oi.unit_price) FROM order_items oi
                     JOIN orders o USING (order_id) WHERE o.status = 'delivered'""")
    view = q(con, "SELECT SUM(net_revenue) FROM v_orders")
    assert view == pytest.approx(base, rel=1e-9)


def test_monthly_kpis_sum_to_total(con):
    kpis = pd.read_sql((ROOT / "sql" / "01_monthly_kpis.sql").read_text(), con)
    assert kpis["net_revenue"].sum() == pytest.approx(q(con, "SELECT SUM(net_revenue) FROM v_orders"), rel=1e-6)
    assert kpis["orders"].sum() == q(con, "SELECT COUNT(*) FROM orders")
