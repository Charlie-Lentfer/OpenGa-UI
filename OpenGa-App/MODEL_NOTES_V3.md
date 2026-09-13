# OpenGa app V3 — alignment with v3.5 and two corrected defects

V3 = V2 plus (1) full alignment with `OpenGa_v3.5_MEB.xlsx`, and (2) two genuine
defects fixed. Everything else is untouched.

## 1. Alignment

V2's `_gen_defaults.py` was generated from **v3.3** and carried none of the v3.4 or
v3.5 inputs. Thirty-three parameters have been added, so the app and the workbook now
hold the same 260 inputs:

| Group | Parameters |
|---|---|
| v3.4 stream assumptions | `SSCap`, `EluAl`, `EluV`, `MistFrac`, `EWRecycle`, `MO2`, `MH2` |
| v3.5 resin duty | `ResinMode`, `ResinCycles`, `BurdenV`, `BurdenAl`, `RetainLiq` |
| v3.5 purification | `AlRemUP9`, `CakeLiqSol` |
| v3.5 admissibility | `LimAlEW`, `LimSO4EW`, `LimVEW` |
| v3.5 atomic weights | `MNa`, `MS`, `MCl`, `MCa`, `MV` |
| v3.5 temperatures | `T_HOST`, `T_AMB`, `T_IX`, `T_ELU`, `T_PREC`, `T_PUR`, `T_EW`, `T_REF`, `CP_W`, `CP_NW`, `CP_LIQ` |

Behaviour added to match the workbook:

- **UP9 solves the electrolyte loop.** `meb._up9_factor` implements
  `eta9 / (1 - r.eta9.(1 - eta10))`. V2 raised a `ValueError` on any non-zero
  `EWRecycle`; V3 models it, and `ga_out["UP9"]` stays the actual gallium entering
  the cell. At `EWRecycle = 0` the cascade is bit-identical to V2.
- **Resin capacity burdens.** `total_load` is now
  `Ga + BurdenV.V + BurdenAl.Al`. At the shipped `BurdenV = 1, BurdenAl = 0` this
  reproduces V2 exactly.
- **Resin life on cycles.** `ResinMode = 2` amortises the charge over
  `ResinCycles x cycle_h` instead of calendar years.
- **Acid mist.** V2 hard-coded S12 to zero, which left sulfur with no outlet. Now
  driven by `MistFrac`.
- **Retained bed liquor** (`RetainLiq`) on S5/S7/S8, **Al rejection** (`AlRemUP9`)
  splitting S27/S28, and **mother-liquor solutes in the cake** (`CakeLiqSol`)
  carrying sulfate into the electrolyte.
- **S30 carries every component of S28**, not only Ga/NaOH/Water. Aluminium and
  sulfate that reach the cell have to leave it again.
- **Circulating inventory.** Caustic, aluminium and sulfate in the electrolyte loop
  are `fresh / (1 - r)`: the purge removes what the feed brings in. This is why a
  100% return is not a steady state, and the guard caps it at 99.9%.
- **Element ledger** extended from Ga/Al/V to Na, S, Cl and Ca, with a relative
  tolerance because rounded molar masses cannot close mass and atoms at once.
- **Stream temperatures and tier-1 sensible heat** (`T_degC`, `H_kWh_th` on every
  stream record). Sensible heat only — no reaction, dilution or mixing heat, and no
  recovery credited.

Stream balance checks went from **52 to 104** (eight quantities across thirteen
boundaries) and all pass, including at `EWRecycle = 90%` and with all five v3.5
inputs moved together.

## 2. Defects found and fixed

**Solid residue mixed an element mass with compound masses.** `meb.run` built
`solid_residue` as `Al(OH)3 + CaO + (ga_cake - ga_elyte) + resin`. The first two
terms are compound masses; the gallium term was the contained metal. What actually
leaves UP9 is Ga(OH)3.

- Understated the disposal tonnage by **0.0418 kg/kg Ga**, about 0.41%.
- Made the OPEX/carbon figure disagree with the stream table: 10.2288 against
  S27 + S19 = 10.2706.
- `allocation.py` repeated the same expression, so the allocation inherited it.

Fixed in both places. The correction moves p\* from A$836.669 to **A$836.676**
(+A$0.0064/kg) and carbon from 32.5958 to 32.5967 kg CO2e/kg. Recovery, throughput,
electricity, ISBL and FCI are unchanged. A regression test now pins the MEB figure to
the stream table.

**Acid mist had no outlet.** S12 was hard-coded to zero while the workbook computed
it from `MistFrac`, so sulfur entering UP4 had nowhere to go. Small (1.5e-4 kg/kg Ga)
but it is an unclosed outlet, and it is why five stream totals differed from the
workbook.

Regression constants in `validation.py` were updated for the corrected figures, with
a comment saying why they moved.

### Checked and found sound

The financial model. NPV at p\* is zero to 1e-7 across all four policy packages and
both capital modes; the grant PV matches its cash-flow row exactly; working capital
is symmetric between the closed form and the cash flow; nominal depreciation is
deflated before discounting at the real rate; the allocation closes to 1e-13 and
carbon ties back to an independent recomputation. Equipment sizing is inside every
correlation's published range. No divide-by-zero or negative flow appears across a
24-point sweep of feed assay and single-pass recovery.

## 3. New check group

`validation.run_all` returns a fourth group, `v3.5`, mirroring Checks section H of the
workbook. **Two of its seven checks are expected to fail at the shipped defaults:**

| Check | Shipped verdict |
|---|---|
| Resin life in years matches the cited life in cycles | **FAIL** — 420 against a cited 30 |
| Aluminium charged against resin capacity | **FAIL** — excluded |
| Electrolyte Al / Na2SO4 / V against limits | PASS (all structurally zero) |
| Solid residue agrees with the stream table | PASS (was failing before V3) |
| Net sensible heat, plant boundary | 24.5 kWh_th/kg Ga, informational |

`selftest.py` reports these under **Findings** and **exits zero**: they are unresolved
assumptions, not a broken build. The Streamlit Checks tab shows them as a fourth
metric with a warning banner.

## 4. Reproduction

At the shipped defaults V3 reproduces the workbook exactly:

```
recovery 0.2581401012  liquor 71.943214 t/kg  electricity 19.826208 kWh/kg
FCI A$467,616,215      cash A$248.0168/kg     p* A$836.6756/kg
internal 14/14   regression 10/10   divergence 0 of 0 (7 info)   v3.5 4 of 6
flowsheet 104 of 104 balance checks pass
```

With all five v3.5 inputs adopted (`ResinMode 2`, `BurdenAl 1`, `RetainLiq 0.4`,
`AlRemUP9 99`, `CakeLiqSol 1`): resin make-up 11.501 kg/kg Ga, H2SO4 30.07, NaOH
27.94, electrolyte Al 0.997 g/L against a 1 g/L limit, net sensible heat 58.8
kWh_th/kg, **p\* A$1,369.20** — matching the workbook to the cent.
