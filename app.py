"""
GrowthLock SVRP Return Model
============================
Interactive return model for the Syndication Velocity Returns Program.

Defaults reflect the conservative scenario discussed (10% default rate,
50% recovery, 50% of payments collected before default, 3% servicing fee,
1.45 factor, 110-day cycles). Sliders allow stress-testing in either direction.

Run locally:    streamlit run app.py
Deploy free:    Push to GitHub → connect at https://streamlit.io/cloud
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="GrowthLock SVRP Return Model",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CORE MATH
# ============================================================

def per_cycle_economics(
    investment: float,
    factor: float,
    default_rate: float,
    default_timing: float,
    recovery: float,
    servicing_fee_pct: float,
    fee_allocation: str = "pre_split",
) -> dict:
    """
    Compute one-cycle investor economics.

    Model:
      - Performing capital (1-D) returns at full factor F.
      - Defaulted capital D pays back fraction T of its scheduled total
        before defaulting, then recovers fraction R of the remaining
        balance via UCC enforcement.
      - Total returned to the deal:
            I * F * [1 - D*(1-T)*(1-R)]
      - Servicing fee is 3% of *invested capital* (per May 9 2026 clarification):
            I * SF

    Fee allocation modes:
      - "pre_split" (partner-fair): fee deducted from partnership pool,
        then 50/50 split of net. GrowthLock pays half the fee implicitly.
      - "investor_only" (per the prospectus's worked example, subsection
        20.3 "Net Return After Fees"): 50/50 split of gross profit first,
        then full fee from investor only. GrowthLock pays zero fees;
        investor's effective split drops below 50%.

    Principal loss (when gross P&L is negative) is absorbed 100% by investor
    in both modes — the agreement is silent on loss allocation when returns
    are insufficient to return principal, interpreted conservatively here.
    """
    I = float(investment)
    F = float(factor)
    D = float(default_rate)
    T = float(default_timing)
    R = float(recovery)
    SF = float(servicing_fee_pct)

    loss_factor = D * (1.0 - T) * (1.0 - R)
    total_returned = I * F * (1.0 - loss_factor)
    servicing_fee = I * SF
    gross_pnl = total_returned - I  # before fees, before split

    if fee_allocation == "pre_split":
        # Partner-fair: fee comes out of the pool, then 50/50 split
        net_pool = gross_pnl - servicing_fee
        if net_pool >= 0:
            investor_pnl = 0.5 * net_pool
            growthlock_pnl = 0.5 * net_pool
        else:
            investor_pnl = net_pool
            growthlock_pnl = 0.0
    else:  # investor_only — per the prospectus's worked example
        # 50/50 split first, then full fee deducted from investor share
        if gross_pnl >= 0:
            growthlock_pnl = 0.5 * gross_pnl
            investor_pnl = 0.5 * gross_pnl - servicing_fee
        else:
            investor_pnl = gross_pnl - servicing_fee
            growthlock_pnl = 0.0

    investor_end = I + investor_pnl
    net_after_fees = total_returned - servicing_fee
    partnership_pnl = net_after_fees - I

    return {
        "investment": I,
        "total_returned": total_returned,
        "servicing_fee": servicing_fee,
        "net_after_fees": net_after_fees,
        "partnership_pnl": partnership_pnl,
        "investor_pnl": investor_pnl,
        "growthlock_pnl": growthlock_pnl,
        "investor_end_position": investor_end,
        "cycle_return_pct": investor_pnl / I if I > 0 else 0.0,
        "loss_factor": loss_factor,
        "capital_lost": max(0.0, -investor_pnl),
        "effective_investor_share_pct": (
            (investor_pnl / gross_pnl) if gross_pnl > 0 else 0.0
        ),
    }


def annualized(
    investment: float,
    factor: float,
    default_rate: float,
    default_timing: float,
    recovery: float,
    servicing_fee_pct: float,
    cycle_days: int,
    fee_allocation: str = "pre_split",
) -> dict:
    """Annualize one-cycle economics under compounding and distribution."""
    cycles_per_year = 365.0 / cycle_days
    full_cycles = int(cycles_per_year)
    partial_cycle = cycles_per_year - full_cycles

    # --- Compounding path: capital rolls between cycles ---
    capital = investment
    history = [capital]
    for _ in range(full_cycles):
        r = per_cycle_economics(
            capital, factor, default_rate, default_timing,
            recovery, servicing_fee_pct, fee_allocation,
        )
        capital = r["investor_end_position"]
        history.append(capital)

    if partial_cycle > 0:
        r = per_cycle_economics(
            capital, factor, default_rate, default_timing,
            recovery, servicing_fee_pct, fee_allocation,
        )
        partial_pnl = r["investor_pnl"] * partial_cycle
        capital = capital + partial_pnl
        history.append(capital)

    compounding_return = (capital - investment) / investment

    # --- Distribution path: principal constant unless losses force erosion ---
    base = per_cycle_economics(
        investment, factor, default_rate, default_timing,
        recovery, servicing_fee_pct, fee_allocation,
    )
    per_cycle_pnl = base["investor_pnl"]
    total_pnl = per_cycle_pnl * cycles_per_year

    if per_cycle_pnl >= 0:
        dist_principal = investment
        dist_profit = total_pnl
        dist_erosion = 0.0
    else:
        dist_principal = investment + total_pnl
        dist_profit = 0.0
        dist_erosion = -total_pnl

    return {
        "cycles_per_year": cycles_per_year,
        "per_cycle_pnl": per_cycle_pnl,
        "per_cycle_return_pct": base["cycle_return_pct"],
        "compounding_final": capital,
        "compounding_return_pct": compounding_return,
        "compounding_history": history,
        "distribution_profit": dist_profit,
        "distribution_principal_end": dist_principal,
        "distribution_erosion": dist_erosion,
        "distribution_return_pct": total_pnl / investment,
    }


# ============================================================
# UI
# ============================================================

st.title("GrowthLock SVRP Return Model")
st.caption(
    "Conservative-default modeling tool with full sensitivity controls. "
    "Defaults reflect the realistic case discussed — not GrowthLock's marketing example."
)

# -------- SIDEBAR --------
with st.sidebar:
    st.header("Model inputs")
    st.caption("Defaults = conservative scenario. Move sliders to stress-test.")

    st.subheader("Deal terms")
    investment = st.slider(
        "Investment amount",
        min_value=100_000, max_value=300_000,
        value=100_000, step=10_000,
        format="$%d",
        help="SVRP minimum \\$100K, maximum \\$300K.",
    )
    factor_rate = st.slider(
        "Factor rate",
        min_value=1.30, max_value=1.60,
        value=1.45, step=0.01,
        help="SVRP target 1.40–1.50+.",
    )
    cycle_days = st.slider(
        "Cycle duration (days)",
        min_value=60, max_value=180,
        value=110, step=5,
        help="SVRP target 100–120 days.",
    )

    st.subheader("Risk model")
    default_rate_pct = st.slider(
        "Default rate",
        min_value=0, max_value=30,
        value=10, step=1,
        format="%d%%",
        help="Industry baseline reported by the funders: 10%. SVRP marketing model assumes 0%.",
    )
    default_rate = default_rate_pct / 100

    default_timing_pct = st.slider(
        "Payments collected before default",
        min_value=0, max_value=100,
        value=50, step=5,
        format="%d%%",
        help="Of the merchant's scheduled total payback, how much they pay before defaulting. "
             "0% = default on day one (worst case). 100% = full repayment (no default). "
             "Higher values mean less remaining balance is at risk when the default occurs.",
    )
    default_timing = default_timing_pct / 100

    recovery_rate_pct = st.slider(
        "Recovery rate on defaulted balance",
        min_value=0, max_value=100,
        value=50, step=5,
        format="%d%%",
        help="Funders cite 50–80% recovery on actively pursued UCC enforcement. "
             "50% = conservative end of that range.",
    )
    recovery_rate = recovery_rate_pct / 100

    st.subheader("Fees")
    servicing_fee_pct = st.slider(
        "Servicing fee (% of invested capital)",
        min_value=0.00, max_value=5.00,
        value=3.00, step=0.25,
        format="%.2f%%",
        help="Funder charges up to 3% of the syndicated amount (per May 9 2026 "
             "clarification). SVRP doc range: 1.75–4% pass-through.",
    )
    servicing_fee = servicing_fee_pct / 100
    fee_allocation_label = st.radio(
        "Fee allocation",
        options=["Pre-split (partner-fair)", "Investor-only (per prospectus math)"],
        index=0,
        help="Pre-split: fee comes out of partnership pool before the 50/50 split — "
             "both sides bear half the fee. Investor-only: 50/50 split first, then "
             "full fee from investor only — GrowthLock pays nothing, investor's effective "
             "split drops below 50%. The prospectus's worked example in its "
             "financial-model section (subsection 20.3, 'Net Return After Fees') uses "
             "the investor-only interpretation. Which one is contractual is the open "
             "question — see the Discrepancies tab.",
    )
    fee_allocation = "pre_split" if fee_allocation_label.startswith("Pre") else "investor_only"

    st.markdown("---")
    st.markdown("**Default settings = conservative case:**")
    st.markdown(
        "- 10% default rate (stated industry baseline)\n"
        "- 50% recovery (low end of the 50–80% funder-reported range)\n"
        "- 50% payments collected before default (mid-cycle)\n"
        "- 3% servicing fee on invested capital\n"
        "- 1.45 factor rate, 110-day cycle"
    )
    st.caption(
        "These defaults represent the realistic case discussed: meaningful default rate, "
        "moderate recovery, mid-cycle default point. The SVRP marketing example uses "
        "zero defaults — that's the dotted reference line in the chart."
    )

# -------- COMPUTE --------
single = per_cycle_economics(
    investment, factor_rate, default_rate, default_timing,
    recovery_rate, servicing_fee, fee_allocation,
)
annual = annualized(
    investment, factor_rate, default_rate, default_timing,
    recovery_rate, servicing_fee, cycle_days, fee_allocation,
)

# Marketing reference: zero defaults, same other inputs
# Note: marketing case uses the SAME fee_allocation as the user selected,
# so the comparison shows what the SVRP numbers SHOULD be under each model.
marketing_single = per_cycle_economics(
    investment, factor_rate, 0.0, 0.0, 1.0, servicing_fee, fee_allocation,
)
marketing_annual = annualized(
    investment, factor_rate, 0.0, 0.0, 1.0, servicing_fee, cycle_days, fee_allocation,
)

# -------- TABS --------
tab_model, tab_sens, tab_loss, tab_disc = st.tabs([
    "📊 Model",
    "📈 Sensitivity",
    "🛡️ Loss-Sharing",
    "⚠️ Discrepancies",
])

# ============== TAB 1: MODEL ==============
with tab_model:
    # Fee allocation context banner
    if fee_allocation == "pre_split":
        st.success(
            f"**Fee allocation: pre-split (partner-fair).** "
            f"Effective investor share of profit: "
            f"**{single['effective_investor_share_pct']*100:.1f}%** "
            f"(would be exactly 50% with zero fees)."
        )
    else:
        st.warning(
            f"**Fee allocation: investor-only (per the prospectus's worked example).** "
            f"Effective investor share of profit: "
            f"**{single['effective_investor_share_pct']*100:.1f}%** — "
            f"below the stated 50/50 split because investor pays full servicing fee. "
            f"Flip to pre-split in the sidebar to see the partner-fair version."
        )

    st.subheader("Per-cycle economics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Total returned",
        f"${single['total_returned']:,.0f}",
        delta=f"on ${investment:,.0f} invested",
    )
    c2.metric(
        "Servicing fee",
        f"-${single['servicing_fee']:,.0f}",
    )
    c3.metric(
        "Investor P&L",
        f"${single['investor_pnl']:,.0f}",
        delta=f"{single['cycle_return_pct']*100:.2f}% per cycle",
    )
    c4.metric(
        "End position",
        f"${single['investor_end_position']:,.0f}",
    )

    if single["capital_lost"] > 0:
        st.error(
            f"⚠️ This scenario produces a **per-cycle loss of "
            f"\\${single['capital_lost']:,.0f}** ({single['capital_lost']/investment*100:.1f}% of capital). "
            f"In compounding mode, that loss compounds against you."
        )

    st.markdown("---")
    st.subheader("Annualized projections")

    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**Compounding** (reinvest each cycle)")
        st.metric(
            "Final capital",
            f"${annual['compounding_final']:,.0f}",
        )
        st.metric(
            "Annual return",
            f"{annual['compounding_return_pct']*100:.1f}%",
        )
        st.caption(
            f"{annual['cycles_per_year']:.2f} cycles per year — each one re-deploys "
            f"the full ending balance of the prior."
        )

    with a2:
        st.markdown("**Distribution** (take profits each cycle)")
        st.metric(
            "Profits collected",
            f"${annual['distribution_profit']:,.0f}",
        )
        st.metric(
            "Annual return",
            f"{annual['distribution_return_pct']*100:.1f}%",
        )
        if annual["distribution_erosion"] > 0:
            st.warning(
                f"Principal eroded by **\\${annual['distribution_erosion']:,.0f}** "
                f"({annual['distribution_erosion']/investment*100:.1f}%) — "
                f"per-cycle losses exceeded distributable profit."
            )
        else:
            st.caption(
                f"Capital stays at \\${investment:,.0f}; profits paid out cycle-by-cycle."
            )

    st.markdown("---")
    st.subheader("Capital trajectory — compounding")
    history = annual["compounding_history"]
    labels = [f"Start" if i == 0 else f"After cycle {i}" for i in range(len(history))]

    # Build marketing reference trajectory at same cycle count
    mkt_history = [investment]
    cap = investment
    for _ in range(len(history) - 1):
        cap = cap * (1.0 + marketing_single["cycle_return_pct"])
        mkt_history.append(cap)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=mkt_history,
        mode="lines+markers",
        line=dict(color="#9B9B9B", width=2, dash="dot"),
        marker=dict(size=7),
        name="Marketing case (0% defaults)",
    ))
    fig.add_trace(go.Scatter(
        x=labels, y=history,
        mode="lines+markers",
        line=dict(color="#1D9E75", width=3),
        marker=dict(size=9),
        name="Your scenario",
    ))
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="",
        yaxis_title="Capital ($)",
        yaxis_tickformat="$,.0f",
        legend=dict(orientation="h", y=-0.18),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Your scenario vs. marketing case")
    comparison = pd.DataFrame({
        "": [
            "Per-cycle investor return",
            "Cycles per year",
            "Annual return — distribution",
            "Annual return — compounding",
            "Final capital (compounding)",
        ],
        "Marketing (0% defaults)": [
            f"{marketing_single['cycle_return_pct']*100:.2f}%",
            f"{annual['cycles_per_year']:.2f}",
            f"{marketing_annual['distribution_return_pct']*100:.1f}%",
            f"{marketing_annual['compounding_return_pct']*100:.1f}%",
            f"${marketing_annual['compounding_final']:,.0f}",
        ],
        "Your scenario": [
            f"{single['cycle_return_pct']*100:.2f}%",
            f"{annual['cycles_per_year']:.2f}",
            f"{annual['distribution_return_pct']*100:.1f}%",
            f"{annual['compounding_return_pct']*100:.1f}%",
            f"${annual['compounding_final']:,.0f}",
        ],
        "Delta": [
            f"{(single['cycle_return_pct']-marketing_single['cycle_return_pct'])*100:+.2f} pp",
            "—",
            f"{(annual['distribution_return_pct']-marketing_annual['distribution_return_pct'])*100:+.1f} pp",
            f"{(annual['compounding_return_pct']-marketing_annual['compounding_return_pct'])*100:+.1f} pp",
            f"${annual['compounding_final']-marketing_annual['compounding_final']:+,.0f}",
        ],
    })
    st.dataframe(comparison, use_container_width=True, hide_index=True)

# ============== TAB 2: SENSITIVITY ==============
with tab_sens:
    st.subheader("Sensitivity — annualized return (compounding)")
    st.markdown(
        "**How to read this:** each cell is the projected annual return percentage "
        "if the default rate is the value on the **left side** and the recovery rate "
        "is the value on the **top**. Green cells = higher returns. Red cells = "
        "worse outcomes. The deeper red anything gets, the more capital you're "
        "losing per year."
    )
    st.markdown(
        f"*Other inputs held constant at sidebar values: factor rate "
        f"{factor_rate:.2f}, cycle {cycle_days} days, default occurs after "
        f"{default_timing*100:.0f}% of payments, fee {servicing_fee*100:.2f}%, "
        f"investment \\${investment:,.0f}.*"
    )

    d_grid = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    r_grid = [0.00, 0.25, 0.50, 0.75, 1.00]

    matrix = []
    for d in d_grid:
        row = []
        for r in r_grid:
            res = annualized(
                investment, factor_rate, d, default_timing,
                r, servicing_fee, cycle_days, fee_allocation,
            )
            row.append(res["compounding_return_pct"] * 100.0)
        matrix.append(row)

    fig_h = go.Figure(data=go.Heatmap(
        z=matrix,
        x=[f"{int(r*100)}%" for r in r_grid],
        y=[f"{int(d*100)}%" for d in d_grid],
        colorscale="RdYlGn",
        zmid=0,
        text=[[f"{v:.0f}%" for v in row] for row in matrix],
        texttemplate="%{text}",
        textfont={"size": 14},
        colorbar=dict(title=dict(text="Annual<br>return %", side="right")),
    ))
    fig_h.update_layout(
        height=460,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Recovery rate on defaulted balance →",
        yaxis_title="Default rate (% of cycles that default) ↓",
        yaxis=dict(autorange="reversed"),
        xaxis=dict(side="top"),
    )
    st.plotly_chart(fig_h, use_container_width=True)

    st.markdown("---")
    st.subheader("Sensitivity — single-cycle return")
    st.markdown(
        "**How to read this:** each cell is the investor's return for one cycle "
        "at the factor rate (top) and default rate (left). This is the underlying "
        "per-cycle math — multiply by cycles per year (~3.3 at default settings) "
        "to estimate annualized returns."
    )
    st.markdown(
        f"*Other inputs held constant: default occurs after "
        f"{default_timing*100:.0f}% of payments, recovery "
        f"{recovery_rate*100:.0f}%, fee {servicing_fee*100:.2f}%.*"
    )
    f_grid = [1.30, 1.35, 1.40, 1.45, 1.50, 1.55, 1.60]
    matrix2 = []
    for d in d_grid:
        row = []
        for f in f_grid:
            res = per_cycle_economics(
                investment, f, d, default_timing,
                recovery_rate, servicing_fee, fee_allocation,
            )
            row.append(res["cycle_return_pct"] * 100.0)
        matrix2.append(row)

    fig_h2 = go.Figure(data=go.Heatmap(
        z=matrix2,
        x=[f"{f:.2f}" for f in f_grid],
        y=[f"{int(d*100)}%" for d in d_grid],
        colorscale="RdYlGn",
        zmid=0,
        text=[[f"{v:.1f}%" for v in row] for row in matrix2],
        texttemplate="%{text}",
        textfont={"size": 13},
        colorbar=dict(title=dict(text="Per-cycle<br>return %", side="right")),
    ))
    fig_h2.update_layout(
        height=460,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Factor rate →",
        yaxis_title="Default rate (% of cycles that default) ↓",
        yaxis=dict(autorange="reversed"),
        xaxis=dict(side="top"),
    )
    st.plotly_chart(fig_h2, use_container_width=True)

    st.info(
        "**Takeaway from these charts.** The MCA structure has wide downside "
        "tolerance — even at 20% default rates with 25% recovery, the factor rate "
        "spread is wide enough that returns stay positive in most cells. The factor "
        "rate matters more than people expect; a move from 1.45 to 1.50 covers a "
        "lot of default risk."
    )

# ============== TAB 3: LOSS-SHARING MECHANISMS ==============
with tab_loss:
    st.subheader("Loss-sharing mechanisms — modeling investor protection")
    st.caption(
        "Modeling two structural mechanisms that could be added to the syndication "
        "agreement to address the asymmetric loss allocation in the current structure. "
        "Both draw from revenue GrowthLock has already earned rather than requiring "
        "fresh capital."
    )

    st.markdown("##### How the two mechanisms work")
    st.markdown(
        "**Mechanism A — Chain-profit clawback.** A 'chain' is a continuous sequence "
        "of renewals on a single borrower (not separate funding events with the same "
        "borrower after a full payoff and gap — those start new chains). If a renewal "
        "in the chain defaults, GrowthLock rebates a percentage of the syndication "
        "profit they collected from earlier renewals in that same chain back to the "
        "affected investor.\n\n"
        "**Mechanism B — Origination commission rebate.** GrowthLock earns origination "
        "commissions from the funding bank on every deal that funds, separate from the "
        "syndication economics (per Q&A disclosure). For any defaulted deal, GrowthLock "
        "rebates a percentage of the commission they earned to the affected investor.\n\n"
        "**The two cover different failure modes.** B alone helps when a first-cycle "
        "deal defaults (no prior chain history to claw back from). A kicks in when a "
        "renewal default lands later in a chain (real accumulated profit exists). "
        "Combined, they cover both scenarios."
    )

    st.markdown("---")
    st.markdown("##### Scenario inputs")

    cli1, cli2 = st.columns(2)
    with cli1:
        chain_length = st.slider(
            "Chain length (total cycles, with the last one defaulting)",
            min_value=1, max_value=6, value=3,
            help="Number of cycles in the chain. Cycle N is the default; cycles 1 "
                 "through N-1 are successful. Chain length 1 = first-cycle default "
                 "(no prior renewals, Mechanism A has nothing to claw back).",
        )
        origination_commission_pct = st.slider(
            "Origination commission rate",
            min_value=0.0, max_value=10.0, value=6.0, step=0.5,
            format="%.1f%%",
            help="Percentage of advance amount the funder pays GrowthLock on "
                 "origination. Per Q&A, typically 6–10% on MCAs, with volume bonuses "
                 "of 1–5 additional points on top.",
        )
    with cli2:
        mechanism_a_pct = st.slider(
            "Mechanism A — clawback % of GL chain profit",
            min_value=0, max_value=100, value=50, step=10,
            format="%d%%",
            help="Percentage of GrowthLock's accumulated syndication profit from the "
                 "successful cycles in the chain that is rebated to the investor on "
                 "default of a subsequent renewal. Transfer is capped at the "
                 "investor's actual loss.",
        )
        mechanism_b_pct = st.slider(
            "Mechanism B — rebate % of origination commission on defaulted cycle",
            min_value=0, max_value=100, value=100, step=10,
            format="%d%%",
            help="Percentage of GrowthLock's origination commission on the defaulted "
                 "deal that is rebated to the investor. 100% = full rebate of "
                 "commission earned on that one deal.",
        )

    # ---- Compute scenarios ----
    success_cycle = per_cycle_economics(
        investment, factor_rate, 0.0, 0.0, 1.0,
        servicing_fee, fee_allocation,
    )
    investor_profit_per_cycle = success_cycle["investor_pnl"]
    gl_profit_per_cycle = success_cycle["growthlock_pnl"]

    default_cycle = per_cycle_economics(
        investment, factor_rate, 1.0, default_timing, recovery_rate,
        servicing_fee, fee_allocation,
    )
    cycle_n_pnl = default_cycle["investor_pnl"]
    investor_loss = max(0.0, -cycle_n_pnl)

    successful_cycles = chain_length - 1
    accumulated_investor_profit = successful_cycles * investor_profit_per_cycle
    accumulated_gl_profit = successful_cycles * gl_profit_per_cycle
    origination_commission_per_cycle = (origination_commission_pct / 100.0) * investment

    mech_a_transfer = min(
        (mechanism_a_pct / 100.0) * accumulated_gl_profit,
        investor_loss,
    )
    remaining_after_a = max(0.0, investor_loss - mech_a_transfer)
    mech_b_transfer = min(
        (mechanism_b_pct / 100.0) * origination_commission_per_cycle,
        remaining_after_a,
    )

    mech_a_alone = min(
        (mechanism_a_pct / 100.0) * accumulated_gl_profit,
        investor_loss,
    )
    mech_b_alone = min(
        (mechanism_b_pct / 100.0) * origination_commission_per_cycle,
        investor_loss,
    )

    unprotected_net = accumulated_investor_profit + cycle_n_pnl
    with_a_net = unprotected_net + mech_a_alone
    with_b_net = unprotected_net + mech_b_alone
    combined_net = unprotected_net + mech_a_transfer + mech_b_transfer

    st.markdown("---")
    st.markdown("##### Scenario summary")

    s1, s2, s3 = st.columns(3)
    s1.metric(
        "Investor profit from prior cycles",
        f"${accumulated_investor_profit:,.0f}",
        delta=(f"from {successful_cycles} successful cycle"
               + ("s" if successful_cycles != 1 else "")
               + " before default") if successful_cycles > 0
              else "no prior cycles",
    )
    if cycle_n_pnl >= 0:
        s2.metric(
            "Cycle N (default) net",
            f"${cycle_n_pnl:,.0f}",
            delta="positive — payments + recovery covered capital + fee",
        )
    else:
        s2.metric(
            "Cycle N (default) loss",
            f"-${investor_loss:,.0f}",
        )
    s3.metric(
        "GL chain profit before default",
        f"${accumulated_gl_profit:,.0f}",
        delta=(f"50% of partnership profit × {successful_cycles}"
               if successful_cycles > 0 else "no chain history"),
    )

    if cycle_n_pnl >= 0:
        st.info(
            "**No loss in this scenario** — at the current default-timing and recovery "
            "assumptions, the defaulted cycle still produced a positive net (collected "
            "payments plus recovery exceeded capital plus fee). Mechanisms A and B "
            "don't trigger because there's no loss to cover. Dial default timing or "
            "recovery lower in the sidebar to model a scenario where the mechanisms "
            "actually engage — try default timing 10–25% with recovery 20–40%."
        )
    else:
        st.markdown("---")
        st.markdown("##### Mechanism impact")

        m1, m2 = st.columns(2)
        with m1:
            st.metric(
                "Mechanism A transfer (combined)",
                f"${mech_a_transfer:,.0f}",
                delta=f"{mechanism_a_pct}% of GL's ${accumulated_gl_profit:,.0f}",
            )
            st.caption(
                f"Capped at the investor's ${investor_loss:,.0f} loss. "
                f"On a first-cycle default (chain length = 1), A has no chain history "
                f"to draw from."
            )
        with m2:
            st.metric(
                "Mechanism B transfer (combined)",
                f"${mech_b_transfer:,.0f}",
                delta=f"{mechanism_b_pct}% of ${origination_commission_per_cycle:,.0f} commission",
            )
            st.caption(
                f"Origination commission on the defaulted cycle: "
                f"${origination_commission_per_cycle:,.0f} "
                f"({origination_commission_pct:.1f}% × ${investment:,.0f}). Applied "
                f"after A, capped at remaining loss."
            )

        st.markdown("---")
        st.markdown("##### Final investor position — unprotected vs. protected")
        st.markdown(
            "Bars show the investor's net dollar position across the full chain. "
            "The percentage in parentheses is the cumulative return on the "
            f"\\${investment:,.0f} deployed each cycle (not annualized)."
        )

        scenarios = ["Unprotected", "With Mechanism A only", "With Mechanism B only", "With A + B combined"]
        values = [unprotected_net, with_a_net, with_b_net, combined_net]
        return_pcts = [v / investment * 100.0 for v in values]
        colors = ["#DC2626" if v < 0 else "#1D9E75" for v in values]
        text_labels = [
            f"${v:,.0f}<br>({p:+.1f}%)"
            for v, p in zip(values, return_pcts)
        ]

        fig = go.Figure(go.Bar(
            x=scenarios,
            y=values,
            text=text_labels,
            textposition="outside",
            marker_color=colors,
        ))
        fig.add_hline(y=0, line_color="gray", line_width=1)
        fig.update_layout(
            height=460,
            margin=dict(l=10, r=10, t=40, b=10),
            yaxis_title="Investor net position across chain ($)",
            yaxis_tickformat="$,.0f",
            xaxis_title="",
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Approximate annualized return note
        chain_days_approx = chain_length * cycle_days
        chain_years_approx = chain_days_approx / 365.0
        if chain_years_approx > 0:
            annualized_combined = (
                ((combined_net / investment + 1.0) ** (1.0 / chain_years_approx) - 1.0) * 100.0
                if combined_net > -investment else None
            )
            annualized_unprotected = (
                ((unprotected_net / investment + 1.0) ** (1.0 / chain_years_approx) - 1.0) * 100.0
                if unprotected_net > -investment else None
            )

        improvement = combined_net - unprotected_net
        pct_improvement = (improvement / investor_loss * 100) if investor_loss > 0 else 0
        if improvement > 0:
            ann_note = ""
            if annualized_combined is not None and annualized_unprotected is not None:
                ann_note = (
                    f" Annualized over the ~{chain_days_approx}-day chain duration, "
                    f"that's roughly {annualized_unprotected:+.1f}% unprotected vs. "
                    f"{annualized_combined:+.1f}% with both mechanisms."
                )
            st.success(
                f"**Combined A + B improves the investor's net position by "
                f"${improvement:,.0f}** in this scenario — recovering "
                f"{pct_improvement:.0f}% of the cycle-N loss. Net position moves from "
                f"${unprotected_net:,.0f} ({unprotected_net/investment*100:+.1f}% return) "
                f"to ${combined_net:,.0f} ({combined_net/investment*100:+.1f}% return)."
                f"{ann_note}"
            )

    st.markdown("---")
    st.markdown("##### Notes on the mechanics")
    st.markdown(
        "- **Cohort scope.** As discussed, this would apply to a limited early "
        "cohort (e.g., the first five investors at \\$100K+ minimum) rather than "
        "every investor. Keeps GrowthLock's maximum exposure bounded and rewards "
        "early adopters specifically.\n"
        "- **Commission clawback window.** The funder has a 30–45 calendar-day "
        "clawback window on origination commissions, measured from the date the "
        "deal funds. If a default happens within that first 30–45 days, the "
        "commission is returned to the funder and Mechanism B has nothing to "
        "rebate. For renewal defaults (chain length > 1), this is rarely an issue "
        "since renewals typically default well after origination. If modeling an "
        "early-default scenario specifically, set Mechanism B to 0% to remove the "
        "commission from the math.\n"
        "- **Chain definition.** A chain is a continuous renewal sequence on the "
        "same borrower. If a borrower pays off in full and comes back later for a "
        "new deal, that starts a new chain — Mechanism A's clawback only applies "
        "within a single chain, not across separate funding histories.\n"
        "- **Transfer caps.** Each mechanism's transfer is capped at the "
        "investor's actual loss, so neither mechanism overpays. The combined "
        "version applies A first, then B against the remaining loss after A."
    )


# ============== TAB 4: DISCREPANCIES ==============
with tab_disc:
    st.subheader("Discrepancies — prospectus materials vs. a conservative read")
    st.caption(
        "Gaps between what the prospectus and verbal Q&A communicate, and what a "
        "conservative read of the same materials produces."
    )

    st.markdown("##### 1. Servicing fee allocation")
    st.markdown(
        "The prospectus's financial-model section (subsection 20.3, 'Net Return After "
        "Fees') is the only place in the document where the return math is worked "
        "out with dollar figures. The literal example, verbatim:\n\n"
        "> Assume: Servicing Fee: 3% (\\$3,000)  \n"
        "> Net to Investor:  \n"
        "> • Gross Profit: \\$22,500  \n"
        "> • Less Fees: (\\$3,000)  \n"
        "> • Net Profit: **\\$19,500**\n\n"
        "The \\$19,500 result is only mathematically achievable one way: the gross "
        "\\$45,000 profit splits 50/50 first (\\$22,500 each), then the full \\$3,000 fee "
        "comes off the investor's \\$22,500. The investor pays 100% of the fee; "
        "GrowthLock pays 0%.\n\n"
        "In conversation, you described the fee structure differently: 'fee comes out "
        "first, then we split what's left 50/50.' That math runs: \\$45,000 minus "
        "\\$3,000 equals \\$42,000, split 50/50 equals **\\$21,000** to investor, not "
        "\\$19,500. The verbal explanation and the prospectus's worked example produce "
        "per-cycle results that are \\$1,500 apart.\n\n"
        "The English language in the document is silent on allocation. The only two "
        "sentences that touch fees:\n"
        "- Section 9: 'Servicing Fees: 1.75%–4% (pass-through only)'\n"
        "- Section 7.2: 'All servicing fees are passed through at cost'\n\n"
        "Neither specifies *who* the fee passes through to. Only the math in §20.3 "
        "implies an answer, and it points to the less-favorable interpretation.\n\n"
        "If the executed agreement operates on the \\$21,000 version, a single sentence "
        "under Section 9 would close the ambiguity permanently: *Servicing fees are "
        "deducted from gross partnership profit prior to the 50/50 split between "
        "Investor and Company.*\n\n"
        "Per-cycle impact: \\$1,500. Annualized: roughly 5 percentage points of return. "
        "The sidebar toggle flips between the two interpretations."
    )

    st.markdown("##### 2. Default rate baseline")
    st.markdown(
        "The prospectus's financial model walks through several annualized return "
        "scenarios (58.5% / 68–75% / 80–100%+) and **none of them include any default "
        "rate** — every projection assumes 100% of advances repay in full. You "
        "confirmed (May 8 2026 Q&A) that the funders operate against a 10% industry "
        "baseline. The model anchors on 10% by default; the slider stress-tests in "
        "either direction. Adding a baseline reference and a stressed-scenario row to "
        "the prospectus's financial-model section would close the gap between the "
        "marketing projections and the underlying reality."
    )

    st.markdown("##### 3. Track record framing")
    st.markdown(
        "The prospectus presents the 20-deal performance snapshot in language that "
        "reads like an active syndication track record. You confirmed (April 24 2026 "
        "Q&A) that external capital under management is zero — those deals were "
        "funded with GrowthLock's own operating capital. Surfacing that distinction "
        "directly in the marketing materials would strengthen rather than weaken the "
        "story: it makes clear the performance data is honest deal-level history "
        "rather than investor-return history that doesn't yet exist."
    )

    st.markdown("##### 4. Recovery rate not modeled")
    st.markdown(
        "The prospectus doesn't model recovery on defaulted positions at all. Your "
        "funders reported 50–80% recovery on actively pursued UCC enforcement — a "
        "structural feature of MCAs that materially softens default impact. Leaving "
        "it out of the prospectus actually *understates* the program's risk-adjusted "
        "return profile. Including it would make the stressed scenarios more "
        "compelling, not less. The model uses 50% as the conservative anchor."
    )

    st.markdown("##### 5. Asymmetric loss allocation")
    st.markdown(
        "The agreement's profit-allocation language reads: 'Return of Investor "
        "capital, then remaining Net Profits split 50% Investor / 50% Company.' The "
        "language is silent on loss allocation when total returns don't cover the "
        "principal-return step. The model assumes the conservative interpretation — "
        "investor absorbs full principal loss while GrowthLock takes 50% of upside "
        "only.\n\n"
        "Worth structurally addressing rather than just clarifying. The **Loss-Sharing "
        "tab** models two specific mechanisms — chain-profit clawback and origination "
        "commission rebate — that would close this gap without requiring fresh capital "
        "from GrowthLock. Both draw from revenue you've already earned (syndication "
        "profits on prior renewals, origination commissions on the defaulted deal). "
        "The model lets you dial in the parameters and see the dollar impact on a "
        "defaulted chain."
    )

    st.markdown("##### 6. Compounding example math")
    st.markdown(
        "The compounding illustration shows: \\$100K → \\$119,500 → \\$142,802 → "
        "\\$170,608 after three cycles, labeled a 19.5% per-cycle compounding result. "
        "The math reconciles cleanly (100,000 × 1.195³ = \\$170,648). The issue is "
        "framing: it's predicated on 19.5% per cycle holding for three consecutive "
        "cycles with no variance, no defaults, no deployment lag.\n\n"
        "Two cleanest ways to close the gap:\n\n"
        "- **Form 1 — single-sentence fix:** Add a disclaimer below the table: "
        "*'This illustration assumes 19.5% per cycle held constant for three cycles "
        "with no defaults, no recovery costs, and immediate redeployment between "
        "cycles. Realized returns will vary based on default rates, recovery, and "
        "deployment timing.'* Five-minute change to the document, closes the gap "
        "honestly.\n"
        "- **Form 3 — parallel-column treatment:** Add a second 'conservative case' "
        "column to the same compounding table, with realistic default and recovery "
        "assumptions. Mirrors the dual-case framing this app uses in its Model tab. "
        "Structurally cleaner but a bigger lift.\n\n"
        "Other approaches exist (showing the chart as a range, or pointing investors "
        "to a modeling tool — see point 4 above) but these two are probably the "
        "cleanest for GrowthLock to execute on quickly."
    )

    st.markdown("---")
    st.caption(
        "These read as first-generation document gaps rather than intent. Each is "
        "something a clarifying sentence in the materials or executed agreement would "
        "address directly."
    )

# -------- FOOTER --------
st.markdown("---")
st.caption(
    "Model built on documented SVRP terms and Q&A responses from April 24, May 8, "
    "and May 9 2026. All projections are non-guaranteed."
)
