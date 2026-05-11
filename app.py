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
      - Servicing fee is 3% of *invested capital* (per operator clarification, May 9 2026):
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
        help="Industry baseline per the operator's funders: 10%. SVRP marketing model: 0%.",
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
        help="The operator's funders cite 50–80% on actively pursued UCC enforcement. "
             "50% = conservative end of their range.",
    )
    recovery_rate = recovery_rate_pct / 100

    st.subheader("Fees")
    servicing_fee_pct = st.slider(
        "Servicing fee (% of invested capital)",
        min_value=0.00, max_value=5.00,
        value=3.00, step=0.25,
        format="%.2f%%",
        help="Per operator clarification (May 9 2026): up to 3% of syndicated amount. "
             "SVRP doc range: 1.75–4% pass-through.",
    )
    servicing_fee = servicing_fee_pct / 100
    fee_allocation_label = st.radio(
        "Fee allocation",
        options=["Pre-split (partner-fair)", "Investor-only (per prospectus math)"],
        index=0,
        help="Pre-split: fee comes out of partnership pool before the 50/50 split — "
             "GrowthLock pays half. Investor-only: 50/50 split first, then full fee "
             "from investor — GrowthLock pays zero, investor's effective split drops "
             "below 50%. The prospectus's worked example in its financial-model section "
             "(20.3, 'Net Return After Fees') uses the second interpretation. "
             "Worth pinning the operator down on which one is actually contractual.",
    )
    fee_allocation = "pre_split" if fee_allocation_label.startswith("Pre") else "investor_only"

    st.markdown("---")
    st.markdown("**Default settings = conservative case:**")
    st.markdown(
        "- 10% default rate (the operator's stated industry baseline)\n"
        "- 50% recovery (low end of the operator's 50–80% range)\n"
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
tab_model, tab_sens, tab_disc = st.tabs([
    "📊 Model",
    "📈 Sensitivity",
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
    st.subheader("Sensitivity — annual return (compounding)")
    st.caption(
        f"Holding: factor {factor_rate:.2f}, cycle {cycle_days}d, "
        f"timing: default after {default_timing*100:.0f}% of payments, "
        f"fee {servicing_fee*100:.2f}%, "
        f"investment \\${investment:,.0f}"
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
        textfont={"size": 13},
        colorbar=dict(title="Annual %"),
    ))
    fig_h.update_layout(
        height=440,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Recovery rate →",
        yaxis_title="Default rate ↓",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_h, use_container_width=True)

    st.markdown("---")
    st.subheader("Sensitivity — per-cycle return")
    st.caption(
        f"Factor rate × default rate, holding default after {default_timing*100:.0f}% of payments, "
        f"recovery {recovery_rate*100:.0f}%, fee {servicing_fee*100:.2f}%"
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
        textfont={"size": 12},
        colorbar=dict(title="Per-cycle %"),
    ))
    fig_h2.update_layout(
        height=440,
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="Factor rate →",
        yaxis_title="Default rate ↓",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_h2, use_container_width=True)

    st.info(
        "**Read these heatmaps left-to-right and top-to-bottom.** The MCA structure has "
        "wide downside tolerance — even at 20% default rates with 25% recovery, the factor "
        "rate spread is wide enough that returns stay positive in most cells. The factor "
        "rate matters more than people expect; a move from 1.45 to 1.50 covers a lot of "
        "default risk."
    )

# ============== TAB 3: GROWTHLOCK ACTUALS ==============
# ============== TAB 4: DISCREPANCIES ==============
with tab_disc:
    st.subheader("Documented discrepancies — prospectus materials vs. conservative model")
    st.caption(
        "These are the gaps between what the SVRP prospectus and verbal Q&A "
        "communicate, and what a conservative read of the same materials produces. "
        "Each one should be resolved in writing before signing."
    )

    st.markdown("##### 1. Servicing fee allocation — the biggest discrepancy")
    st.markdown(
        "The prospectus's financial-model section (subsection 20.3, 'Net Return After "
        "Fees') is the only place in the entire document where the actual return math "
        "is worked out with dollar figures. Here is the literal example, verbatim:\n\n"
        "> Assume: Servicing Fee: 3% (\\$3,000)  \n"
        "> Net to Investor:  \n"
        "> • Gross Profit: \\$22,500  \n"
        "> • Less Fees: (\\$3,000)  \n"
        "> • Net Profit: **\\$19,500**\n\n"
        "The \\$19,500 result is only mathematically achievable one way: split the gross "
        "\\$45,000 profit 50/50 first (\\$22,500 each), then deduct the **full** \\$3,000 fee "
        "from the investor's \\$22,500. The operator pays \\$0 of the fee and keeps the full "
        "\\$22,500.\n\n"
        "**The contradiction to surface with the operator:** in conversation, the operator "
        "described the fee structure as 'fee comes out first, then we split what's left "
        "50/50.' That math produces a different number — \\$45,000 minus \\$3,000 equals "
        "\\$42,000, split 50/50 equals **\\$21,000** to the investor, not \\$19,500. The verbal "
        "explanation and the document's worked example produce results that are \\$1,500 "
        "apart per cycle.\n\n"
        "**What the document language actually says about fees** — total, across the "
        "entire prospectus and agreement:\n"
        "- Section 9: 'Servicing Fees: 1.75%–4% (pass-through only)'\n"
        "- Section 7.2: 'All servicing fees are passed through at cost'\n\n"
        "Neither sentence specifies *who* the fee passes through to. The English language "
        "is silent on allocation; only the math in the worked example points to the "
        "investor-only interpretation.\n\n"
        "**The question to put to the operator, with the dollar amounts:** *'Your verbal "
        "explanation produces \\$21,000 to investor per cycle. The prospectus's worked example "
        "shows \\$19,500 to investor per cycle. Which is contractually binding? If it is the "
        "\\$21,000 version, can we add a single sentence to Section 9 of the executed "
        "agreement that says: \"Servicing fees are deducted from gross partnership profit "
        "prior to the 50/50 split between Investor and Company\"? That closes the ambiguity "
        "permanently.'*\n\n"
        "Per-cycle impact: \\$1,500. Annualized impact: roughly 5 percentage points of return. "
        "The sidebar toggle lets you flip between the two interpretations and see the "
        "compounding effect."
    )

    st.markdown("##### 2. Servicing fee basis")
    st.markdown(
        "Independent of allocation, the **basis** for the 3% deserves clarification. Per "
        "operator clarification (May 9 2026), the funder charges **up to 3% of the syndicated amount** — "
        "i.e., your invested capital. The SVRP example doesn't explicitly say this. On a "
        "\\$100K investment taking 100% of a \\$100K advance, basis doesn't matter. On a \\$100K "
        "investment syndicated into 25% of a \\$400K advance, the fee scales with your \\$100K, "
        "not the \\$400K. The model uses the operator's stated basis (3% of invested capital)."
    )

    st.markdown("##### 3. Default rate baseline")
    st.markdown(
        "The prospectus's financial model walks through several annualized return "
        "scenarios (58.5% / 68–75% / 80–100%+) and **none of them include any default "
        "rate** — every projection assumes 100% of advances repay in full. The operator "
        "confirmed (May 8 2026 Q&A) that his funders operate against a **10% industry "
        "baseline default rate**. The prospectus financial model should at minimum "
        "reference this baseline and ideally show stressed scenarios. Currently it shows "
        "none."
    )

    st.markdown("##### 4. Track record framing")
    st.markdown(
        "The SVRP prospectus presents a 20-deal performance snapshot in language that "
        "reads like an active syndication track record. The operator confirmed (April 24 "
        "2026 Q&A) that **external capital under management is zero**. Those deals were "
        "funded with GrowthLock's own operating capital. The marketing materials should "
        "disclose this directly rather than requiring an investor to surface it in due "
        "diligence."
    )

    st.markdown("##### 5. Recovery rate not modeled")
    st.markdown(
        "**SVRP** doesn't model recovery on defaulted positions at all. **the operator's funders** "
        "reported 50–80% recovery on actively pursued UCC enforcement. This is a structural "
        "feature of MCAs that materially softens default impact — and not mentioning it "
        "in the prospectus understates the program's actual risk-adjusted return profile. "
        "The model uses 50% as the conservative anchor."
    )

    st.markdown("##### 6. Asymmetric loss allocation")
    st.markdown(
        "The agreement's profit-allocation language reads: 'Return of Investor capital, "
        "then remaining Net Profits split 50% Investor / 50% Company.' The language is "
        "silent on **loss allocation** when total returns aren't sufficient to return "
        "principal in full. The model assumes the conservative interpretation — investor "
        "absorbs full principal loss while GrowthLock takes 50% of upside only. This is "
        "asymmetric and should be pinned down in the executed agreement before signing."
    )

    st.markdown("##### 7. Compounding example math")
    st.markdown(
        "The prospectus's compounding illustration shows: \\$100K → \\$119,500 → \\$142,802 → "
        "\\$170,608 after three cycles, calling that a 19.5% per-cycle compounding result. "
        "Spot-checking: 100,000 × 1.195³ = \\$170,648 ✓. The math itself is fine — but it's "
        "predicated on 19.5% per cycle holding for three consecutive cycles with no "
        "variance, no defaults, no deployment lag between cycles. That's a marketing "
        "illustration, not a forecast."
    )

    st.markdown("---")
    st.caption(
        "None of these are accusations of bad faith — they read as first-generation "
        "document gaps. But for someone committing \\$100K–\\$300K (or considering an equity "
        "position), each one should be resolved in writing."
    )

# -------- FOOTER --------
st.markdown("---")
st.caption(
    "Model built on documented SVRP terms and operator Q&A responses (April 24, May 8, "
    "May 9 2026). All projections are non-guaranteed."
)
