"""
utils.py — Data loading and transformation layer.

Architecture decision: all DataFrame operations live here so app.py stays
purely presentational. This separation makes each function independently
testable and keeps Streamlit cache decorators close to the I/O boundary.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

# Resolve data directory relative to this file so the app works regardless
# of where the user launches Streamlit from.
DATA_DIR = Path(__file__).parent / "data"

_ORDERS_FILE = DATA_DIR / "olist_orders_dataset.csv"
_ITEMS_FILE = DATA_DIR / "olist_order_items_dataset.csv"
_PRODUCTS_FILE = DATA_DIR / "olist_products_dataset.csv"

# Months with fewer orders than this are treated as incomplete in the trend chart.
MIN_ORDERS_PER_MONTH = 500


@st.cache_data
def load_data() -> pd.DataFrame:
    """Load and merge the three Olist CSV files into a consolidated DataFrame.

    Merge strategy:
        orders  →  order_items  (inner join on order_id — keeps only orders
                                  that have at least one item)
        result  →  products     (left join on product_id — keeps all items
                                  even if the product has no category)

    Revenue is computed as price + freight_value so every downstream function
    works from a single "revenue" column rather than summing two columns each time.

    Returns
    -------
    pd.DataFrame
        Consolidated DataFrame with columns from all three source files plus:
        - revenue       : float  — price + freight_value per order item
        - order_month   : Timestamp — first day of the purchase month (for grouping)

    Raises
    ------
    FileNotFoundError
        If any of the three source CSVs is missing from data/.
    """
    missing = [f for f in [_ORDERS_FILE, _ITEMS_FILE, _PRODUCTS_FILE] if not f.exists()]
    if missing:
        names = ", ".join(f.name for f in missing)
        raise FileNotFoundError(
            f"Missing CSV file(s) in data/: {names}. "
            "Download the Olist dataset from Kaggle and place the files in the data/ folder."
        )

    orders = pd.read_csv(
        _ORDERS_FILE,
        parse_dates=["order_purchase_timestamp"],
    )
    items = pd.read_csv(_ITEMS_FILE)
    # Only the two columns we actually use from products to keep memory lean.
    products = pd.read_csv(_PRODUCTS_FILE, usecols=["product_id", "product_category_name"])

    df = orders.merge(items, on="order_id", how="inner")
    df = df.merge(products, on="product_id", how="left")

    df["revenue"] = df["price"] + df["freight_value"]

    # to_period("M").to_timestamp() gives the first day of each month —
    # a proper datetime that Plotly can render on a continuous time axis.
    df["order_month"] = df["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()

    return df

# English display names for the most common Olist categories (the raw dataset
# uses Portuguese snake_case). Unmapped categories fall back to a cleaned label.
CATEGORY_LABELS_EN = {
    "beleza_saude": "Health & Beauty",
    "relogios_presentes": "Watches & Gifts",
    "cama_mesa_banho": "Bed, Bath & Table",
    "esporte_lazer": "Sports & Leisure",
    "informatica_acessorios": "Computer Accessories",
    "moveis_decoracao": "Furniture & Decor",
    "utilidades_domesticas": "Housewares",
    "cool_stuff": "Cool Stuff",
    "automotivo": "Automotive",
    "ferramentas_jardim": "Garden Tools",
    "brinquedos": "Toys",
    "bebes": "Baby",
    "perfumaria": "Perfumery",
    "telefonia": "Telephony",
    "moveis_escritorio": "Office Furniture",
    "papelaria": "Stationery",
    "pet_shop": "Pet Shop",
    "eletronicos": "Electronics",
    "construcao_ferramentas_construcao": "Construction Tools",
    "fashion_bolsas_e_acessorios": "Bags & Accessories",
}


def category_label(raw: str) -> str:
    """Readable English label for an Olist category name."""
    return CATEGORY_LABELS_EN.get(raw, raw.replace("_", " ").capitalize())


def get_monthly_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate total revenue by calendar month.

    Parameters
    ----------
    df : pd.DataFrame
        Consolidated DataFrame produced by load_data().

    Months with fewer than MIN_ORDERS_PER_MONTH orders (the partial months at
    the edges of the dataset) are excluded.

    Returns
    -------
    pd.DataFrame
        Columns: order_month (Timestamp), revenue (float), sorted ascending.
    """
    monthly = (
        df.groupby("order_month", as_index=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .sort_values("order_month")
    )
    # The dataset starts and ends with partial months (e.g. Sep 2018 has only a
    # handful of orders). Plotting them would show a fake collapse in revenue,
    # so months below a minimum order volume are left out of the trend line.
    return monthly[monthly["orders"] >= MIN_ORDERS_PER_MONTH][["order_month", "revenue"]]


def get_top_categories(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return the top N product categories ranked by total revenue.

    Rows where product_category_name is NaN (items with no matching product)
    are excluded so they don't pollute the chart with an "unknown" bar.

    Parameters
    ----------
    df : pd.DataFrame
        Consolidated DataFrame produced by load_data().
    n : int
        Number of top categories to return. Defaults to 10.

    Returns
    -------
    pd.DataFrame
        Columns: product_category_name (str, English display label), revenue (float),
        sorted descending by revenue, length ≤ n.
    """
    return (
        df.dropna(subset=["product_category_name"])
        .groupby("product_category_name", as_index=False)["revenue"]
        .sum()
        .sort_values("revenue", ascending=False)
        .head(n)
        .assign(product_category_name=lambda d: d["product_category_name"].map(category_label))
    )


def get_order_status_dist(df: pd.DataFrame) -> pd.DataFrame:
    """Return the percentage distribution of order statuses.

    We deduplicate on order_id first because each order can have multiple
    items — without deduplication, multi-item orders would be over-counted.

    Parameters
    ----------
    df : pd.DataFrame
        Consolidated DataFrame produced by load_data().

    Returns
    -------
    pd.DataFrame
        Columns: order_status (str), percentage (float, 0–100).
    """
    counts = (
        df.drop_duplicates("order_id")["order_status"]
        .value_counts(normalize=True)
        .reset_index()
    )
    counts.columns = ["order_status", "percentage"]
    counts["percentage"] = (counts["percentage"] * 100).round(2)
    return counts


def get_kpis(df: pd.DataFrame) -> dict:
    """Compute top-level business KPIs from the filtered DataFrame.

    Average ticket is calculated as total_revenue / total_orders (not per item)
    to reflect the real business metric: revenue per order placed.

    Parameters
    ----------
    df : pd.DataFrame
        Consolidated DataFrame produced by load_data() (may be date-filtered).

    Returns
    -------
    dict
        Keys: total_revenue (float), total_orders (int), avg_ticket (float).
    """
    total_revenue = df["revenue"].sum()
    total_orders = df["order_id"].nunique()
    avg_ticket = total_revenue / total_orders if total_orders > 0 else 0.0
    return {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "avg_ticket": avg_ticket,
    }
