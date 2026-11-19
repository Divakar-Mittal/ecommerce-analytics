"""
Generate a realistic (and deliberately messy) e-commerce dataset.

The data simulates an online retailer from 2024-01-01 to 2025-12-31 with:
  * customer growth and Nov/Dec seasonality
  * acquisition channels with different repeat-purchase behaviour
  * category-specific margins and return rates
  * discount codes, heavier around Black Friday

Real-world data quality problems are injected on purpose so the cleaning
step has something to do: duplicates, inconsistent casing/whitespace,
mixed date formats, prices stored as text, impossible values and orphan keys.

Usage:  python -m src.generate_data
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START = pd.Timestamp("2024-01-01")
END = pd.Timestamp("2025-12-31")
N_CUSTOMERS = 8_000

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

CATEGORIES = {
    # name: (n_products, price_low, price_high, margin, return_rate)
    "Electronics": (20, 40, 900, 0.18, 0.08),
    "Home & Kitchen": (25, 15, 250, 0.35, 0.06),
    "Fashion": (30, 12, 180, 0.55, 0.18),
    "Beauty": (20, 8, 90, 0.60, 0.05),
    "Sports": (15, 15, 300, 0.40, 0.07),
    "Books": (10, 6, 45, 0.30, 0.02),
}

CHANNELS = {
    # name: (share of signups, probability of another purchase)
    "Organic": (0.30, 0.45),
    "Paid Search": (0.25, 0.35),
    "Social": (0.20, 0.28),
    "Email": (0.10, 0.50),
    "Referral": (0.15, 0.55),
}

REGIONS = ["North", "South", "East", "West", "Central"]
REGION_WEIGHTS = [0.22, 0.24, 0.18, 0.26, 0.10]

ADJECTIVES = ["Classic", "Pro", "Eco", "Smart", "Ultra", "Essential", "Premium", "Lite", "Max", "Urban"]
NOUNS = {
    "Electronics": ["Headphones", "Speaker", "Smartwatch", "Tablet", "Charger", "Camera", "Keyboard"],
    "Home & Kitchen": ["Blender", "Pan Set", "Lamp", "Kettle", "Cushion", "Knife Set", "Organizer"],
    "Fashion": ["Jacket", "Sneakers", "Jeans", "Dress", "Hoodie", "Scarf", "Backpack"],
    "Beauty": ["Serum", "Moisturizer", "Lipstick", "Shampoo", "Face Mask", "Perfume"],
    "Sports": ["Yoga Mat", "Dumbbells", "Running Shoes", "Water Bottle", "Bike Helmet"],
    "Books": ["Novel", "Cookbook", "Biography", "Guidebook", "Workbook"],
}


def make_products(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    pid = 1000
    for cat, (n, lo, hi, margin, _) in CATEGORIES.items():
        for _ in range(n):
            # log-uniform prices: many cheap items, a few expensive ones
            price = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
            price = round(price) - 0.01 if price > 20 else round(price, 1) - 0.01
            cost = round(price * (1 - margin) * rng.uniform(0.9, 1.1), 2)
            name = f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS[cat])}"
            rows.append((pid, name, cat, round(price, 2), cost))
            pid += 1
    return pd.DataFrame(rows, columns=["product_id", "product_name", "category", "list_price", "unit_cost"])


def make_customers(rng: np.random.Generator) -> pd.DataFrame:
    days = pd.date_range(START, END - pd.Timedelta(days=14), freq="D")
    t = np.arange(len(days)) / len(days)
    weight = 1 + 1.5 * t  # business is growing
    weight *= np.where(days.month.isin([11, 12]), 1.6, 1.0)  # holiday acquisition
    weight /= weight.sum()
    signup = rng.choice(days, size=N_CUSTOMERS, p=weight)

    ch_names = list(CHANNELS)
    ch_p = np.array([CHANNELS[c][0] for c in ch_names])
    return pd.DataFrame({
        "customer_id": np.arange(1, N_CUSTOMERS + 1),
        "signup_date": pd.to_datetime(signup),
        "region": rng.choice(REGIONS, size=N_CUSTOMERS, p=REGION_WEIGHTS),
        "acquisition_channel": rng.choice(ch_names, size=N_CUSTOMERS, p=ch_p / ch_p.sum()),
        "age": np.clip(rng.normal(36, 11, N_CUSTOMERS).round(), 18, 80).astype(int),
    })


def make_orders(rng, customers, products):
    cat_return = {c: v[4] for c, v in CATEGORIES.items()}
    prod_ids = products["product_id"].to_numpy()
    # Zipf-like popularity: a handful of products drive most sales
    pop = 1 / np.arange(1, len(prod_ids) + 1) ** 0.8
    pop = rng.permutation(pop)
    pop /= pop.sum()
    price_of = products.set_index("product_id")["list_price"].to_dict()
    cat_of = products.set_index("product_id")["category"].to_dict()

    orders, items = [], []
    oid, iid = 500_000, 1

    def add_order(cust_id, date):
        nonlocal oid, iid
        oid += 1
        bf = date.month == 11 and 20 <= date.day <= 30
        if bf and rng.random() < 0.55:
            code, disc = "BLACKFRIDAY25", 0.25
        elif rng.random() < 0.22:
            code = str(rng.choice(["SAVE10", "SAVE15", "VIP20"], p=[0.5, 0.35, 0.15]))
            disc = {"SAVE10": 0.10, "SAVE15": 0.15, "VIP20": 0.20}[code]
        else:
            code, disc = "", 0.0
        n_items = rng.choice([1, 2, 3, 4], p=[0.5, 0.3, 0.15, 0.05])
        chosen = rng.choice(prod_ids, size=n_items, replace=False, p=pop)
        ret_p = max(cat_return[cat_of[p]] for p in chosen)
        r = rng.random()
        status = "cancelled" if r < 0.03 else ("returned" if r < 0.03 + ret_p else "delivered")
        subtotal = 0.0
        for p in chosen:
            qty = int(rng.choice([1, 2, 3], p=[0.8, 0.15, 0.05]))
            unit = round(price_of[p] * (1 - disc), 2)
            subtotal += qty * unit
            items.append((iid, oid, int(p), qty, unit))
            iid += 1
        shipping = 0.0 if subtotal >= 50 else 4.99
        orders.append((oid, cust_id, date, status, code, shipping))

    for c in customers.itertuples(index=False):
        p_repeat = CHANNELS[c.acquisition_channel][1]
        date = c.signup_date + pd.Timedelta(days=int(rng.integers(0, 7)))
        while date <= END:
            add_order(c.customer_id, date)
            if rng.random() > p_repeat:
                break
            date = date + pd.Timedelta(days=int(rng.exponential(55)) + 3)
        # holiday shopping: existing customers come back for gifts
        for year in (2024, 2025):
            if c.signup_date < pd.Timestamp(f"{year}-11-01") and rng.random() < 0.12:
                add_order(c.customer_id, pd.Timestamp(f"{year}-11-15") + pd.Timedelta(days=int(rng.integers(0, 40))))

    orders = pd.DataFrame(orders, columns=["order_id", "customer_id", "order_date", "status", "discount_code", "shipping_fee"])
    items = pd.DataFrame(items, columns=["order_item_id", "order_id", "product_id", "quantity", "unit_price"])
    orders = orders[orders["order_date"] <= END]
    items = items[items["order_id"].isin(orders["order_id"])]
    return orders, items


def make_messy(rng, customers, orders, items):
    """Inject the kind of problems you meet in real exports."""
    customers = customers.copy()
    orders = orders.copy()
    items = items.copy()

    # customers: inconsistent text, missing / impossible ages, duplicate rows
    idx = rng.choice(customers.index, size=int(0.06 * len(customers)), replace=False)
    customers.loc[idx, "region"] = [rng.choice([r.upper(), r.lower(), f" {r} ", f"{r} "]) for r in customers.loc[idx, "region"]]
    idx = rng.choice(customers.index, size=int(0.04 * len(customers)), replace=False)
    customers.loc[idx, "acquisition_channel"] = customers.loc[idx, "acquisition_channel"].str.lower()
    customers["age"] = customers["age"].astype("float")
    customers.loc[rng.choice(customers.index, size=int(0.08 * len(customers)), replace=False), "age"] = np.nan
    customers.loc[rng.choice(customers.index, size=15, replace=False), "age"] = rng.choice([0, 999, -1, 150], size=15)
    customers = pd.concat([customers, customers.sample(40, random_state=SEED)], ignore_index=True)

    # orders: duplicates, mixed date formats, status casing, orphan/test orders
    orders["order_date"] = orders["order_date"].dt.strftime("%Y-%m-%d")
    idx = rng.choice(orders.index, size=int(0.03 * len(orders)), replace=False)
    orders.loc[idx, "order_date"] = pd.to_datetime(orders.loc[idx, "order_date"]).dt.strftime("%d/%m/%Y")
    idx = rng.choice(orders.index, size=int(0.05 * len(orders)), replace=False)
    orders.loc[idx, "status"] = orders.loc[idx, "status"].str.capitalize()
    orders.loc[rng.choice(orders.index, size=int(0.01 * len(orders)), replace=False), "status"] = "DELIVERED"
    test = pd.DataFrame({
        "order_id": np.arange(900_001, 900_026),
        "customer_id": 99_999,  # not a real customer
        "order_date": "2025-03-01",
        "status": "delivered",
        "discount_code": "TEST",
        "shipping_fee": 0.0,
    })
    orders = pd.concat([orders, test, orders.sample(frac=0.015, random_state=SEED)], ignore_index=True)

    # items: prices stored as text, negative quantities, missing product ids
    items["unit_price"] = items["unit_price"].astype(object)
    idx = rng.choice(items.index, size=int(0.02 * len(items)), replace=False)
    items.loc[idx, "unit_price"] = ["$" + f"{v:,.2f}" for v in items.loc[idx, "unit_price"]]
    items.loc[rng.choice(items.index, size=int(0.003 * len(items)), replace=False), "quantity"] = -1
    items["product_id"] = items["product_id"].astype("Int64")
    items.loc[rng.choice(items.index, size=25, replace=False), "product_id"] = pd.NA
    items = pd.concat([items, items.sample(frac=0.01, random_state=SEED)], ignore_index=True)

    return customers.sample(frac=1, random_state=SEED), orders.sample(frac=1, random_state=SEED), items


def main() -> None:
    rng = np.random.default_rng(SEED)
    products = make_products(rng)
    customers = make_customers(rng)
    orders, items = make_orders(rng, customers, products)
    customers, orders, items = make_messy(rng, customers, orders, items)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    products.to_csv(RAW_DIR / "products.csv", index=False)
    customers.to_csv(RAW_DIR / "customers.csv", index=False, date_format="%Y-%m-%d")
    orders.to_csv(RAW_DIR / "orders.csv", index=False)
    items.to_csv(RAW_DIR / "order_items.csv", index=False)
    print(f"Raw data written to {RAW_DIR}")
    for name, df in [("products", products), ("customers", customers), ("orders", orders), ("order_items", items)]:
        print(f"  {name:<12} {len(df):>7,} rows")


if __name__ == "__main__":
    main()
