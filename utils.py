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


def get_monthly_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate total revenue by calendar month.

    Parameters
    ----------
    df : pd.DataFrame
        Consolidated DataFrame produced by load_data().

    Returns
    -------
    pd.DataFrame
        Columns: order_month (Timestamp), revenue (float), sorted ascending.
    """
    return (
        df.groupby("order_month", as_index=False)["revenue"]
        .sum()
        .sort_values("order_month")
    )


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
        Columns: product_category_name (str), revenue (float),
        sorted descending by revenue, length ≤ n.
    """
    return (
        df.dropna(subset=["product_category_name"])
        .groupby("product_category_name", as_index=False)["revenue"]
        .sum()
        .sort_values("revenue", ascending=False)
        .head(n)
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
