"""
OpenGa — techno-economic and carbon model for primary gallium recovery from an
Australian Bayer liquor slipstream.

Run:   streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import charts  # noqa: E402  (same directory)
from openga_v1 import analysis, config, engine, policy as policy_mod, validation  # noqa: E402
from openga_v1.config import (CAPEX_MODES, CATEGORIES, ENERGY_MODES, PERCENT_KEYS,
                              POLICY_MODELS, RESIN_PRESETS, SELECTOR_KEYS, UNIT_OPS,
                              ModelInputs, base_params, meta)  # noqa: E402
from openga_v1.energy import ROUTES  # noqa: E402
from openga_v1.streams import balance_rows, stream_issues  # noqa: E402
from openga_flowsheet.app_flowsheet_tab import flowsheet_tab  # noqa: E402

st.set_page_config(page_title="OpenGa V2", page_icon="⚗️", layout="wide",
                   initial_sidebar_state="expanded")


def _width_kwargs() -> dict:
    """Streamlit renamed ``use_container_width`` to ``width="stretch"``. Detect
    which spelling this installation takes rather than pinning a version, and
    only switch when every widget used here accepts the new one."""
    try:
        import inspect
        for fn in (st.dataframe, st.altair_chart, st.button):
            if "width" not in inspect.signature(fn).parameters:
                return {"use_container_width": True}
        return {"width": "stretch"}
    except (TypeError, ValueError):
        return {"use_container_width": True}


_W = _width_kwargs()

# --------------------------------------------------------------------------
# session state
# --------------------------------------------------------------------------
if "overrides" not in st.session_state:
    st.session_state.overrides = {}
if "cfg" not in st.session_state:
    st.session_state.cfg = config.ModelConfig()


def reset_overrides():
    st.session_state.overrides = {}
    for name in list(st.session_state):
        if name.startswith("in_"):
            del st.session_state[name]


def input_widget_key(group, title, parameter):
    # IXRec occurs in two sections; each displayed widget needs its own key.
    return f"in_{group}_{title}_{parameter}"


def apply_input(parameter, widget_key, percent=False):
    """Commit edits before the next model run, then sync any duplicate controls."""
    shown = st.session_state[widget_key]
    value = float(shown) / 100 if percent else float(shown)
    if abs(value - meta(parameter)["default"]) > 1e-15:
        st.session_state.overrides[parameter] = value
    else:
        st.session_state.overrides.pop(parameter, None)
    for group, title, keys in CATEGORIES:
        if parameter in keys:
            other = input_widget_key(group, title, parameter)
            if other != widget_key:
                st.session_state[other] = shown


def fmt(x, nd=2):
    if x is None:
        return "—"
    try:
        return f"{x:,.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


# --------------------------------------------------------------------------
# sidebar
# --------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## OpenGa V2")
    st.caption("100 t/yr gallium from an Australian Bayer liquor slipstream")

    mode = st.radio("Mode", ["Baseline", "User"], horizontal=True,
                    help="Baseline runs the shipped v3.3 defaults and ignores every edit. "
                         "User unlocks the Inputs tab and applies your changes.")
    baseline = mode == "Baseline"
    if baseline and st.session_state.overrides:
        st.info(f"{len(st.session_state.overrides)} edit(s) held but not applied. "
                "Switch to User mode to use them.")

    st.divider()
    st.markdown("### Structural switches")
    st.caption("These change which equations run, not just their inputs. "
               "They stay live in both modes.")

    cfg = st.session_state.cfg
    energy_mode = st.selectbox(
        "Energy model", list(ENERGY_MODES), index=list(ENERGY_MODES).index(cfg.energy_mode),
        format_func=lambda k: ENERGY_MODES[k].split(" — ")[0],
        help="\n\n".join(f"**{k}** — {v}" for k, v in ENERGY_MODES.items()))
    st.caption(ENERGY_MODES[energy_mode])

    capex_mode = st.selectbox(
        "CAPEX method", list(CAPEX_MODES), index=list(CAPEX_MODES).index(cfg.capex_mode),
        format_func=lambda k: CAPEX_MODES[k].split(" — ")[0])
    st.caption(CAPEX_MODES[capex_mode])

    policy_model = st.selectbox(
        "Policy model", list(POLICY_MODELS), index=list(POLICY_MODELS).index(cfg.policy_model),
        format_func=lambda k: POLICY_MODELS[k].split(" — ")[0])

    resin_preset = st.selectbox(
        "Resin preset", [r.id for r in RESIN_PRESETS],
        index=[r.id for r in RESIN_PRESETS].index(cfg.resin_preset),
        format_func=lambda i: config.get_resin_preset(i).name)

    if policy_model == "v31":
        pkgs = config.default_policy_packages(base_params())
        policy_package = st.selectbox(
            "Policy package", [k.id for k in pkgs],
            index=[k.id for k in pkgs].index(cfg.policy_package),
            format_func=lambda i: next(k.name for k in pkgs if k.id == i))
        legacy_policy = cfg.legacy_policy
    else:
        policy_package = cfg.policy_package
        legacy_policy = st.selectbox(
            "Scenario", [s.id for s in config.LEGACY_POLICY_SCENARIOS],
            index=[s.id for s in config.LEGACY_POLICY_SCENARIOS].index(cfg.legacy_policy),
            format_func=lambda i: next(s.name for s in config.LEGACY_POLICY_SCENARIOS
                                       if s.id == i))

    st.session_state.cfg = dataclasses.replace(
        cfg, energy_mode=energy_mode, capex_mode=capex_mode, policy_model=policy_model,
        resin_preset=resin_preset, policy_package=policy_package, legacy_policy=legacy_policy)

    st.divider()
    if st.button("Reset all inputs to baseline", **_W):
        reset_overrides()
        st.rerun()
    st.caption(f"{len(st.session_state.overrides)} input(s) edited")


# --------------------------------------------------------------------------
# build and run
# --------------------------------------------------------------------------
mi = ModelInputs(params=base_params(), cfg=st.session_state.cfg)
if not baseline:
    mi = mi.with_overrides(st.session_state.overrides)
    mi = ModelInputs(params=mi.params, cfg=st.session_state.cfg)

R = engine.run(mi)

for w in R.warnings:
    st.warning(w)

TABS = ["Dashboard", "Inputs", "Mass & energy", "Flowsheet", "Equipment & CAPEX", "Operating cost",
        "Cost by unit", "Carbon", "Finance", "Policy", "Sensitivity", "Checks & sources"]
tabs = st.tabs(TABS)


# ============================================================== 1 DASHBOARD
with tabs[TABS.index('Dashboard')]:
    st.subheader("What a kilogram of Australian gallium costs")
    c = st.columns(4)
    c[0].metric("Production cost", f"A${fmt(R.lcop)}/kg",
                help="Pre-tax, cash operating cost plus annualised capital.")
    c[1].metric("Minimum viable price p*", f"A${fmt(R.pstar)}/kg",
                help="The constant real price at which NPV is zero. Not a bankable "
                     "or negotiated price.")
    c[2].metric("Cash operating cost", f"A${fmt(R.opex.cash_cost_per_kg)}/kg")
    c[3].metric("Carbon intensity", f"{fmt(R.carbon.total, 1)} kg CO₂e/kg",
                help="All boundaries. Scope 1 + 2 alone is "
                     f"{fmt(R.carbon.scope12, 1)}.")

    c = st.columns(4)
    c[0].metric("Fixed capital", f"A${R.capex.fci_aud / 1e6:,.1f}M")
    c[1].metric("Liquor throughput", f"{fmt(R.meb.liquor_t_per_kg, 1)} t/kg Ga",
                help=f"{R.meb.liquor_m3_h:,.0f} m³/h — the number that sizes the plant.")
    c[2].metric("Overall recovery", f"{R.meb.recovery_overall * 100:,.2f}%")
    c[3].metric("Electricity", f"{fmt(R.meb.elec_kwh_kg, 2)} kWh/kg")

    st.divider()
    left, right = st.columns(2)
    with left:
        rows = [{"unit": u, "Variable": R.cost_by_up[u]["variable"],
                 "Fixed": R.cost_by_up[u]["fixed"],
                 "Capital charge": R.cost_by_up[u]["capital"]} for u, _ in UNIT_OPS]
        st.altair_chart(charts.stacked_by_unit(
            pd.DataFrame(rows), ["Variable", "Fixed", "Capital charge"],
            "Production cost by unit operation", "AUD / kg Ga"), **_W)
    with right:
        rows = [{"unit": u, "Scope 1": R.carbon.by_up[u]["scope1"],
                 "Scope 2": R.carbon.by_up[u]["scope2"],
                 "Upstream": R.carbon.by_up[u]["upstream"]} for u, _ in UNIT_OPS]
        st.altair_chart(charts.stacked_by_unit(
            pd.DataFrame(rows), ["Scope 1", "Scope 2", "Upstream"],
            "Carbon intensity by unit operation", "kg CO₂e / kg Ga"),
            **_W)

    st.divider()
    st.markdown("#### Cost against feed assay")
    st.caption("No Australian refinery has published a gallium assay. This is the honest "
               "headline: a cost as a function of the number nobody has measured.")
    ac = pd.DataFrame(analysis.assay_curve(mi))
    st.altair_chart(charts.line(ac, "assay_mgL", "production_cost",
                                "Production cost vs feed gallium assay",
                                "Feed Ga assay (mg/L)", "AUD / kg Ga",
                                marker_x=R.params["GaFeed"]), **_W)
    with st.expander("Assay curve data"):
        st.dataframe(ac, **_W, hide_index=True)

    st.divider()
    st.markdown("#### Read this before quoting anything above")
    b = R.capex
    st.markdown(f"""
- The capital number carries an equipment-list completeness factor of
  **{b.completeness_factor:g}**. The itemised list costs out at
  **{b.raw_share_of_reference * 100:.0f}%** of the published comparable; a factor of
  **{b.completeness_required:.1f}** would reconcile them exactly.
- Energy model: **{ENERGY_MODES[st.session_state.cfg.energy_mode].split(' — ')[0]}**.
  CAPEX method: **{CAPEX_MODES[st.session_state.cfg.capex_mode].split(' — ')[0]}**.
- p* is the minimum constant real price that clears the cost of capital under the
  stated assumptions. It is not a bankable price, not a forecast and not a
  negotiated contract.
- The carbon figure is a **screening inventory, not a product LCA**, and its wider
  boundary rests on unverified embodied factors.
""")


# ================================================================ 2 INPUTS
with tabs[TABS.index('Inputs')]:
    st.subheader("Inputs")
    if baseline:
        st.info("Baseline mode. Every input below is shown read-only and the model is "
                "running the shipped v3.3 defaults. Switch to **User** mode in the sidebar "
                "to edit.")
    st.caption("Grouped by what they belong to. Each carries its unit, evidence status "
               "and source. Status is the thing to read: PLACEHOLDER means nobody has "
               "sourced it.")

    groups = {}
    for grp, title, keys in CATEGORIES:
        groups.setdefault(grp, []).append((title, keys))

    gtabs = st.tabs(list(groups))
    for gt, (grp, sections) in zip(gtabs, groups.items()):
        with gt:
            for title, keys in sections:
                with st.expander(title, expanded=(grp == "Plant basis")):
                    for key in keys:
                        m = meta(key)
                        if "default" not in m:
                            continue
                        cur = mi.params.get(key, m["default"])
                        cols = st.columns([3, 2, 5])
                        label = f"{m['label']}"
                        unit = m["unit"]
                        pct = key in PERCENT_KEYS
                        widget_key = input_widget_key(grp, title, key)
                        with cols[0]:
                            st.markdown(f"**{label}**")
                            st.caption(f"`{key}` · {unit}")
                        with cols[1]:
                            if baseline:
                                st.markdown(f"### {fmt(cur * 100 if pct else cur, 4)}"
                                            f"{'%' if pct else ''}")
                            elif key in SELECTOR_KEYS:
                                opts = SELECTOR_KEYS[key]
                                v = st.selectbox(label, opts, index=opts.index(int(cur))
                                                 if int(cur) in opts else 0,
                                                 key=widget_key, label_visibility="collapsed",
                                                 on_change=apply_input, args=(key, widget_key, False))
                            else:
                                shown = cur * 100 if pct else cur
                                if widget_key not in st.session_state:
                                    st.session_state[widget_key] = float(shown)
                                v = st.number_input(
                                    label, step=0.01, key=widget_key,
                                    label_visibility="collapsed", format="%.6g",
                                    on_change=apply_input, args=(key, widget_key, pct))
                        with cols[2]:
                            st.caption(f"**{m['status']}** (confidence {m['conf']}) — "
                                       f"{m['source']}")
                        st.divider()

    if not baseline and st.session_state.overrides:
        st.markdown("#### Edited inputs")
        ed = pd.DataFrame([{"key": k, "label": meta(k)["label"],
                            "baseline": meta(k).get("default"), "your value": v}
                           for k, v in sorted(st.session_state.overrides.items())])
        st.dataframe(ed, **_W, hide_index=True)


# ========================================================== 3 MASS & ENERGY
with tabs[TABS.index('Mass & energy')]:
    st.subheader("Mass and energy balance")
    st.caption("Basis: one kilogram of 4N gallium. Eleven unit operations, one recovery "
               "each. Reagents from stoichiometry, energy from duty.")
    m = R.meb
    c = st.columns(4)
    c[0].metric("Overall recovery", f"{m.recovery_overall * 100:.3f}%")
    c[1].metric("Feed gallium required", f"{fmt(m.feed_ga_kg, 3)} kg/kg")
    c[2].metric("Liquor", f"{fmt(m.liquor_t_per_kg, 2)} t/kg Ga")
    c[3].metric("Liquor flow", f"{m.liquor_m3_h:,.0f} m³/h")

    st.markdown("#### Recovery cascade")
    casc = pd.DataFrame([{"Unit": u, "Operation": nm,
                          "Recovery": m.recoveries[u],
                          "Ga out (kg)": m.ga_out[u]} for u, nm in UNIT_OPS])
    st.dataframe(casc.style.format({"Recovery": "{:.4%}", "Ga out (kg)": "{:.5f}"}),
                 **_W, hide_index=True)

    cc = st.columns(2)
    with cc[0]:
        st.markdown("#### Reagents, per kg Ga")
        st.dataframe(pd.DataFrame([
            {"Reagent": "H2SO4 contained in eluant", "kg/kg Ga": m.h2so4_contained},
            {"Reagent": "H2SO4 delivered (98%)", "kg/kg Ga": m.h2so4_delivered},
            {"Reagent": "NaOH at UP7 (precipitation)", "kg/kg Ga": m.naoh_up7},
            {"Reagent": "NaOH at UP9 (purification)", "kg/kg Ga": m.naoh_up9},
            {"Reagent": "NaOH total", "kg/kg Ga": m.naoh_total},
            {"Reagent": "Na2SO4 formed (to host circuit)", "kg/kg Ga": m.na2so4},
            {"Reagent": "CaO", "kg/kg Ga": m.cao},
            {"Reagent": "HCl", "kg/kg Ga": m.hcl},
            {"Reagent": "Resin make-up", "kg/kg Ga": m.resin_makeup},
        ]).style.format({"kg/kg Ga": "{:,.4f}"}), **_W, hide_index=True)
    with cc[1]:
        st.markdown("#### Energy")
        st.dataframe(pd.DataFrame([
            {"Item": "Liquor circuit pumping", "kW": m.kw_liquor},
            {"Item": "Wash / eluant / transfer pumping", "kW": m.kw_secondary},
            {"Item": "Electrowinning", "kW": m.kw_ew},
            {"Item": "Ancillary allowance", "kW": m.kw_misc},
            {"Item": "TOTAL", "kW": m.kw_total},
        ]).style.format({"kW": "{:,.2f}"}), **_W, hide_index=True)
        st.metric("Electricity intensity", f"{fmt(m.elec_kwh_kg, 3)} kWh/kg Ga")
        st.metric("Steam", f"{fmt(m.steam_kg_kg, 3)} kg/kg Ga")
        st.caption("Steam is zero in the base case: under the mechanistic caustic dose "
                   "there is no evaporation duty.")

    st.markdown("#### Ion exchange")
    st.dataframe(pd.DataFrame([
        {"Quantity": "Bed area (hydraulic)", "Value": m.bed_area_m2, "Unit": "m²"},
        {"Quantity": "Column diameter", "Value": m.col_dia_m, "Unit": "m"},
        {"Quantity": "Resin installed, all columns", "Value": m.resin_total_kg, "Unit": "kg"},
        {"Quantity": "Loading cycle time", "Value": m.cycle_h, "Unit": "h"},
        {"Quantity": "Bed volumes turned over per hour", "Value": m.bv_per_h, "Unit": "m³/h"},
        {"Quantity": "Precipitate grade", "Value": m.precip_grade * 100, "Unit": "wt% Ga"},
    ]).style.format({"Value": "{:,.4f}"}), **_W, hide_index=True)
    st.caption("Bed volumes per hour is the key result: it is independent of column "
               "diameter and superficial velocity, so wash, eluant and regeneration "
               "volumes do not depend on how the bed is arranged.")


# =============================================================== FLOWSHEET
with tabs[TABS.index("Flowsheet")]:
    st.subheader("Process flowsheet")
    st.caption("Live model results · major inputs and outputs · kg per kg of 4N gallium")
    display = st.radio("Diagram display", ["Image", "Interactive"], horizontal=True,
                       key="flowsheet_display",
                       help="Image fits the whole diagram to the panel. Interactive preserves card tooltips and horizontal scrolling.")
    issues = stream_issues(R.streams)
    if issues:
        st.warning("Some inputs produce invalid stream quantities. Review the stream checks before using this result.")
    flowsheet_tab(R.streams, key="v2_flowsheet", display_mode=display.lower())
    with st.expander("Stream checks and modelling basis"):
        checks = balance_rows(R.streams)
        passed = sum(row["Status"] == "PASS" for row in checks)
        st.caption(f"{passed} of {len(checks)} stream balance checks pass (total mass and elemental Ga, Al and V).")
        st.dataframe(pd.DataFrame(checks), hide_index=True, **_W)
        for issue in issues:
            st.error(issue)
        st.caption("The stream register reads the same V1 MEB as the dashboard. It uses the supplied flowsheet's "
                   "routing assumptions: Al elutes, V leaves through regeneration, and acid mist is zero. "
                   "V1 does not calculate electrolyte recycle, so S30R is zero and S30P is the full purge to neutralisation. "
                   "HCl is reported on V1's 100% equivalent basis. Totals use a lumped liquid/water balance, "
                   "not a complete chemical speciation model. Stream totals do not replace V1's electrolyte "
                   "concentration targets or its existing waste-cost estimates.")


# ====================================================== 4 EQUIPMENT & CAPEX
with tabs[TABS.index('Equipment & CAPEX')]:
    st.subheader("Equipment and capital")
    cm = st.session_state.cfg.capex_mode
    st.info(f"**{CAPEX_MODES[cm]}**")

    if cm == "user_total" and not baseline:
        st.markdown("#### Your capital estimate")
        u = st.session_state.cfg.capex_user
        c = st.columns(3)
        fci = c[0].number_input("Total FCI (AUD)", value=float(u.fci_aud), step=1e6,
                                format="%.0f")
        cap = c[1].number_input("Capacity that FCI belongs to (t Ga/yr)",
                                value=float(u.capacity_t_yr), step=1.0)
        exp = c[2].number_input("Scaling exponent", value=float(u.scaling_exponent),
                                step=0.05, format="%.2f")
        st.session_state.cfg = dataclasses.replace(
            st.session_state.cfg,
            capex_user=config.CapexUserTotal(fci, cap, exp, u.note))
        st.caption("Scaled to the model capacity on the stated exponent, then divided back "
                   "through the OSBL, engineering and contingency chain so those factors "
                   "are not applied on top of a number that already contains them.")

    if cm == "per_stage" and not baseline:
        st.markdown("#### Installed cost per unit operation")
        st.caption("**Installed** means delivered, erected and connected. These eleven "
                   "numbers sum to ISBL; OSBL, engineering and contingency then apply on "
                   "top to reach FCI. They are not bare equipment and not a share of FCI.")
        vals = dict(st.session_state.cfg.capex_stage.values)
        cols = st.columns(3)
        for i, (u, nm) in enumerate(UNIT_OPS):
            with cols[i % 3]:
                vals[u] = st.number_input(f"{u} — {nm}", value=float(vals.get(u, 0.0)),
                                          step=1e6, format="%.0f", key=f"stage_{u}")
        st.session_state.cfg = dataclasses.replace(
            st.session_state.cfg, capex_stage=config.CapexPerStage(vals))
        st.metric("ISBL from your entries", f"A${sum(vals.values()) / 1e6:,.1f}M")
        if sum(vals.values()) == 0:
            st.error("Every stage is zero, so all capital-derived figures are zero.")

    for n in R.capex.notes:
        st.caption(f"→ {n}")

    st.markdown("#### Capital build-up")
    cx = R.capex
    st.dataframe(pd.DataFrame([
        {"Item": "ISBL from the correlated equipment list", "AUD": cx.isbl_correlated_aud},
        {"Item": "Directly priced items (resin charge, rectifier)", "AUD": cx.isbl_direct_aud},
        {"Item": "ISBL, raw bottom-up", "AUD": cx.isbl_raw_aud},
        {"Item": f"ISBL applied (completeness factor {cx.completeness_factor:g})",
         "AUD": cx.isbl_aud},
        {"Item": "OSBL (offsites and utilities)", "AUD": cx.osbl_aud},
        {"Item": "Engineering and project management", "AUD": cx.engineering_aud},
        {"Item": "Contingency", "AUD": cx.contingency_aud},
        {"Item": "FIXED CAPITAL INVESTMENT", "AUD": cx.fci_aud},
        {"Item": "Working capital", "AUD": cx.working_capital_aud},
        {"Item": "TOTAL CAPITAL INVESTMENT", "AUD": cx.tci_aud},
    ]).style.format({"AUD": "{:,.0f}"}), **_W, hide_index=True)

    st.markdown("#### Does the capital number stand up?")
    st.caption("Three independent benchmarks. This is the weakest part of the estimate and "
               "it is shown rather than hidden.")
    c = st.columns(4)
    c[0].metric("Raw bottom-up FCI", f"A${cx.fci_raw_aud / 1e6:,.0f}M")
    c[1].metric("Comparable-plant FCI", f"A${cx.fci_reference_aud / 1e6:,.0f}M")
    c[2].metric("Raw as a share of comparable", f"{cx.raw_share_of_reference * 100:,.0f}%")
    c[3].metric("Capital intensity", f"US${cx.intensity_usd_k_per_t:,.0f}k per t/yr")

    st.markdown("#### Itemised equipment")
    if R.equipment.out_of_range:
        st.warning(f"{R.equipment.out_of_range} item(s) sized outside their correlation's "
                   "published range — the correlation is being extrapolated.")
    eq = pd.DataFrame([{
        "ID": i.id, "Item": i.name, "UP": i.unit_op, "Corr": i.corr, "N": i.n_duty,
        "S each": i.s_each, "S unit": i.s_unit, "S min": i.s_min, "S max": i.s_max,
        "In range?": i.in_range, "Ce total (2010 US$)": i.ce_total_usd2010,
        "Installed (2010 US$)": i.installed_usd2010, "Sizing basis": i.basis}
        for i in R.equipment.items])
    st.dataframe(eq.style.format({"N": "{:.0f}", "S each": "{:,.4g}", "S min": "{:,.4g}",
                                  "S max": "{:,.4g}", "Ce total (2010 US$)": "{:,.0f}",
                                  "Installed (2010 US$)": "{:,.0f}"}),
                 **_W, hide_index=True)
    st.caption("Towler & Sinnott, Chemical Engineering Design 2nd ed., Table 7.2. "
               "Basis US Gulf Coast, January 2010, CEPCI 532.9.")

    st.markdown("#### Capital by unit operation")
    cb = pd.DataFrame([{"unit": u, "ISBL (AUD)": cx.isbl_by_up.get(u, 0.0)}
                       for u, _ in UNIT_OPS])
    st.altair_chart(charts.simple_bar(cb, "unit", "ISBL (AUD)",
                                      "ISBL by unit operation", "Unit", "AUD",
                                      horizontal=False, fmt=",.0f"),
                    **_W)


# ======================================================== 5 OPERATING COST
with tabs[TABS.index('Operating cost')]:
    st.subheader("Operating cost")
    ox = R.opex
    c = st.columns(3)
    c[0].metric("Variable", f"A${ox.variable_total / 1e6:,.2f}M/yr")
    c[1].metric("Fixed", f"A${ox.fixed_total / 1e6:,.2f}M/yr")
    c[2].metric("Cash operating cost", f"A${fmt(ox.cash_cost_per_kg)}/kg Ga")
    if R.energy.use_mix:
        st.info(f"The blended electricity price of A${fmt(R.energy.mix_price)}/MWh is "
                "feeding OPEX (Energy mix tab, financial connection = Yes).")

    st.markdown("#### Variable cost")
    vt = pd.DataFrame([{"Line": k, "Quantity": ox.quantities[k][0],
                        "Unit": ox.quantities[k][1], "AUD/yr": v,
                        "AUD/kg Ga": v / R.params["CapProd"]}
                       for k, v in ox.variable.items()])
    st.dataframe(vt.style.format({"Quantity": "{:,.1f}", "AUD/yr": "{:,.0f}",
                                  "AUD/kg Ga": "{:,.2f}"}),
                 **_W, hide_index=True)

    st.markdown("#### Fixed cost")
    ft = pd.DataFrame([{"Line": k, "AUD/yr": v, "AUD/kg Ga": v / R.params["CapProd"]}
                       for k, v in ox.fixed.items()])
    st.dataframe(ft.style.format({"AUD/yr": "{:,.0f}", "AUD/kg Ga": "{:,.2f}"}),
                 **_W, hide_index=True)

    st.markdown("#### Cost stack per kilogram")
    stack = pd.DataFrame([{"Line": k, "AUD/kg Ga": v}
                          for k, v in sorted(ox.stack_per_kg.items(),
                                             key=lambda kv: -kv[1]) if v > 0])
    st.altair_chart(charts.simple_bar(stack, "Line", "AUD/kg Ga",
                                      "Cash operating cost stack", "Line", "AUD / kg Ga"), **_W)
    st.caption(f"Variable cost is A${ox.variable_total / R.params['CapProd']:,.2f} of the "
               f"A${R.lcop:,.2f} production cost. The rest is fixed cost and capital "
               "charge, both distributed on installed-capital share — so the per-unit "
               "charts substantially restate which unit owns the most equipment.")


# ======================================================== 6 COST BY UNIT
with tabs[TABS.index('Cost by unit')]:
    st.subheader("Cost by unit operation")
    st.caption("Allocation changes attribution, never totals. The reconciliation below "
               "proves every column sums back to the figure it came from.")

    rows = [{"unit": u, "Operation": nm,
             "Variable": R.cost_by_up[u]["variable"],
             "Fixed": R.cost_by_up[u]["fixed"],
             "Cash": R.cost_by_up[u]["cash"],
             "Capital charge": R.cost_by_up[u]["capital"],
             "Production cost": R.cost_by_up[u]["production"],
             "Share": R.cost_by_up[u]["production"] / R.lcop if R.lcop else 0}
            for u, nm in UNIT_OPS]
    df = pd.DataFrame(rows)
    st.altair_chart(charts.stacked_by_unit(
        df, ["Variable", "Fixed", "Capital charge"],
        "Production cost by unit operation", "AUD / kg Ga"), **_W)
    st.dataframe(df.drop(columns=["unit"]).assign(Unit=[u for u, _ in UNIT_OPS])
                 [["Unit", "Operation", "Variable", "Fixed", "Cash", "Capital charge",
                   "Production cost", "Share"]]
                 .style.format({"Variable": "{:,.2f}", "Fixed": "{:,.2f}",
                                "Cash": "{:,.2f}", "Capital charge": "{:,.2f}",
                                "Production cost": "{:,.2f}", "Share": "{:.1%}"}),
                 **_W, hide_index=True)

    st.markdown("#### Physical allocation register")
    ph = pd.DataFrame([{"Unit": u, **{lbl: R.allocation.phys[u][k]
                                      for k, lbl, _un in
                                      __import__("openga_v1.allocation",
                                                 fromlist=["RESOURCES"]).RESOURCES}}
                       for u, _ in UNIT_OPS])
    st.dataframe(ph.style.format({c: "{:,.4g}" for c in ph.columns if c != "Unit"}),
                 **_W, hide_index=True)
    st.metric("Worst allocation residual", f"{R.allocation.max_residual:.2e}",
              help="Across all eleven resource columns and the capital share. "
                   "Zero means the split is a genuine decomposition.")

    with st.expander("Allocation conventions, stated rather than buried"):
        st.markdown("""
- **Sulfuric acid → UP4**, the acid make-up unit, not UP5 where it is consumed.
- **Resin make-up → UP6**, where the resin is replaced. The initial resin **charge**
  stays capital at UP2 and is not double counted.
- **Liquor circuit pumping → UP1/UP2** on `AL_LIQ1`, the single typed allocation
  share in the model. The 40 m head lumps take-off, filter press, ion exchange bed
  and return, and cannot be split without a hydraulic model.
- **Secondary pumping → UP3/UP5/UP6** by the volumes each circuit moves.
- **Ancillary power and all fixed cost** by installed-capital share. Maintenance and
  insurance are exact on that basis; labour and overhead on it is an assumption — a
  real plant staffs to shifts and complexity, not to capital.
- **Raw water** grossed up for treatment reject, then split pro-rata by net demand.
""")


# ============================================================== 7 CARBON
with tabs[TABS.index('Carbon')]:
    st.subheader("Energy mix and carbon")
    en, cb = R.energy, R.carbon

    st.markdown("#### Electricity mix")
    st.caption("Shares of electricity **delivered to the process**. Each between 0% and "
               "100%, summing to exactly 100%. Nothing is normalised.")
    if not baseline:
        cols = st.columns(5)
        for i, (key, name, pkey) in enumerate(ROUTES):
            with cols[i]:
                cur = mi.params[pkey] * 100
                v = st.number_input(name, value=float(cur), min_value=-50.0,
                                    max_value=150.0, step=5.0, key=f"mix_{pkey}")
                if abs(v / 100 - meta(pkey)["default"]) > 1e-12:
                    st.session_state.overrides[pkey] = v / 100
                else:
                    st.session_state.overrides.pop(pkey, None)
    if en.valid:
        st.success(f"Mix is valid — shares sum to {en.share_sum * 100:.2f}%.")
    else:
        st.error(en.invalid_reason)

    c = st.columns(4)
    c[0].metric("Blended electricity price", f"A${fmt(en.mix_price)}/MWh",
                delta=f"{en.mix_price - en.grid_price:+,.2f} vs 100% grid")
    c[1].metric("Supply emissions intensity", f"{en.mix_ef_total:.4f} kg CO₂e/kWh",
                delta=f"{en.mix_ef_total - en.grid_ef_total:+.4f}")
    c[2].metric("Plant carbon intensity", f"{fmt(cb.total, 2)} kg CO₂e/kg Ga",
                delta=f"{cb.total - cb.ref_total:+,.2f} vs 100% grid")
    c[3].metric("Annual emissions", f"{cb.annual_t_all:,.0f} t CO₂e/yr")

    st.markdown("#### Route register")
    st.caption("Every value per kWh **delivered**. Generator efficiency and battery "
               "round-trip losses are applied once, here, and never again downstream.")
    reg = pd.DataFrame([{"Route": rt.name, "Share": rt.share, "Price (AUD/MWh)": rt.price,
                         "Scope 1": rt.ef_s1, "Scope 2": rt.ef_s2, "Upstream": rt.ef_up,
                         "Status": rt.status, "Conf": rt.confidence,
                         "Boundary": rt.boundary, "Source": rt.source}
                        for rt in en.routes])
    st.dataframe(reg.style.format({"Share": "{:.1%}", "Price (AUD/MWh)": "{:,.2f}",
                                   "Scope 1": "{:.6f}", "Scope 2": "{:.6f}",
                                   "Upstream": "{:.6f}"}),
                 **_W, hide_index=True)

    st.divider()
    st.markdown("#### Emissions by unit operation")
    rows = [{"unit": u, "Scope 1": cb.by_up[u]["scope1"], "Scope 2": cb.by_up[u]["scope2"],
             "Upstream": cb.by_up[u]["upstream"]} for u, _ in UNIT_OPS]
    st.altair_chart(charts.stacked_by_unit(
        pd.DataFrame(rows), ["Scope 1", "Scope 2", "Upstream"],
        "Carbon intensity by unit operation", "kg CO₂e / kg Ga"), **_W)
    ct = pd.DataFrame([{"Unit": u, "Operation": nm,
                        "Electricity (kWh/kg)": cb.by_up[u]["electricity_kwh"],
                        "Scope 1": cb.by_up[u]["scope1"], "Scope 2": cb.by_up[u]["scope2"],
                        "Upstream": cb.by_up[u]["upstream"], "Total": cb.by_up[u]["total"],
                        "Share": cb.by_up[u]["total"] / cb.total if cb.total else 0}
                       for u, nm in UNIT_OPS])
    st.dataframe(ct.style.format({"Electricity (kWh/kg)": "{:,.3f}", "Scope 1": "{:,.3f}",
                                  "Scope 2": "{:,.3f}", "Upstream": "{:,.3f}",
                                  "Total": "{:,.3f}", "Share": "{:.1%}"}),
                 **_W, hide_index=True)

    st.markdown("#### Selected mix against 100% grid")
    cmp_df = pd.DataFrame([
        {"Measure": "Electricity emissions", "Selected mix": cb.total - cb.non_electricity,
         "100% grid": cb.ref_elec_emissions},
        {"Measure": "Non-electricity emissions", "Selected mix": cb.non_electricity,
         "100% grid": cb.non_electricity},
        {"Measure": "Total plant intensity", "Selected mix": cb.total,
         "100% grid": cb.ref_total},
    ])
    cmp_df["Change"] = cmp_df["Selected mix"] - cmp_df["100% grid"]
    st.dataframe(cmp_df.style.format({"Selected mix": "{:,.3f}", "100% grid": "{:,.3f}",
                                      "Change": "{:+,.3f}"}),
                 **_W, hide_index=True)
    st.caption("Non-electricity emissions are identical in both columns by construction — "
               "that is the point of the comparison.")

    c = st.columns(2)
    c[0].metric("Scope 1 + 2", f"{fmt(cb.scope12, 2)} kg CO₂e/kg",
                help="Site emissions only. This is the figure that rests on published "
                     "Australian factors.")
    c[1].metric("Electricity share of total", f"{cb.electricity_share:.1%}")

    with st.expander("Boundary — what is inside and what is not"):
        st.markdown("""
**Inside.** Onsite fuel combustion (scope 1). Purchased electricity and purchased steam
(scope 2). Upstream and embodied emissions for grid network losses, upstream natural gas
supply, renewable and battery manufacturing, and the purchased sulfuric acid, caustic,
lime, hydrochloric acid, resin, water, treatment reject and solid residue the MEB
quantifies.

**Outside.** Plant construction and equipment manufacture. Decommissioning. Employee
transport. Fugitive process emissions other than the fuel supply chain. Reagent and
residue transport. Refrigerants. Land use change. Every impact category other than
global warming.

**This is a screening inventory, not a complete product LCA.** Do not present it as one.

**The Bayer liquor carries zero upstream burden** by cut-off: the slipstream is drawn
from and returned to a refinery circuit that would run anyway. That is the largest
boundary decision here. An economic or mass allocation would load part of the alumina
footprint onto the gallium and it would not be small. No avoided-burden credit is taken
for the sodium sulfate returned to the host.

**No dispatch check.** Annual assumed delivered shares only. Nothing here tests hourly
matching, generation capacity, curtailment, firming or battery sizing. A 100% direct
solar mix is arithmetically valid here and physically impossible for a continuous
process.
""")


# ============================================================== 8 FINANCE
with tabs[TABS.index('Finance')]:
    st.subheader("Finance")
    f = R.finance
    c = st.columns(4)
    c[0].metric("Real WACC", f"{f.real_wacc:.4%}")
    c[1].metric("Annuity factor", fmt(f.annuity, 4))
    c[2].metric("Production cost", f"A${fmt(f.production_cost_per_kg)}/kg")
    c[3].metric("p*", f"A${fmt(f.pstar)}/kg")
    c = st.columns(4)
    c[0].metric("Cash cost", f"A${fmt(f.cash_cost_per_kg)}/kg")
    c[1].metric("Capital charge", f"A${fmt(f.capital_charge_per_kg)}/kg")
    c[2].metric("Production cost (USD)", f"US${fmt(f.production_cost_usd)}/kg")
    c[3].metric("p* (USD)", f"US${fmt(f.pstar_usd)}/kg")

    st.metric("NPV at p*", f"A${f.npv_at_pstar:,.6f}",
              help="The 31-year cash flow is built independently of the closed-form p*. "
                   "It must vanish there.")

    st.markdown("#### 31-year real cash flow")
    cf = pd.DataFrame(f.cash_flow)
    st.dataframe(cf.style.format({c: "{:,.0f}" for c in cf.columns
                                  if c not in ("year", "discount")}
                                 | {"discount": "{:.6f}"}),
                 **_W, hide_index=True, height=340)
    st.caption("Real, constant 2026 AUD, discounted at the real WACC. Nominal "
               "historical-cost tax depreciation is deflated by (1+i)^-t before "
               "discounting, so a real DCF is not credited with a nominal shield.")


# =============================================================== 9 POLICY
with tabs[TABS.index('Policy')]:
    st.subheader("Policy")
    st.warning("These are hypothetical packages, not government commitments. No grant "
               "programme has committed anything, Export Finance Australia publishes no "
               "universal concessional rate, and the grant's tax treatment would need a "
               "ruling.")
    pol = R.policy

    if st.session_state.cfg.policy_model == "v31":
        st.markdown("#### All four packages on one set of physical assumptions")
        sw = pd.DataFrame(engine.scenario_sweep(mi))
        st.dataframe(sw[["id", "name", "pstar", "pstar_usd", "reduction", "reduction_pct",
                         "wacc_real", "grant", "supported_debt", "pv_concession",
                         "cmpti_annual", "pv_cmpti"]]
                     .style.format({"pstar": "{:,.2f}", "pstar_usd": "{:,.2f}",
                                    "reduction": "{:,.2f}", "reduction_pct": "{:.2%}",
                                    "wacc_real": "{:.4%}", "grant": "{:,.0f}",
                                    "supported_debt": "{:,.0f}",
                                    "pv_concession": "{:,.0f}",
                                    "cmpti_annual": "{:,.0f}", "pv_cmpti": "{:,.0f}"}),
                     **_W, hide_index=True)
        st.altair_chart(charts.simple_bar(
            sw.assign(label=sw["name"])[["label", "pstar"]].rename(
                columns={"label": "Package", "pstar": "p*"}),
            "Package", "p*", "Minimum viable price by policy package", "Package",
            "AUD / kg Ga", horizontal=False), **_W)

        st.markdown("#### Financing build-up")
        fb = pol.financing
        st.dataframe(pd.DataFrame([
            {"Item": "Debt / equity", "Value": fb.debt_equity},
            {"Item": "Levered beta (Hamada)", "Value": fb.beta_levered},
            {"Item": "Cost of equity Ke (nominal, CAPM)", "Value": fb.ke},
            {"Item": "Commercial cost of debt (nominal)", "Value": fb.kd_commercial},
            {"Item": "Blended cost of debt (nominal)", "Value": fb.kd_blended},
            {"Item": "Kd used in WACC", "Value": fb.kd_in_wacc},
            {"Item": "WACC, nominal", "Value": fb.wacc_nominal},
            {"Item": "WACC, real", "Value": fb.wacc_real},
        ]).style.format({"Value": "{:,.6f}"}), **_W, hide_index=True)
        st.caption("Under FINMODE 2 (the default) the WACC keeps the **commercial** rate "
                   "and the concession is valued separately over its actual tenor. "
                   "Blending it into the WACC as well would count the same benefit twice.")

        st.markdown("#### CMPTI eligibility register")
        er = pd.DataFrame(policy_mod.eligibility_register(R.opex.variable, R.opex.fixed))
        st.dataframe(er.style.format({"cost": "{:,.0f}", "fraction": "{:.0%}",
                                      "eligible": "{:,.0f}"}),
                     **_W, hide_index=True)
        st.caption("The fractions are what this register asserts, not what the ATO has "
                   "confirmed for a gallium flowsheet. Nothing here has been tested.")
    else:
        st.markdown("#### Legacy WP4 scenario")
        st.write(f"**{pol.label}**")
        st.dataframe(pd.DataFrame([
            {"Item": "OPEX offset", "Value": f"{pol.value.opex_offset:.0%}"},
            {"Item": "Real WACC", "Value": f"{pol.value.real_wacc:.3%}"},
            {"Item": "Price floor (AUD/kg)", "Value": f"{pol.value.price_floor:,.0f}"},
        ]), **_W, hide_index=True)

    for n in pol.notes:
        st.caption(f"→ {n}")

    if pol.concession_schedule:
        st.markdown("#### Concessional benefit schedule")
        cs = pd.DataFrame(pol.concession_schedule)
        st.altair_chart(charts.simple_bar(
            cs.assign(Year=cs["year"].astype(str))[["Year", "saving"]].rename(
                columns={"saving": "After-tax interest saving"}),
            "Year", "After-tax interest saving",
            "After-tax interest saving over the loan tenor", "Year", "AUD",
            horizontal=False, fmt=",.0f"), **_W)
        st.caption("Zero after the tenor expires. A concessional loan runs for its term, "
                   "not for the life of the plant.")


# =========================================================== 10 SENSITIVITY
with tabs[TABS.index('Sensitivity')]:
    st.subheader("Sensitivity and Monte Carlo")
    target = st.radio("Target", ["pstar", "lcop", "carbon"], horizontal=True,
                      format_func=lambda t: {"pstar": "Minimum viable price p*",
                                             "lcop": "Production cost",
                                             "carbon": "Carbon intensity"}[t])
    base_v = {"pstar": R.pstar, "lcop": R.lcop, "carbon": R.carbon.total}[target]
    unit = "kg CO₂e / kg Ga" if target == "carbon" else "AUD / kg Ga"

    tor = analysis.tornado(mi, target=target)
    st.altair_chart(charts.tornado(tor, base_v, "One-at-a-time swing about the base case",
                                   f"Change in {unit}"), **_W)
    st.dataframe(pd.DataFrame(tor)[["label", "low_input", "high_input", "low", "high",
                                    "swing", "basis"]]
                 .style.format({"low_input": "{:,.4g}", "high_input": "{:,.4g}",
                                "low": "{:,.2f}", "high": "{:,.2f}", "swing": "{:,.2f}"}),
                 **_W, hide_index=True)

    st.divider()
    st.markdown("#### Monte Carlo")
    c = st.columns(3)
    trials = c[0].select_slider("Trials", [200, 500, 1000, 2000, 5000], value=1000)
    seed = c[1].number_input("Seed", value=20260909, step=1)
    run_mc = c[2].button("Run", type="primary", **_W)

    if run_mc or st.session_state.get("mc_done"):
        if run_mc or "mc" not in st.session_state:
            with st.spinner(f"Running {trials} trials…"):
                st.session_state.mc = analysis.monte_carlo(mi, trials=int(trials),
                                                           seed=int(seed))
            st.session_state.mc_done = True
        mc = st.session_state.mc
        key = {"pstar": "pstar", "lcop": "lcop", "carbon": "carbon"}[target]
        vals, sstats = mc[key], mc["stats"][key]
        c = st.columns(5)
        for i, k in enumerate(["p10", "p50", "p90", "mean", "sd"]):
            c[i].metric(k.upper(), fmt(sstats[k]))
        st.altair_chart(charts.histogram(
            analysis.histogram(vals, 20),
            f"Distribution of {'p*' if target == 'pstar' else target} "
            f"({mc['trials']:,} trials)", unit,
            markers={"P10": sstats["p10"], "P50": sstats["p50"], "P90": sstats["p90"]}),
            **_W)
        st.caption("Read the tail, not the mode. The distribution is right-skewed because "
                   "assay, recovery and the completeness factor all cut one way. The P90 "
                   "is the number a lender looks at.")
        st.markdown("##### Distribution specification")
        st.dataframe(pd.DataFrame([{"Input": s.label, "Low": s.low, "Mode": s.mode,
                                    "High": s.high, "Basis": s.basis}
                                   for s in mc["specs"]])
                     .style.format({"Low": "{:,.4g}", "Mode": "{:,.4g}", "High": "{:,.4g}"}),
                     **_W, hide_index=True)
        st.caption("Triangular, because for most of these a plausible range and a most "
                   "likely value are all anyone can defend.")
    else:
        st.info("Press **Run** to sample. A thousand trials takes well under a second — "
                "the model runs in full on every draw, so nothing is approximated.")


# ====================================================== 11 CHECKS & SOURCES
with tabs[TABS.index('Checks & sources')]:
    st.subheader("Checks and sources")
    groups = validation.run_all(mi)
    summ = validation.summary(groups)
    c = st.columns(4)
    c[0].metric("Internal consistency", summ["internal"])
    c[1].metric("Workbook regression", summ["regression"])
    c[2].metric("Documented divergences", summ["divergence"])
    c[3].metric("Unresolved assumptions", summ["v3.5"])
    findings = [ck for ck in groups["v3.5"] if ck.verdict == "FAIL"]
    if findings:
        st.warning("**" + str(len(findings)) + " unresolved assumption(s).** These are findings, "
                   "not arithmetic failures. Each marks a choice that was invisible before it "
                   "became an input:\n\n"
                   + "\n\n".join(f"- **{ck.name}** — {ck.note}" for ck in findings))

    for gname, gtitle, blurb in [
        ("internal", "Internal consistency",
         "Arithmetic and closure. A failure here means the model is broken, not merely "
         "uncertain."),
        ("regression", "Workbook regression",
         "Does the port still reproduce OpenGa_v3.5_MEB.xlsx? A failure means the "
         "Python and the workbook have drifted apart."),
        ("divergence", "Documented divergences",
         "Places where this model and the published inventory part company. These are "
         "NOT failures — they are reported so the difference is visible."),
        ("v3.5", "Unresolved assumptions",
         "Resin duty, electrolyte admissibility and the solid-residue reconciliation. Two of "
         "these are expected to fail at the shipped defaults: the resin life is carried in "
         "calendar years while the cited source reports cycles, and aluminium is excluded from "
         "the resin capacity calculation. Neither is arithmetic — both are choices you have to "
         "defend."),
    ]:
        st.markdown(f"#### {gtitle}")
        st.caption(blurb)
        rows = [{"Check": ck.name, "Model": ck.model, "Reference": ck.reference,
                 "Deviation": ck.deviation, "Verdict": ck.verdict, "Note": ck.note}
                for ck in groups[gname]]
        st.dataframe(pd.DataFrame(rows).style.format(
            {"Model": "{:,.6g}", "Reference": "{:,.6g}", "Deviation": "{:.3e}"}),
            **_W, hide_index=True)

    st.divider()
    st.markdown("#### What this verification does not do")
    st.markdown("""
It confirms arithmetic, unit consistency, scope discipline and reconciliation, and that
the Python reproduces the workbook. **It validates no input.** It cannot tell you whether
the feed assay, the caustic dose, the completeness factor, any route price or any
embodied emission factor is right — and most of them are labelled PLACEHOLDER or
ESTIMATE for exactly that reason.
""")

    st.markdown("#### Inputs by evidence status")
    stat = {}
    for k in mi.params:
        m = meta(k)
        if "default" in m:
            stat.setdefault(m["status"], []).append(k)
    st.dataframe(pd.DataFrame([{"Status": s, "Count": len(v),
                                "Keys": ", ".join(sorted(v)[:14]) + ("…" if len(v) > 14 else "")}
                               for s, v in sorted(stat.items(), key=lambda kv: -len(kv[1]))]),
                 **_W, hide_index=True)

    st.markdown("#### Principal sources")
    st.markdown("""
- **Towler & Sinnott**, *Chemical Engineering Design* 2nd ed., Table 7.2 — purchased
  equipment correlations, Hand factors, location factor, OSBL/engineering/contingency.
- **DCCEEW**, *Australian National Greenhouse Accounts Factors 2025* — WA SWIS scope 2
  and scope 3, natural gas combustion and state upstream factors.
- **CSIRO**, *GenCost 2025-26* — battery capital, NEM generation price band.
- **IEEFA** (Nov 2025) — Western Australian domestic gas contract and spot prices.
- **Energies** 2025, 18(24):6413 — utility PV and onshore wind life-cycle intensities.
- **GJETA** 2025 — utility-scale lithium-ion round-trip efficiency, cycle life,
  manufacturing emissions.
- **Lu et al. 2026**, *Solar Energy* 303 — onsite PV+BESS and Australian industrial
  grid tariff range.
- **Luo et al. 2025**, *Int. J. Life Cycle Assess.* 30:1545–1559 — the only
  industrial-scale primary gallium LCA. See the divergence table above for the Table 2
  exponent defect.
- **Zhao et al. 2016**, *ACS Sust. Chem. Eng.*; **Gorzin et al.**; **Materials** 2024,
  17(16), 4109 — resin performance.
- **Wesselkaemper et al. 2025**; **Alcoa** Wagerup disclosures — capital comparables.
""")
