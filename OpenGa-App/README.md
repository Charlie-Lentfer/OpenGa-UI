# OpenGa

Open-source techno-economic model for primary gallium recovery from an Australian
Bayer liquor slipstream. Mass and energy balance, equipment sizing, capital and
operating cost, policy scenarios, carbon, and an interactive flowsheet.

The current version is **v3.0 of the app**, which tracks the `OpenGa_v3.5_MEB.xlsx`
workbook. It lives at the root of this repository. Earlier versions are git tags,
not folders — see [Versions](#versions).

## Run it

```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Or without a browser, to get the headline numbers and the full check suite:

```bash
python3 selftest.py
python3 -m pytest tests -q
```

## What it produces

At the shipped defaults, on a basis of one kilogram of 4N gallium:

| | |
|---|---|
| Overall gallium recovery | 25.81 % |
| Liquor throughput | 71.94 t/kg Ga |
| Electricity | 19.83 kWh/kg Ga |
| Fixed capital | A$467.6 M |
| Cash operating cost | A$248.02/kg |
| Production cost | A$697.41/kg |
| Minimum viable price p\* | A$836.68/kg |

**Read this before quoting any of those.** This is a **Class 5** concept-screening
basis under AACE 18R-97, whose accuracy range is −20 % to −50 % / +30 % to +100 %.
On p\* that is roughly **A$420 – A$1,670**. The point estimate is printed to the
cent because the arithmetic is deterministic, not because the answer is known to
that precision. Of 276 parameters carrying a status, 29 % are Low confidence and 20
are placeholders — including the feed assay, which is unmeasured and is the single
largest swing in the model.

## Two checks are meant to fail

`selftest.py` exits zero with two findings reported. They are not build failures —
each marks an assumption that was invisible until it became an input:

- **Resin life is carried in calendar years; the cited source reports cycles.** Three
  years at the modelled cycle time is about 420 cycles against a cited 30. On a
  30-cycle basis the resin make-up rises from 0.33 to about 4.6 kg/kg Ga.
- **Aluminium is excluded from the resin capacity calculation.** Co-adsorption is
  0.1 %, but that is 2.77 kg Al per kg Ga — more than twice the gallium loaded.

Both are exposed as inputs (`ResinMode`, `ResinCycles`, `BurdenAl`). Set them and the
model responds; leave them and it keeps telling you they are unresolved.

## Layout

```
app/                 Streamlit interface
openga_v1/           model: meb, streams, equipment, capex, opex, policy, finance,
                     allocation, carbon, validation, analysis
openga_flowsheet/    flowsheet renderer and geometry
tests/               unit and app tests
selftest.py          headline numbers plus the full check suite, no browser
```

`engine.run(ModelInputs) -> Results` walks the whole model in one pass with no
iteration. Defaults in `openga_v1/_gen_defaults.py` are generated from the workbook,
so the code and the spreadsheet cannot drift by transcription.

## Versions

| Tag | What it is |
|---|---|
| `v3.0` | Current. Aligned with `OpenGa_v3.5_MEB.xlsx`: electrolyte recycle, resin duty and capacity burdens, electrolyte admissibility screening, Na/S/Cl/Ca element ledger, stream temperatures. Fixes two defects carried since V1. |
| `v2.0` | Interactive flowsheet and the S1–S34 stream register. |
| `v1.0` | First Streamlit port of the v3.3 workbook. |

```bash
git checkout v2.0     # any earlier version
git checkout main     # back to current
```

Change records: [`MODEL_NOTES_V3.md`](MODEL_NOTES_V3.md),
[`MODEL_NOTES_V1.md`](MODEL_NOTES_V1.md),
[`FLOW_MODEL_NOTES.md`](FLOW_MODEL_NOTES.md).

## What this model does not do

It validates no input. It predicts no product purity. It carries no acid–base
equilibrium and no reaction thermochemistry beyond a tier-1 sensible-heat ledger.
The capital estimate applies a visible completeness factor of 6 to an equipment list
that costs out at about one sixth of the published comparable, and that comparable is
itself a six-tenths scaling of a zinc plant. All of this is stated on the Checks tab
rather than hidden.
