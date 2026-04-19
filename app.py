"""
app.py — Streamlit presentation layer.

Architecture decision: this file contains zero business logic. Every
DataFrame transformation is delegated to utils.py so that the dashboard
can be read top-to-bottom as a pure layout description.
"""

import streamlit as st
import plotly.express as px

from utils import (
    load_data,
    get_monthly_revenue,
    get_top_categories,
    get_order_status_dist,
    get_kpis,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Olist Sales Dashboard",
    page_icon="🛒",
    layout="wide",
)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🛒 Olist Sales Dashboard")
st.subheader("E-commerce Analytics — Brazilian Market")
st.markdown(
    """
    Analytical dashboard built on the
    [Olist E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
    Explore monthly revenue trends, top-performing product categories,
    and the full distribution of order statuses — all filterable by date.
    """
)

# ── Data loading ──────────────────────────────────────────────────────────────
# Errors here mean the CSVs are missing; we surface a clear message and halt
# rather than letting Python raise a cryptic traceback inside Streamlit.
try:
    df_raw = load_data()
except FileNotFoundError as exc:
    st.error(f"**Data not found.** {exc}")
    st.stop()

# ── Sidebar: date-range filter ────────────────────────────────────────────────
st.sidebar.header("⚙️ Filters")
st.sidebar.markdown("---")

min_date = df_raw["order_purchase_timestamp"].dt.date.min()
max_date = df_raw["order_purchase_timestamp"].dt.date.max()

date_range = st.sidebar.date_input(
    "Select date range",
    value=[min_date, max_date],
    min_value=min_date,
    max_value=max_date,
)

# date_input returns a tuple only after both dates are chosen; guard against
# the intermediate single-date state while the user is still picking.
if len(date_range) != 2:
    st.info("Please select both a start and an end date in the sidebar.")
    st.stop()

start_date, end_date = date_range

mask = (
    df_raw["order_purchase_timestamp"].dt.date >= start_date
) & (df_raw["order_purchase_timestamp"].dt.date <= end_date)
df = df_raw[mask]

if df.empty:
    st.warning("No orders found for the selected date range. Try widening the filter.")
    st.stop()

st.sidebar.markdown(
    f"**{df['order_id'].nunique():,}** orders in range  \n"
    f"{start_date} → {end_date}"
)

# ── Row 1: KPI metrics ────────────────────────────────────────────────────────
kpis = get_kpis(df)

col1, col2, col3 = st.columns(3)
col1.metric(
    label="💰 Total Revenue",
    value=f"R$ {kpis['total_revenue']:,.0f}",
)
col2.metric(
    label="📦 Total Orders",
    value=f"{kpis['total_orders']:,}",
)
col3.metric(
    label="🎯 Average Ticket",
    value=f"R$ {kpis['avg_ticket']:,.2f}",
)

st.divider()

# ── Row 2: Monthly revenue line chart ─────────────────────────────────────────
monthly = get_monthly_revenue(df)

fig_line = px.line(
    monthly,
    x="order_month",
    y="revenue",
    title="Monthly Revenue Over Time",
    labels={"order_month": "Month", "revenue": "Revenue (R$)"},
    markers=True,
    template="plotly_white",
)
fig_line.update_traces(line_color="#1f77b4", line_width=2.5)
fig_line.update_layout(hovermode="x unified", title_font_size=18)

st.plotly_chart(fig_line, use_container_width=True)

# ── Row 3: Top categories horizontal bar chart ────────────────────────────────
top_cats = get_top_categories(df, n=10)

# Sort ascending so the longest bar appears at the top of the chart.
fig_bar = px.bar(
    top_cats.sort_values("revenue", ascending=True),
    x="revenue",
    y="product_category_name",
    orientation="h",
    title="Top 10 Categories by Revenue",
    labels={"revenue": "Revenue (R$)", "product_category_name": "Category"},
    color="revenue",
    color_continuous_scale="Blues",
    template="plotly_white",
)
fig_bar.update_layout(
    coloraxis_showscale=False,
    title_font_size=18,
    yaxis_title=None,
)

st.plotly_chart(fig_bar, use_container_width=True)

# ── Row 4: Order status pie chart ─────────────────────────────────────────────
status_dist = get_order_status_dist(df)

fig_pie = px.pie(
    status_dist,
    names="order_status",
    values="percentage",
    title="Order Status Distribution",
    hole=0.45,  # donut style — easier to read percentage labels
    template="plotly_white",
    color_discrete_sequence=px.colors.qualitative.Set2,
)
fig_pie.update_traces(textposition="outside", textinfo="percent+label")
fig_pie.update_layout(title_font_size=18, showlegend=True)

st.plotly_chart(fig_pie, use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Data source: "
    "[Olist E-Commerce Public Dataset on Kaggle]"
    "(https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) · "
    "Built with [Streamlit](https://streamlit.io) & [Plotly](https://plotly.com)"
)
