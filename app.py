import hashlib
import sqlite3
from datetime import date
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from pocketcfo.ai_extractor import InvoiceExtractionError, extract_invoice_fields
from pocketcfo.database import (
    DEFAULT_DATABASE_PATH,
    DuplicateRecordError,
    delete_invoice,
    delete_transaction,
    find_invoice_duplicate,
    initialize_database,
    list_invoices,
    list_transactions,
    record_invoice_payment,
    save_invoice,
    save_transaction,
    update_invoice,
    update_transaction,
)
from pocketcfo.pdf_extractor import PDFExtractionError, extract_pdf_text
from pocketcfo.reports import (
    DATE_FILTERS,
    currency_summary,
    dashboard_summary,
    filter_records_by_period,
    invoice_status,
    invoices_to_csv,
    monthly_cashflow,
    spending_by_category,
    transactions_to_csv,
)
from pocketcfo.validation import (
    InputValidationError,
    invoice_transaction_defaults,
    validate_invoice_input,
    validate_transaction_input,
)


st.set_page_config(
    page_title="PocketCFO AI",
    page_icon="P",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        --pc-ink: #17243b;
        --pc-muted: #748198;
        --pc-indigo: #4456c7;
        --pc-teal: #12a895;
        --pc-line: #e4eaf2;
        --pc-surface: #ffffff;
        --pc-canvas: #f3f6fb;
    }
    html, body, [class*="css"] {
        font-family: Inter, ui-sans-serif, system-ui, -apple-system,
                     BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .stApp {
        background:
            radial-gradient(ellipse at 86% 2%, rgba(68, 86, 199, .075), transparent 28rem),
            var(--pc-canvas);
        color: var(--pc-ink);
    }
    [data-testid="stHeader"] {
        background: rgba(243, 246, 251, .88);
    }
    [data-testid="stMainBlockContainer"] {
        max-width: 1480px;
        padding: 2rem clamp(1.25rem, 4vw, 3.75rem) 4rem;
    }
    section[data-testid="stSidebar"] {
        background: #111b32;
        border-right: 1px solid rgba(255, 255, 255, .08);
    }
    section[data-testid="stSidebar"] > div {
        background: linear-gradient(180deg, #111b32 0%, #172440 100%);
    }
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #aebbd1;
    }
    .brand-lockup {
        display: flex;
        align-items: center;
        gap: .75rem;
        padding: .5rem .25rem 1.25rem;
    }
    .brand-mark {
        display: grid;
        width: 2.6rem;
        height: 2.6rem;
        place-items: center;
        border-radius: .85rem;
        background: linear-gradient(145deg, #24c6ad, #4c62d5);
        box-shadow: 0 8px 24px rgba(18, 168, 149, .24);
        color: #fff;
        font-size: .82rem;
        font-weight: 800;
        letter-spacing: .03em;
    }
    .brand-name {
        color: #f7f9ff;
        font-size: 1.04rem;
        font-weight: 750;
        letter-spacing: -.025em;
    }
    .brand-subtitle {
        margin-top: .1rem;
        color: #93a2bb;
        font-size: .72rem;
    }
    section[data-testid="stSidebar"] [data-testid="stRadioGroup"] {
        gap: .35rem;
        margin-top: .45rem;
    }
    section[data-testid="stSidebar"] [data-testid="stRadioOption"] {
        min-height: 2.75rem;
        padding: .55rem .8rem;
        border: 1px solid transparent;
        border-radius: .8rem;
        background: transparent;
        transition: background .16s ease, border-color .16s ease;
    }
    section[data-testid="stSidebar"] [data-testid="stRadioOption"] p {
        color: #bdc9dc !important;
        font-size: .91rem;
        font-weight: 550;
    }
    section[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {
        border-color: rgba(255, 255, 255, .08);
        background: rgba(255, 255, 255, .07);
    }
    section[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {
        border-color: rgba(91, 214, 196, .22);
        background: linear-gradient(100deg, rgba(18, 168, 149, .22), rgba(68, 86, 199, .22));
        box-shadow: inset 3px 0 #37d0b9;
    }
    section[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p {
        color: #ffffff !important;
        font-weight: 700;
    }
    .sidebar-status {
        margin-top: .8rem;
        padding: .85rem .9rem;
        border: 1px solid rgba(255, 255, 255, .09);
        border-radius: .9rem;
        background: rgba(255, 255, 255, .045);
    }
    .sidebar-status-title {
        color: #eef3ff;
        font-size: .78rem;
        font-weight: 650;
    }
    .sidebar-status-copy {
        margin-top: .3rem;
        color: #9eacc3;
        font-size: .72rem;
        line-height: 1.5;
    }
    .page-heading {
        padding: .2rem 0 1.4rem;
    }
    .page-eyebrow {
        margin-bottom: .35rem;
        color: var(--pc-indigo);
        font-size: .7rem;
        font-weight: 800;
        letter-spacing: .13em;
        text-transform: uppercase;
    }
    .page-heading h1 {
        margin: 0;
        color: var(--pc-ink);
        font-size: clamp(1.8rem, 3vw, 2.45rem);
        font-weight: 760;
        letter-spacing: -.055em;
        line-height: 1.12;
    }
    .page-heading p {
        margin: .55rem 0 0;
        color: var(--pc-muted);
        font-size: .98rem;
        line-height: 1.55;
    }
    [data-testid="stMetric"] {
        min-height: 7.25rem;
        padding: 1.1rem 1.2rem;
        border: 1px solid var(--pc-line);
        border-radius: 1rem;
        background: var(--pc-surface);
        box-shadow: 0 4px 16px rgba(28, 46, 82, .035);
    }
    [data-testid="stMetricLabel"] p {
        color: var(--pc-muted);
        font-size: .78rem;
        font-weight: 650;
    }
    [data-testid="stMetricValue"] {
        color: var(--pc-ink);
        font-size: clamp(1.05rem, 1.6vw, 1.45rem);
        font-weight: 740;
        letter-spacing: -.04em;
    }
    [data-testid="stMetricDelta"] {
        font-size: .75rem;
    }
    h2, h3 {
        color: var(--pc-ink);
        letter-spacing: -.035em;
    }
    h2 {
        font-size: 1.3rem;
        font-weight: 730;
    }
    h3 {
        font-size: 1.04rem;
        font-weight: 700;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--pc-line);
        border-radius: 1rem;
        background: rgba(255, 255, 255, .84);
        box-shadow: 0 5px 22px rgba(28, 46, 82, .035);
    }
    [data-testid="stPlotlyChart"] {
        overflow: hidden;
        border: 1px solid var(--pc-line);
        border-radius: 1rem;
        background: #fff;
        padding: .45rem .55rem .1rem;
        box-shadow: 0 5px 22px rgba(28, 46, 82, .035);
    }
    [data-testid="stDataFrame"] {
        overflow: hidden;
        border: 1px solid var(--pc-line);
        border-radius: .9rem;
        background: #fff;
    }
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        border-color: #dce3ed;
        border-radius: .7rem;
        background: #fff;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: var(--pc-indigo);
        box-shadow: 0 0 0 3px rgba(68, 86, 199, .12);
    }
    [data-testid="stFileUploader"] section {
        border: 1.5px dashed #b8c5d9;
        border-radius: 1rem;
        background: linear-gradient(135deg, #f8faff, #f1fbfa);
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: var(--pc-teal);
        background: #f1fbfa;
    }
    [data-testid="stForm"] {
        padding: 1.25rem;
        border: 1px solid var(--pc-line);
        border-radius: 1rem;
        background: #fff;
        box-shadow: 0 5px 22px rgba(28, 46, 82, .035);
    }
    .stButton > button, [data-testid="stDownloadButton"] button {
        min-height: 2.7rem;
        border: 1px solid #dce3ed;
        border-radius: .72rem;
        background: #fff;
        color: var(--pc-ink);
        font-weight: 650;
        transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
    }
    .stButton > button:hover, [data-testid="stDownloadButton"] button:hover {
        transform: translateY(-1px);
        border-color: #9eacd0;
        box-shadow: 0 6px 15px rgba(28, 46, 82, .09);
        color: var(--pc-indigo);
    }
    .stButton > button[kind="primary"] {
        border-color: var(--pc-indigo);
        background: linear-gradient(105deg, #4456c7, #5568d7);
        color: #fff;
        box-shadow: 0 7px 18px rgba(68, 86, 199, .2);
    }
    .stButton > button[kind="primary"]:hover {
        border-color: #3548b8;
        background: #3548b8;
        color: #fff;
    }
    [data-testid="stAlert"] {
        border-radius: .8rem;
    }
    [data-testid="stExpander"] {
        overflow: hidden;
        border: 1px solid var(--pc-line);
        border-radius: .9rem;
        background: #fff;
    }
    .empty-state {
        padding: 1.45rem 1.55rem;
        border: 1px solid #dce7f0;
        border-radius: 1rem;
        background: linear-gradient(115deg, #fff 0%, #f2fbfa 100%);
        box-shadow: 0 8px 24px rgba(28, 46, 82, .04);
    }
    .empty-state-kicker {
        margin-bottom: .4rem;
        color: #168d80;
        font-size: .7rem;
        font-weight: 800;
        letter-spacing: .12em;
        text-transform: uppercase;
    }
    .empty-state-title {
        color: var(--pc-ink);
        font-size: 1.13rem;
        font-weight: 730;
        letter-spacing: -.025em;
    }
    .empty-state-copy {
        max-width: 48rem;
        margin-top: .42rem;
        color: var(--pc-muted);
        font-size: .91rem;
        line-height: 1.55;
    }
    .privacy-note {
        padding: .9rem 1rem;
        border-left: 3px solid var(--pc-teal);
        border-radius: 0 .7rem .7rem 0;
        background: #f0faf8;
        color: #466675;
        font-size: .86rem;
        line-height: 1.5;
    }
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: .4rem;
        padding: .38rem .7rem;
        border-radius: 999px;
        font-size: .78rem;
        font-weight: 700;
    }
    .status-paid {
        background: #e9f8f2;
        color: #187755;
    }
    .status-unpaid {
        background: #eef1ff;
        color: #4859bd;
    }
    .status-overdue {
        background: #fff1ec;
        color: #ad563d;
    }
    .upload-intro {
        padding: .35rem .15rem .8rem;
    }
    .upload-intro-title {
        color: var(--pc-ink);
        font-size: 1.18rem;
        font-weight: 740;
    }
    .upload-intro-copy {
        margin-top: .35rem;
        color: var(--pc-muted);
        font-size: .91rem;
        line-height: 1.55;
    }
    @media (max-width: 760px) {
        [data-testid="stMainBlockContainer"] {
            padding: 1.25rem 1rem 2.5rem;
        }
        .page-heading {
            padding-bottom: 1rem;
        }
        [data-testid="stMetric"] {
            min-height: 6.4rem;
            padding: .9rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.05rem;
        }
        [data-testid="stForm"] {
            padding: .85rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    initialize_database()
except (OSError, sqlite3.Error) as error:
    st.error(f"The local PocketCFO database could not be opened: {error}")
    st.stop()

with st.sidebar:
    st.markdown(
        """
        <div class="brand-lockup">
            <div class="brand-mark">PC</div>
            <div>
                <div class="brand-name">PocketCFO</div>
                <div class="brand-subtitle">Your independent finance desk</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    navigation_values = st.session_state.pop("navigation_values", {})
    for key, value in navigation_values.items():
        st.session_state[key] = value
    target_page = st.session_state.pop("navigate_to", None)
    if target_page:
        st.session_state["workspace_page"] = target_page
    page = st.radio(
        "Workspace",
        ("Dashboard", "Invoice intake", "Invoices", "Transactions", "Analytics & export"),
        format_func=lambda value: {
            "Dashboard": "▦   Dashboard",
            "Invoice intake": "↥   Invoice intake",
            "Invoices": "▤   Invoices",
            "Transactions": "↗   Transactions",
            "Analytics & export": "◫   Analytics & export",
        }[value],
        label_visibility="collapsed",
        key="workspace_page",
    )
    st.divider()
    st.markdown(
        f"""
        <div class="sidebar-status">
            <div class="sidebar-status-title">● &nbsp; Local-first workspace</div>
            <div class="sidebar-status-copy">
                AI model · qwen2.5:3b via Ollama<br>
                Records · {DEFAULT_DATABASE_PATH.name}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _invoice_label(invoice: dict[str, Any]) -> str:
    number = invoice["invoice_number"] or "no invoice number"
    return f"#{invoice['id']} · {invoice['vendor']} · {number}"


def _read_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        return list_invoices(), list_transactions()
    except sqlite3.Error as error:
        st.error(f"Could not read the local finance records: {error}")
        st.stop()
    return [], []


def _period_filter(
    label: str,
    key: str,
) -> tuple[str, date | None, date | None]:
    period = st.selectbox(label, DATE_FILTERS, key=key)
    if period != "Custom Range":
        return period, None, None

    today = date.today()
    selected = st.date_input(
        "Custom date range",
        value=(today.replace(day=1), today),
        key=f"{key}_dates",
    )
    if not isinstance(selected, (tuple, list)) or len(selected) != 2:
        st.info("Choose both a start and end date.")
        return period, None, None
    start_date, end_date = selected
    if end_date < start_date:
        st.error("The end date must be on or after the start date.")
        return period, None, None
    return period, start_date, end_date


def _filter_by_selected_period(
    records: list[dict[str, Any]],
    date_field: str,
    period: str,
    start_date: date | None,
    end_date: date | None,
) -> list[dict[str, Any]]:
    if period == "Custom Range" and (start_date is None or end_date is None):
        return []
    return filter_records_by_period(
        records,
        date_field,
        period,
        start_date=start_date,
        end_date=end_date,
    )


def _render_page_header(
    *,
    title: str,
    description: str,
    eyebrow: str,
    action_label: str,
    action_destination: str,
) -> None:
    left, right = st.columns([5, 1.65], vertical_alignment="center")
    with left:
        st.markdown(
            f"""
            <div class="page-heading">
                <div class="page-eyebrow">{eyebrow}</div>
                <h1>{title}</h1>
                <p>{description}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        if st.button(
            action_label,
            key=f"header_action_{action_destination}",
            type="primary",
            width="stretch",
        ):
            st.session_state["navigate_to"] = action_destination
            st.rerun()


def _invoice_fields_form(
    *,
    form_key: str,
    values: dict[str, Any],
    button_label: str,
) -> dict[str, Any] | None:
    with st.form(form_key):
        left, right = st.columns(2)
        with left:
            vendor = st.text_input("Vendor / supplier *", value=values.get("vendor") or "")
            invoice_number = st.text_input(
                "Invoice number",
                value=values.get("invoice_number") or "",
            )
            issue_date = st.text_input(
                "Issue date (YYYY-MM-DD)",
                value=values.get("issue_date") or "",
            )
            due_date = st.text_input(
                "Due date (YYYY-MM-DD)",
                value=values.get("due_date") or "",
            )
        with right:
            currency = st.text_input(
                "Currency code *",
                value=values.get("currency") or "",
                help="Enter the three-letter currency shown on the invoice, such as USD.",
            )
            total_amount = st.text_input(
                "Invoice total *",
                value=values.get("total_amount") or "",
                help="Enter the number only. Do not include the currency symbol.",
            )
            tax_amount = st.text_input(
                "Tax amount",
                value=values.get("tax_amount") or "",
            )
        notes = st.text_area("Notes", value=values.get("notes") or "")
        submitted = st.form_submit_button(button_label, type="primary")

    if not submitted:
        return None
    return {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "issue_date": issue_date,
        "due_date": due_date,
        "currency": currency,
        "total_amount": total_amount,
        "tax_amount": tax_amount,
        "notes": notes,
    }


def _render_dashboard(
    invoices: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> None:
    period, start_date, end_date = _period_filter("Date range", "dashboard_period")
    filtered_transactions = _filter_by_selected_period(
        transactions, "transaction_date", period, start_date, end_date
    )
    filtered_invoices = _filter_by_selected_period(
        invoices, "issue_date", period, start_date, end_date
    )
    summary = dashboard_summary(filtered_invoices, filtered_transactions)
    currency_names = list(summary["currencies"])

    def render_totals(values: dict[str, Any], kind: str | None = None) -> str:
        return " · ".join(
            f"{currency} {(amount if kind is None else amount[kind]):,.2f}"
            for currency, amount in values.items()
        ) or "—"

    metric_columns = st.columns(4)
    metric_details = (
        ("↗  Income received", "income"),
        ("↘  Expenses recorded", "expenses"),
        ("≈  Net cash flow", "net"),
    )
    for column, (label, field) in zip(metric_columns, metric_details):
        with column:
            st.metric(label, render_totals(summary["currencies"], field))
    with metric_columns[3]:
        st.metric(
            "◷  Outstanding invoices",
            render_totals(summary["outstanding_by_currency"]),
        )

    st.caption(
        "Financial totals use saved transactions only. An invoice is never treated "
        "as income or payment automatically; currencies are shown separately."
    )
    st.markdown("#### Payment follow-up")
    overdue_columns = st.columns(2)
    with overdue_columns[0]:
        st.metric(
            "⚠  Overdue invoices",
            summary["overdue_count"],
            help="Unpaid invoices whose due date is before today.",
        )
    with overdue_columns[1]:
        st.metric(
            "◷  Overdue amount",
            render_totals(summary["overdue_by_currency"]),
        )
    st.caption(f"Confirmed invoices in this period: {summary['invoice_count']}")

    if not filtered_transactions:
        st.markdown(
            """
            <div class="empty-state">
                <div class="empty-state-kicker">A clear starting point</div>
                <div class="empty-state-title">Your cash-flow story starts here</div>
                <div class="empty-state-copy">
                    There are no transactions in this date range yet. Add a real
                    income or expense to bring your dashboard to life, or review
                    invoices and explicitly record a payment. No sample numbers
                    are shown.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        action_columns = st.columns([1.15, 1.15, 3.7])
        with action_columns[0]:
            if st.button(
                "＋  Add transaction",
                key="dashboard_empty_add_transaction",
                type="primary",
                width="stretch",
            ):
                st.session_state["navigate_to"] = "Transactions"
                st.rerun()
        with action_columns[1]:
            destination = "Invoices" if invoices else "Invoice intake"
            label = "Review invoices" if invoices else "Upload an invoice"
            if st.button(
                label,
                key="dashboard_empty_invoice_action",
                width="stretch",
            ):
                st.session_state["navigate_to"] = destination
                st.rerun()
    else:
        st.markdown("#### Cash flow")
        if not currency_names:
            st.info("No transaction totals are available for this date range.")
        else:
            currency = st.selectbox(
                "Chart currency",
                currency_names,
                key="dashboard_chart_currency",
            )
            selected_totals = summary["currencies"][currency]
            comparison = pd.DataFrame(
                [
                    {"kind": "Income", "amount": float(selected_totals["income"])},
                    {"kind": "Expenses", "amount": float(selected_totals["expenses"])},
                ]
            )
            monthly = monthly_cashflow(filtered_transactions, currency)
            chart_columns = st.columns(2)
            with chart_columns[0]:
                comparison_chart = px.bar(
                    comparison,
                    x="kind",
                    y="amount",
                    color="kind",
                    title=f"Income vs. expenses · {currency}",
                    labels={"kind": "Type", "amount": currency},
                    color_discrete_map={
                        "Income": "#12a895",
                        "Expenses": "#e28b73",
                    },
                )
                comparison_chart.update_layout(
                    template="plotly_white",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font={"family": "Inter, sans-serif", "color": "#53627a"},
                    title={"font": {"size": 15, "color": "#17243b"}},
                    margin={"l": 12, "r": 12, "t": 58, "b": 20},
                    showlegend=False,
                    yaxis={"gridcolor": "#edf1f6", "zeroline": False},
                )
                st.plotly_chart(
                    comparison_chart,
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                )
            with chart_columns[1]:
                if monthly.empty:
                    st.info(f"No {currency} transactions in this date range.")
                else:
                    monthly_chart = px.bar(
                        monthly.assign(amount=monthly["amount"].map(float)),
                        x="month",
                        y="amount",
                        color="kind",
                        barmode="group",
                        title=f"Monthly cash flow · {currency}",
                        labels={"month": "Month", "amount": currency, "kind": "Type"},
                        color_discrete_map={
                            "income": "#12a895",
                            "expense": "#e28b73",
                        },
                    )
                    monthly_chart.update_layout(
                        template="plotly_white",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font={"family": "Inter, sans-serif", "color": "#53627a"},
                        title={"font": {"size": 15, "color": "#17243b"}},
                        margin={"l": 12, "r": 12, "t": 58, "b": 20},
                        legend={"orientation": "h", "y": 1.12, "x": 0},
                        yaxis={"gridcolor": "#edf1f6", "zeroline": False},
                    )
                    st.plotly_chart(
                        monthly_chart,
                        width="stretch",
                        config={"displayModeBar": False, "responsive": True},
                    )

            category_totals = spending_by_category(filtered_transactions, currency)
            st.markdown("#### Spending by category")
            if category_totals.empty:
                st.info(f"No {currency} expenses in this date range.")
            else:
                category_chart = px.bar(
                    category_totals.assign(
                        amount=category_totals["amount"].map(float)
                    ),
                    x="category",
                    y="amount",
                    title=f"Expenses by category · {currency}",
                    labels={"category": "Category", "amount": currency},
                    color_discrete_sequence=["#5368d5"],
                )
                category_chart.update_layout(
                    template="plotly_white",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font={"family": "Inter, sans-serif", "color": "#53627a"},
                    title={"font": {"size": 15, "color": "#17243b"}},
                    margin={"l": 12, "r": 12, "t": 58, "b": 20},
                    showlegend=False,
                    xaxis={"gridcolor": "#edf1f6"},
                )
                st.plotly_chart(
                    category_chart,
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                )

    st.markdown("#### Your recent activity")
    invoice_column, transaction_column = st.columns(2)
    with invoice_column:
        overdue_invoices = [
            invoice
            for invoice in filtered_invoices
            if invoice_status(invoice) == "Overdue"
        ]
        st.markdown("##### Invoices requiring attention")
        if not overdue_invoices:
            st.caption("No overdue invoices in this date range.")
        for invoice in overdue_invoices[:5]:
            st.warning(
                f"{_invoice_label(invoice)} · {invoice['currency']} "
                f"{invoice['total_amount']} · due {invoice['due_date']}"
            )
        st.markdown("##### Recent invoices")
        if not filtered_invoices:
            st.caption("No saved invoices for this date range.")
        for invoice in filtered_invoices[:5]:
            if st.button(
                f"Open invoice #{invoice['id']} · {invoice['vendor']} · "
                f"{invoice['currency']} {invoice['total_amount']} · "
                f"{invoice_status(invoice)}",
                key=f"dashboard_invoice_{invoice['id']}",
                width="stretch",
            ):
                st.session_state["navigate_to"] = "Invoices"
                st.session_state["navigation_values"] = {
                    "invoice_to_edit": invoice["id"]
                }
                st.rerun()
    with transaction_column:
        st.markdown("##### Recent transactions")
        if not filtered_transactions:
            st.caption("No saved transactions for this date range.")
        for transaction in filtered_transactions[:5]:
            if st.button(
                f"Open transaction #{transaction['id']} · "
                f"{transaction['description']} · {transaction['currency']} "
                f"{transaction['amount']}",
                key=f"dashboard_transaction_{transaction['id']}",
                width="stretch",
            ):
                st.session_state["navigate_to"] = "Transactions"
                st.session_state["navigation_values"] = {
                    "transaction_to_edit": transaction["id"]
                }
                st.rerun()


def _render_invoice_intake() -> None:
    with st.container(border=True):
        st.markdown(
            """
            <div class="upload-intro">
                <div class="upload-intro-title">Turn an invoice into a reviewable draft</div>
                <div class="upload-intro-copy">
                    Select a text-based PDF and PocketCFO will prepare fields for
                    you to verify. Your original file stays in memory and is not
                    added to the database.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        model_col, limit_col = st.columns(2)
        with model_col:
            st.markdown(
                '<div class="privacy-note"><strong>Local AI</strong> · '
                "Extraction runs through qwen2.5:3b in your local Ollama service. "
                "Invoice text is not sent to a hosted AI API.</div>",
                unsafe_allow_html=True,
            )
        with limit_col:
            st.markdown(
                '<div class="privacy-note"><strong>PDF limit</strong> · '
                "Up to 10 MB. Scanned image-only files need OCR, which is not "
                "included.</div>",
                unsafe_allow_html=True,
            )
        st.write("")
        uploaded_pdf = st.file_uploader(
            "Choose a PDF invoice",
            type=["pdf"],
            help="PDFs are limited to 10 MB and processed locally in memory.",
            max_upload_size=10,
            key="invoice_pdf_upload",
        )
    if uploaded_pdf is None:
        st.caption(
            "No file is uploaded until you choose one. You can also enter invoice "
            "details manually without Ollama."
        )
        if st.button(
            "Enter invoice manually",
            key="invoice_intake_manual_entry",
        ):
            st.session_state["navigate_to"] = "Invoices"
            st.rerun()
        return

    pdf_bytes = uploaded_pdf.getvalue()
    document_hash = hashlib.sha256(pdf_bytes).hexdigest()
    try:
        extracted_text = extract_pdf_text(uploaded_pdf.name, pdf_bytes)
    except PDFExtractionError as error:
        st.error(str(error))
        return

    st.success("PDF text extracted. Compare the draft with the original invoice.")
    with st.expander("Show extracted PDF text"):
        st.text_area(
            "Selectable PDF text",
            value=extracted_text,
            height=240,
            disabled=True,
        )

    existing_draft = st.session_state.get("invoice_draft")
    if existing_draft and existing_draft["document_sha256"] != document_hash:
        st.warning(
            "The uploaded PDF differs from the unsaved draft. The old draft has not "
            "been saved; discard it to continue with this PDF."
        )
        if st.button(
            "Discard previous draft and continue",
            key=f"discard_previous_draft_{document_hash[:12]}",
        ):
            st.session_state.pop("invoice_draft", None)
            st.rerun()
        return

    if st.button("Extract fields with local Ollama", type="primary"):
        with st.spinner("Asking qwen2.5:3b to read the invoice text locally..."):
            try:
                extracted = extract_invoice_fields(extracted_text)
            except InvoiceExtractionError as error:
                st.error(str(error))
            else:
                st.session_state["invoice_draft"] = {
                    **extracted,
                    "document_sha256": document_hash,
                }
                st.rerun()

    draft = st.session_state.get("invoice_draft")
    if not draft:
        return

    st.markdown("### Review before saving")
    st.warning(
        "AI-extracted values are suggestions, not verified financial facts. "
        "Check every field against the original invoice."
    )
    if draft["review_fields"]:
        labels = ", ".join(field.replace("_", " ") for field in draft["review_fields"])
        st.info(f"Please pay special attention to missing, uncertain, or invalid fields: {labels}.")
    for warning in draft["warnings"]:
        st.warning(warning)

    with st.expander("Model confidence estimates"):
        st.caption(
            "These are the model's estimates, not guarantees. Low or missing confidence "
            "is highlighted above."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Field": field.replace("_", " ").title(),
                        "Model confidence": f"{score:.0%}",
                    }
                    for field, score in draft["confidence"].items()
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    values = dict(draft["fields"])
    submitted_fields = _invoice_fields_form(
        form_key=f"review_invoice_{document_hash[:12]}",
        values=values,
        button_label="Confirm and save invoice",
    )
    if submitted_fields is None:
        st.caption("* Vendor, currency, and total are required to save.")
        return

    try:
        validated = validate_invoice_input(submitted_fields)
        duplicate = find_invoice_duplicate(
            validated,
            document_sha256=document_hash,
        )
        if duplicate:
            st.error(
                f"This appears to duplicate invoice #{duplicate['id']} "
                f"for {duplicate['vendor']}. Review the saved invoice instead."
            )
            return
        saved_id = save_invoice(
            validated,
            document_sha256=document_hash,
        )
    except InputValidationError as error:
        st.error(str(error))
    except DuplicateRecordError as error:
        st.error(str(error))
    except sqlite3.Error as error:
        st.error(f"The invoice could not be saved to SQLite: {error}")
    else:
        st.success(f"Invoice #{saved_id} saved after your confirmation.")
        st.session_state.pop("invoice_draft", None)
        st.rerun()


def _render_invoices(
    invoices: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> None:
    st.markdown("### Your invoices")
    with st.expander("Add invoice manually", expanded=not invoices):
        submitted = _invoice_fields_form(
            form_key="manual_invoice",
            values={},
            button_label="Save invoice",
        )
        if submitted is not None:
            try:
                validated = validate_invoice_input(submitted)
                duplicate = find_invoice_duplicate(validated)
                if duplicate:
                    st.error(
                        f"This matches invoice #{duplicate['id']} "
                        f"for {duplicate['vendor']}."
                    )
                else:
                    saved_id = save_invoice(validated)
            except InputValidationError as error:
                st.error(str(error))
            except DuplicateRecordError as error:
                st.error(str(error))
            except sqlite3.Error as error:
                st.error(f"The invoice could not be saved: {error}")
            else:
                if not duplicate:
                    st.success(f"Invoice #{saved_id} saved.")
                    st.rerun()

    if not invoices:
        st.markdown(
            """
            <div class="empty-state">
                <div class="empty-state-kicker">Invoice workspace</div>
                <div class="empty-state-title">No invoices saved yet</div>
                <div class="empty-state-copy">
                    Add invoice details manually above, or review a PDF draft
                    prepared with your local Ollama model. An invoice will not be
                    counted as received income unless you confirm its payment.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            "Upload a PDF invoice",
            key="invoices_empty_upload",
            type="primary",
        ):
            st.session_state["navigate_to"] = "Invoice intake"
            st.rerun()
        return

    filter_search, filter_status = st.columns([2, 1])
    with filter_search:
        search = st.text_input(
            "Search invoices",
            placeholder="Vendor or invoice number",
            key="invoice_search",
        ).strip().casefold()
    with filter_status:
        status_filter = st.selectbox(
            "Invoice status",
            ("All statuses", "Unpaid", "Overdue", "Paid"),
            key="invoice_status_filter",
        )
    visible_invoices = [
        invoice
        for invoice in invoices
        if (
            not search
            or search in str(invoice["vendor"]).casefold()
            or search in str(invoice["invoice_number"] or "").casefold()
        )
        and (
            status_filter == "All statuses"
            or invoice_status(invoice) == status_filter
        )
    ]
    if not visible_invoices:
        st.info("No invoices match the current search and status filters.")
        return

    view = pd.DataFrame(visible_invoices)
    view["status"] = view.apply(
        lambda row: invoice_status(row.to_dict()),
        axis=1,
    )
    linked_transactions = {
        transaction["invoice_id"]: transaction["id"]
        for transaction in transactions
        if transaction["invoice_id"] is not None
    }
    view["linked_transaction"] = view["id"].map(
        lambda invoice_id: linked_transactions.get(invoice_id, "Not created")
    )
    st.dataframe(
        view[
            [
                "id",
                "vendor",
                "invoice_number",
                "issue_date",
                "due_date",
                "total_amount",
                "currency",
                "status",
                "linked_transaction",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
    selected_id = st.selectbox(
        "Choose an invoice to edit or delete",
        [invoice["id"] for invoice in visible_invoices],
        format_func=lambda invoice_id: _invoice_label(
            next(item for item in visible_invoices if item["id"] == invoice_id)
        ),
        key="invoice_to_edit",
    )
    selected = next(
        invoice for invoice in visible_invoices if invoice["id"] == selected_id
    )
    linked_transaction_id = linked_transactions.get(selected_id)
    selected_status = invoice_status(selected)
    status_class = {
        "Paid": "status-paid",
        "Unpaid": "status-unpaid",
        "Overdue": "status-overdue",
    }[selected_status]
    st.markdown(
        f'<span class="status-pill {status_class}">● &nbsp; {selected_status}</span>',
        unsafe_allow_html=True,
    )
    if selected_status == "Paid":
        st.success(
            f"Payment confirmed on {selected['paid_date']}. "
            f"Linked income transaction #{linked_transaction_id}."
        )
    else:
        st.info(
            "Unpaid invoices are not income. Overdue means an unpaid invoice has "
            "a due date before today."
        )
        with st.container(border=True):
            st.markdown("##### Confirm payment received")
            with st.form(f"confirm_invoice_payment_{selected_id}"):
                payment_date = st.date_input(
                    "Payment received on",
                    value=date.today(),
                )
                st.caption(
                    (
                        "Confirming updates the date and paid status of the existing "
                        "linked income transaction."
                        if linked_transaction_id is not None
                        else "Confirming creates one linked income transaction."
                    )
                    + f" Amount: {selected['currency']} {selected['total_amount']} "
                    f"({selected['invoice_number'] or 'no invoice number'})."
                )
                payment_submitted = st.form_submit_button(
                    "Mark paid and create income",
                    type="primary",
                )
        if payment_submitted:
            try:
                transaction_id = record_invoice_payment(
                    selected_id,
                    payment_date.isoformat(),
                )
            except (InputValidationError, DuplicateRecordError, ValueError) as error:
                st.error(str(error))
            except sqlite3.Error as error:
                st.error(f"Payment could not be recorded: {error}")
            else:
                st.success(
                    f"Invoice marked paid with linked income transaction "
                    f"#{transaction_id}."
                )
                st.rerun()

    if linked_transaction_id is None:
        if st.button(
            "Create transaction",
            key=f"create_transaction_from_invoice_{selected_id}",
            type="primary",
        ):
            st.session_state["pending_invoice_id"] = selected_id
            st.session_state["navigate_to"] = "Transactions"
            st.rerun()
        st.caption(
            "Creating a transaction does not mark the invoice as paid. "
            "You must choose Income or Expense and confirm the transaction details."
        )
    elif selected_status != "Paid":
        st.info(
            f"Transaction #{linked_transaction_id} is already linked to this invoice."
        )

    with st.expander("Edit invoice details"):
        submitted = _invoice_fields_form(
            form_key=f"edit_invoice_{selected_id}",
            values=selected,
            button_label="Save invoice changes",
        )
    if submitted is not None:
        try:
            update_invoice(selected_id, submitted)
        except InputValidationError as error:
            st.error(str(error))
        except DuplicateRecordError as error:
            st.error(str(error))
        except ValueError as error:
            st.error(str(error))
        except sqlite3.Error as error:
            st.error(f"The invoice changes could not be saved: {error}")
        else:
            st.success(f"Invoice #{selected_id} updated.")
            st.rerun()

    if st.checkbox(
        "I understand that deleting this invoice cannot be undone.",
        key=f"confirm_delete_invoice_{selected_id}",
    ):
        if st.button("Delete invoice", key=f"delete_invoice_{selected_id}"):
            try:
                delete_invoice(selected_id)
            except sqlite3.Error as error:
                st.error(f"The invoice could not be deleted: {error}")
            else:
                st.success(f"Invoice #{selected_id} deleted.")
                st.rerun()


def _render_transactions(
    invoices: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> None:
    st.markdown(
        """
        <div class="privacy-note">
            <strong>Recorded cash only</strong> · Add money actually received or
            spent. An invoice is not automatically considered paid or counted
            as income.
        </div>
        """,
        unsafe_allow_html=True,
    )
    invoice_options: list[int | None] = [None] + [invoice["id"] for invoice in invoices]
    pending_invoice_id = st.session_state.get("pending_invoice_id")
    pending_invoice = next(
        (
            invoice
            for invoice in invoices
            if invoice["id"] == pending_invoice_id
        ),
        None,
    )
    if pending_invoice is None and pending_invoice_id is not None:
        st.error("The invoice selected for conversion no longer exists.")
        st.session_state.pop("pending_invoice_id", None)

    if pending_invoice is not None:
        st.info(
            f"Creating a transaction from invoice #{pending_invoice['id']} "
            f"({pending_invoice['vendor']}). This does not imply payment."
        )
        transaction_defaults = {
            "transaction_date": pending_invoice["issue_date"] or "",
            "description": pending_invoice["vendor"],
            "category": "",
            "amount": pending_invoice["total_amount"],
            "currency": pending_invoice["currency"],
        }
    else:
        transaction_defaults = {
            "transaction_date": "",
            "description": "",
            "category": "",
            "amount": "",
            "currency": "",
        }

    st.markdown("### Add a transaction")
    with st.form(
        f"new_transaction_from_invoice_{pending_invoice_id}"
        if pending_invoice is not None
        else "new_transaction"
    ):
        first, second = st.columns(2)
        with first:
            kind_choice = st.selectbox(
                "Type *",
                ("Choose Income or Expense", "income", "expense"),
                format_func=lambda value: {
                    "Choose Income or Expense": "Choose Income or Expense",
                    "income": "Income",
                    "expense": "Expense",
                }[value],
            )
            transaction_date = st.text_input(
                "Date (YYYY-MM-DD) *",
                value=transaction_defaults["transaction_date"],
            )
            description = st.text_input(
                "Vendor / description *",
                value=transaction_defaults["description"],
            )
            category = st.text_input(
                "Category",
                value=transaction_defaults["category"],
            )
        with second:
            amount = st.text_input(
                "Amount *",
                value=transaction_defaults["amount"],
                help="Use a positive number.",
            )
            currency = st.text_input(
                "Currency code *",
                value=transaction_defaults["currency"],
                help="For example USD.",
            )
            if pending_invoice is None:
                invoice_id = st.selectbox(
                    "Related invoice (optional)",
                    invoice_options,
                    format_func=lambda value: (
                        "No linked invoice"
                        if value is None
                        else _invoice_label(
                            next(item for item in invoices if item["id"] == value)
                        )
                    ),
                )
            else:
                invoice_id = pending_invoice["id"]
                st.caption(f"Linked invoice: {_invoice_label(pending_invoice)}")
        add_transaction = st.form_submit_button(
            "Create transaction" if pending_invoice is not None else "Save transaction",
            type="primary",
        )
    if add_transaction:
        kind = None if kind_choice == "Choose Income or Expense" else kind_choice
        try:
            if pending_invoice is not None:
                transaction_fields = invoice_transaction_defaults(
                    pending_invoice, kind
                )
                transaction_fields.update(
                    {
                        "transaction_date": transaction_date,
                        "description": description,
                        "category": category,
                        "amount": amount,
                        "currency": currency,
                    }
                )
            else:
                transaction_fields = {
                    "kind": kind,
                    "transaction_date": transaction_date,
                    "description": description,
                    "category": category,
                    "amount": amount,
                    "currency": currency,
                    "invoice_id": invoice_id,
                }
            transaction = validate_transaction_input(transaction_fields)
            saved_id = save_transaction(transaction)
        except InputValidationError as error:
            st.error(str(error))
        except DuplicateRecordError as error:
            st.error(str(error))
        except sqlite3.Error as error:
            st.error(f"The transaction could not be saved: {error}")
        else:
            st.success(f"Transaction #{saved_id} saved.")
            st.session_state.pop("pending_invoice_id", None)
            st.rerun()

    if not transactions:
        st.markdown(
            """
            <div class="empty-state">
                <div class="empty-state-kicker">Transaction ledger</div>
                <div class="empty-state-title">Your first entry sets the baseline</div>
                <div class="empty-state-copy">
                    Save an actual income or expense above. Your dashboard and
                    reports will use only recorded transactions, with each
                    currency kept separate.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    filter_search, filter_type = st.columns([2, 1])
    with filter_search:
        search = st.text_input(
            "Search transactions",
            placeholder="Description or category",
            key="transaction_search",
        ).strip().casefold()
    with filter_type:
        type_filter = st.selectbox(
            "Transaction type",
            ("All types", "income", "expense"),
            key="transaction_type_filter",
        )
    currency_options = sorted({item["currency"] for item in transactions})
    category_options = sorted(
        {
            item["category"] or "Uncategorized"
            for item in transactions
        }
    )
    currency_filter_col, category_filter_col, period_filter_col = st.columns(3)
    with currency_filter_col:
        currency_filter = st.selectbox(
            "Currency",
            ("All currencies", *currency_options),
            key="transaction_currency_filter",
        )
    with category_filter_col:
        category_filter = st.selectbox(
            "Category",
            ("All categories", *category_options),
            key="transaction_category_filter",
        )
    with period_filter_col:
        period, start_date, end_date = _period_filter(
            "Transaction date range",
            "transaction_period",
        )
    visible_transactions = _filter_by_selected_period(
        transactions,
        "transaction_date",
        period,
        start_date,
        end_date,
    )
    visible_transactions = [
        transaction
        for transaction in visible_transactions
        if (
            not search
            or search in str(transaction["description"]).casefold()
            or search in str(transaction["category"] or "").casefold()
        )
        and (
            type_filter == "All types"
            or transaction["kind"] == type_filter
        )
        and (
            currency_filter == "All currencies"
            or transaction["currency"] == currency_filter
        )
        and (
            category_filter == "All categories"
            or (transaction["category"] or "Uncategorized") == category_filter
        )
    ]
    st.download_button(
        "Download filtered transactions CSV",
        data=transactions_to_csv(visible_transactions),
        file_name="pocketcfo_transactions.csv",
        mime="text/csv",
        disabled=not visible_transactions,
    )
    if not visible_transactions:
        st.info("No transactions match the current search and filters.")
        return

    st.markdown("#### Filtered transactions")
    transaction_frame = pd.DataFrame(visible_transactions)
    transaction_frame["related_invoice"] = transaction_frame["invoice_id"].map(
        lambda invoice_id: (
            "Not linked"
            if invoice_id is None
            else _invoice_label(
                next(item for item in invoices if item["id"] == invoice_id)
            )
        )
    )
    st.dataframe(
        transaction_frame[
            [
                "id",
                "transaction_date",
                "kind",
                "description",
                "category",
                "amount",
                "currency",
                "related_invoice",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
    selected_id = st.selectbox(
        "Choose a transaction to edit or delete",
        [transaction["id"] for transaction in visible_transactions],
        format_func=lambda transaction_id: (
            f"#{transaction_id} · "
            f"{next(item for item in visible_transactions if item['id'] == transaction_id)['transaction_date']} · "
            f"{next(item for item in visible_transactions if item['id'] == transaction_id)['description']}"
        ),
        key="transaction_to_edit",
    )
    selected = next(
        item for item in visible_transactions if item["id"] == selected_id
    )
    with st.expander("Edit selected transaction"):
        with st.form(f"edit_transaction_{selected_id}"):
            first, second = st.columns(2)
            with first:
                edit_kind = st.selectbox(
                    "Type",
                    ("income", "expense"),
                    index=("income", "expense").index(selected["kind"]),
                    key=f"edit_kind_{selected_id}",
                )
                edit_date = st.text_input(
                    "Date (YYYY-MM-DD) *",
                    value=selected["transaction_date"],
                    key=f"edit_date_{selected_id}",
                )
                edit_description = st.text_input(
                    "Description *",
                    value=selected["description"],
                    key=f"edit_description_{selected_id}",
                )
                edit_category = st.text_input(
                    "Category",
                    value=selected["category"] or "",
                    key=f"edit_category_{selected_id}",
                )
            with second:
                edit_amount = st.text_input(
                    "Amount *",
                    value=selected["amount"],
                    key=f"edit_amount_{selected_id}",
                )
                edit_currency = st.text_input(
                    "Currency code *",
                    value=selected["currency"],
                    key=f"edit_currency_{selected_id}",
                )
                edit_invoice_id = st.selectbox(
                    "Related invoice (optional)",
                    invoice_options,
                    index=invoice_options.index(selected["invoice_id"]),
                    format_func=lambda value: (
                        "No linked invoice"
                        if value is None
                        else _invoice_label(
                            next(item for item in invoices if item["id"] == value)
                        )
                    ),
                    key=f"edit_invoice_link_{selected_id}",
                )
            update_submitted = st.form_submit_button("Save transaction changes")
    if update_submitted:
        try:
            update_transaction(
                selected_id,
                {
                    "kind": edit_kind,
                    "transaction_date": edit_date,
                    "description": edit_description,
                    "category": edit_category,
                    "amount": edit_amount,
                    "currency": edit_currency,
                    "invoice_id": edit_invoice_id,
                },
            )
        except InputValidationError as error:
            st.error(str(error))
        except DuplicateRecordError as error:
            st.error(str(error))
        except sqlite3.Error as error:
            st.error(f"The transaction changes could not be saved: {error}")
        else:
            st.success(f"Transaction #{selected_id} updated.")
            st.rerun()

    if st.checkbox(
        "I understand that deleting this transaction cannot be undone.",
        key=f"confirm_delete_transaction_{selected_id}",
    ):
        if st.button("Delete transaction", key=f"delete_transaction_{selected_id}"):
            try:
                delete_transaction(selected_id)
            except sqlite3.Error as error:
                st.error(f"The transaction could not be deleted: {error}")
            else:
                st.success(f"Transaction #{selected_id} deleted.")
                st.rerun()


def _render_analytics(
    invoices: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> None:
    st.markdown(
        """
        <div class="privacy-note">
            <strong>Read your real cash flow</strong> · Income and expenses come
            from recorded transactions, not invoice totals. Each currency is
            reported separately.
        </div>
        """,
        unsafe_allow_html=True,
    )
    period, start_date, end_date = _period_filter(
        "Report date range",
        "analytics_period",
    )
    filtered_transactions = _filter_by_selected_period(
        transactions,
        "transaction_date",
        period,
        start_date,
        end_date,
    )
    filtered_invoices = _filter_by_selected_period(
        invoices,
        "issue_date",
        period,
        start_date,
        end_date,
    )
    summary = currency_summary(filtered_transactions)
    if summary.empty:
        st.markdown(
            """
            <div class="empty-state">
                <div class="empty-state-kicker">Analytics</div>
                <div class="empty-state-title">Nothing to chart for this period</div>
                <div class="empty-state-copy">
                    Once you record income or expenses, currency-separated
                    summaries and monthly comparisons will appear here.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown("### Cash flow by currency")
        st.dataframe(summary, width="stretch", hide_index=True)
        currency = st.selectbox("Chart currency", summary["currency"].tolist())
        chart_data = monthly_cashflow(filtered_transactions, currency)
        if not chart_data.empty:
            plot_data = chart_data.assign(amount=chart_data["amount"].map(float))
            chart = px.bar(
                plot_data,
                x="month",
                y="amount",
                color="kind",
                barmode="group",
                title=f"Monthly cash flow · {currency}",
                labels={"month": "Month", "amount": currency, "kind": "Type"},
                color_discrete_map={"income": "#12a895", "expense": "#e28b73"},
            )
            chart.update_layout(
                template="plotly_white",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font={"family": "Inter, sans-serif", "color": "#53627a"},
                title={"font": {"size": 15, "color": "#17243b"}},
                margin={"l": 12, "r": 12, "t": 58, "b": 20},
                legend={"orientation": "h", "y": 1.12, "x": 0},
                yaxis={"gridcolor": "#edf1f6", "zeroline": False},
            )
            st.plotly_chart(
                chart,
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
            )

    st.markdown("### Export your records")
    st.caption(
        "Exports are generated in memory and include only records in the selected "
        "date range."
    )
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("##### Transactions")
            st.caption("Income and expenses recorded in the selected period.")
            st.download_button(
                "Download transactions CSV",
                data=transactions_to_csv(filtered_transactions),
                file_name="pocketcfo_transactions.csv",
                mime="text/csv",
                disabled=not filtered_transactions,
                width="stretch",
            )
    with right:
        with st.container(border=True):
            st.markdown("##### Invoices")
            st.caption("Invoices issued in the selected period, separate from cash.")
            st.download_button(
                "Download invoices CSV",
                data=invoices_to_csv(filtered_invoices),
                file_name="pocketcfo_invoices.csv",
                mime="text/csv",
                disabled=not filtered_invoices,
                width="stretch",
            )
    st.caption(
        "Invoice dates are filtered by issue date; unpaid invoices are not counted "
        "as received income."
    )


invoices, transactions = _read_records()
page_descriptions = {
    "Dashboard": "A live view of confirmed income, recorded expenses, and invoices to follow up.",
    "Invoice intake": "Review extracted invoice details before saving them.",
    "Invoices": "Review invoice status, follow up on payments, and record money received.",
    "Transactions": "Record, find, and manage money actually received or spent.",
    "Analytics & export": "Explore currency-separated cash flow and export filtered records.",
}
page_headers = {
    "Dashboard": ("YOUR FINANCE OVERVIEW", "＋  Add transaction", "Transactions"),
    "Invoice intake": ("INVOICE WORKFLOW", "View saved invoices", "Invoices"),
    "Invoices": ("INVOICE WORKFLOW", "＋  Upload invoice", "Invoice intake"),
    "Transactions": ("CASH LEDGER", "View invoices", "Invoices"),
    "Analytics & export": ("REPORTING", "＋  Add transaction", "Transactions"),
}
eyebrow, action_label, action_destination = page_headers[page]
_render_page_header(
    title=page,
    description=page_descriptions[page],
    eyebrow=eyebrow,
    action_label=action_label,
    action_destination=action_destination,
)

if page == "Dashboard":
    _render_dashboard(invoices, transactions)
elif page == "Invoice intake":
    _render_invoice_intake()
elif page == "Invoices":
    _render_invoices(invoices, transactions)
elif page == "Transactions":
    _render_transactions(invoices, transactions)
else:
    _render_analytics(invoices, transactions)
