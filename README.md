# SVRP Return Model

Interactive Streamlit app for stress-testing returns on a Syndication Velocity Returns Program structured around merchant cash advance participation.

## What this is

A side-by-side comparison of:
- **Marketing case** — zero defaults, full factor-rate return every cycle (per the program prospectus's projected-return model)
- **Conservative scenario** — adjustable defaults, recovery, default timing, fees, factor rate, cycle duration

The slider defaults represent the realistic case after operator Q&A: 10% default rate (cited industry baseline), 50% recovery (low end of cited 50–80% range), 50% default timing, 3% servicing fee on invested capital, 1.45 factor rate, 110-day cycles.

Move any slider to stress-test in either direction.

## Tabs

1. **Model** — per-cycle and annualized returns, capital trajectory chart, side-by-side with marketing case
2. **Sensitivity** — two heatmaps showing how default rate × recovery and factor rate × default rate move annual returns
3. **Discrepancies** — documented gaps between program marketing materials and conservative reality

## Fee allocation toggle

The sidebar includes a toggle for fee allocation:
- **Pre-split (partner-fair):** servicing fee deducted from partnership pool before 50/50 split. Both sides bear half the fee.
- **Investor-only (prospectus style):** 50/50 split first, then full fee from investor. Operator pays zero fees; investor's effective profit share drops below 50%.

The prospectus's example math uses the investor-only allocation. The difference is ~1.5 percentage points per cycle, which compounds to ~5–9 points annually.

## Run locally

Requires Python 3.9+.

\`\`\`bash
pip install -r requirements.txt
streamlit run app.py
\`\`\`

Opens at http://localhost:8501.

## Deploy to Streamlit Community Cloud

1. Push this folder to a public GitHub repo
2. Go to https://share.streamlit.io
3. Create app → point at the repo's app.py on the main branch
4. Deploy — takes 2–4 minutes for first build
