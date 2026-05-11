# GrowthLock SVRP Return Model

Interactive Streamlit app for stress-testing returns on the GrowthLock Syndication Velocity Returns Program (SVRP).

## What this is

A side-by-side comparison of:
- **SVRP marketing case** — zero defaults, full factor-rate return every cycle (the prospectus's Section 20 model)
- **Your scenario** — adjustable defaults, recovery, default timing, fees, factor rate, cycle duration

The slider defaults represent the **conservative case** we landed on after Chad's Q&A: 10% default rate (his funders' baseline), 50% recovery (low end of his cited 50–80% range), 50% default timing, 3% servicing fee on invested capital, 1.45 factor rate, 110-day cycles.

Move any slider to stress-test in either direction.

## Tabs

1. **Model** — per-cycle and annualized returns, capital trajectory chart, side-by-side with marketing case
2. **Sensitivity** — two heatmaps showing how default rate × recovery and factor rate × default rate move annual returns
3. **GrowthLock Spreadsheet** — the actual 21-deal data Chad sent, for context. Not used to drive the model.
4. **Discrepancies** — six documented gaps between SVRP marketing materials and conservative reality

## Run locally

Requires Python 3.9+.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Deploy for free (shareable URL)

1. Push this folder to a new GitHub repo (public or private).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click "New app", select the repo, point at `app.py`, deploy.
4. You get a URL like `https://your-repo.streamlit.app` — usable on phone, sharable with Chad.

Free tier supports private repos and unlimited public apps.

## Model assumptions

**Per-cycle math:**
- Performing capital `(1-D) × I` returns at full factor `F`
- Defaulted capital `D × I` pays back fraction `T` of scheduled total before defaulting, then recovers fraction `R` of the remainder
- Total returned: `I × F × [1 - D(1-T)(1-R)]`
- Servicing fee: `3% of invested capital` (per Chad, May 9 2026 — not 3% of advance)
- Partnership profit split 50/50
- Principal loss absorbed 100% by investor (per SVRP Section 5.3's silence on loss allocation — conservative interpretation)

**Annualization:**
- Cycles per year: `365 / cycle_days`
- Compounding: capital rolls into each next cycle
- Distribution: capital stays constant; if per-cycle P&L is negative, losses reduce principal (cannot distribute a loss)

## Sources

- `Syndication_Agreement.pdf` and `SYNDICATION_VELOCITY_RETURNS_PROGRAM_SVRP.pdf` — program terms
- `Questions_answered_by_Chad_05_08_26.pdf` and `Follow_up_quesdtions_05_08_26.pdf` — Chad's responses on defaults, recovery, exclusivity, payment flow
- `Initial_questions__04_25_26.pdf` — Chad's responses on track record, custody (SAS), funder relationships
- `Advance_Syndication_Real_World_Example.xlsx` — the 21-deal snapshot shown in the "GrowthLock Spreadsheet" tab
