"""Step 2: the recovery flowsheet, resin, reagents and electrowinning."""

import pandas as pd
import streamlit as st

import state
import ui
from openga_v1.config import UNIT_OPS
from openga_v1.streams import balance_rows, stream_issues
from openga_flowsheet.app_flowsheet_tab import flowsheet_tab

ui.step_intro(
    "2. Gallium recovery process",
    "Describes the flowsheet from clarified liquor to refined metal: how much gallium each "
    "unit operation passes on, how the ion exchange resin performs, the reagent doses and "
    "the electrowinning cell. Together these set overall recovery, reagent use and "
    "electricity demand.",
    "overall gallium recovery, electricity per kilogram, the live flowsheet and the mass "
    "and energy balance.")

ui.how_to(
    ["Choose a **resin preset**. It sets ion exchange recovery, co-adsorption and capacity "
     "together. Choose **Custom** to type your own vendor or pilot values.",
     "Leave the **energy model** on v3.3 mechanistic unless you are reproducing the legacy "
     "WP3 workbook.",
     "Review the recovery cascade. Overall recovery is the product of the eleven unit "
     "recoveries, so a small change in each compounds.",
     "Change reagent doses and electrowinning settings only with a source.",
     "Press **Run model** to draw the flowsheet and the balance tables."],
    ["Overall recovery, liquor throughput and electricity per kilogram.",
     "A flowsheet coloured by total mass, Ga, Al or V, which you can download as SVG.",
     "Recovery, reagent, energy and ion exchange sizing tables, and stream checks."])

st.subheader("Method choices")
c = st.columns(2)
with c[0]:
    state.resin_select()
with c[1]:
    state.energy_select()

st.subheader("Inputs")
state.input_sections([("Process", "Recovery cascade, UP1 to UP11"),
                      ("Process", "Ion exchange performance"),
                      ("Process", "Reagent doses and strengths"),
                      ("Process", "Electrowinning and electrolyte"),
                      ("Process", "Energy and duty")])
state.run_footer("process")

st.subheader("Process results")
box = state.results_container()
if box is None:
    ui.empty_state("Press **Run model** to draw the flowsheet and the mass and energy "
                   "balance.")
else:
    with box:
        R = state.results()
        m = R.meb
        c = st.columns(3)
        c[0].metric("Overall gallium recovery", f"{m.recovery_overall * 100:,.1f}%")
        c[1].metric("Liquor per kg of gallium (t)", f"{m.liquor_t_per_kg:,.1f}")
        c[2].metric("Electricity per kg of gallium (kWh)", f"{m.elec_kwh_kg:,.1f}")

        st.markdown("#### Flowsheet")
        display = st.radio("Diagram display", ["Image", "Interactive"], horizontal=True,
                           key="flowsheet_display",
                           help="Image fits the whole diagram to the panel. Interactive "
                                "keeps card tooltips and horizontal scrolling.")
        issues = stream_issues(R.streams)
        if issues:
            st.warning("Some inputs produce invalid stream quantities. Review the stream "
                       "checks below before using this result.")
        flowsheet_tab(R.streams, key="v2_flowsheet", display_mode=display.lower())

        st.markdown("#### Mass and energy balance")
        st.caption("Basis: one kilogram of 4N gallium. Reagents from stoichiometry, energy "
                   "from duty.")
        with st.expander("Recovery by unit operation"):
            ui.table(pd.DataFrame([{"Unit": u, "Operation": nm, "Recovery": m.recoveries[u],
                                    "Ga out (kg)": m.ga_out[u]} for u, nm in UNIT_OPS]),
                     {"Recovery": "{:.2%}", "Ga out (kg)": "{:.4f}"})
            st.caption(f"Feed gallium required: {m.feed_ga_kg:,.3f} kg per kg of product.")
        with st.expander("Reagents"):
            ui.table(pd.DataFrame([
                {"Reagent": "H₂SO₄ contained in eluant", "kg per kg Ga": m.h2so4_contained},
                {"Reagent": "H₂SO₄ delivered (98%)", "kg per kg Ga": m.h2so4_delivered},
                {"Reagent": "NaOH at UP7 (precipitation)", "kg per kg Ga": m.naoh_up7},
                {"Reagent": "NaOH at UP9 (purification)", "kg per kg Ga": m.naoh_up9},
                {"Reagent": "NaOH total", "kg per kg Ga": m.naoh_total},
                {"Reagent": "Na₂SO₄ formed (to host circuit)", "kg per kg Ga": m.na2so4},
                {"Reagent": "CaO", "kg per kg Ga": m.cao},
                {"Reagent": "HCl", "kg per kg Ga": m.hcl},
                {"Reagent": "Resin make-up", "kg per kg Ga": m.resin_makeup},
            ]), {"kg per kg Ga": "{:,.3f}"})
        with st.expander("Energy"):
            ui.table(pd.DataFrame([
                {"Load": "Liquor circuit pumping", "kW": m.kw_liquor},
                {"Load": "Wash, eluant and transfer pumping", "kW": m.kw_secondary},
                {"Load": "Electrowinning", "kW": m.kw_ew},
                {"Load": "Ancillary allowance", "kW": m.kw_misc},
                {"Load": "Total", "kW": m.kw_total},
            ]), {"kW": "{:,.1f}"})
            st.caption(f"Steam: {m.steam_kg_kg:,.2f} kg per kg Ga. Zero in the base case "
                       "because the mechanistic caustic dose needs no evaporation.")
        with st.expander("Ion exchange sizing"):
            ui.table(pd.DataFrame([
                {"Quantity": "Bed area (hydraulic)", "Value": m.bed_area_m2, "Unit": "m²"},
                {"Quantity": "Column diameter", "Value": m.col_dia_m, "Unit": "m"},
                {"Quantity": "Resin installed, all columns", "Value": m.resin_total_kg,
                 "Unit": "kg"},
                {"Quantity": "Loading cycle time", "Value": m.cycle_h, "Unit": "h"},
                {"Quantity": "Bed volumes turned over per hour", "Value": m.bv_per_h,
                 "Unit": "m³/h"},
                {"Quantity": "Precipitate grade", "Value": m.precip_grade * 100,
                 "Unit": "wt% Ga"},
            ]), {"Value": "{:,.3f}"})
            st.caption("Bed volumes per hour does not depend on column diameter or "
                       "superficial velocity, so wash, eluant and regeneration volumes do "
                       "not depend on how the bed is arranged.")
        with st.expander("Stream checks and flowsheet basis"):
            checks = balance_rows(R.streams)
            passed = sum(row["Status"] == "PASS" for row in checks)
            st.caption(f"{passed} of {len(checks)} stream balance checks pass (total mass "
                       "and elemental Ga, Al and V).")
            st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch")
            for issue in issues:
                st.error(issue)
            st.caption("The stream register reads the same mass balance as the rest of the "
                       "app. Al elutes, V leaves through regeneration and acid mist is zero. "
                       "Electrolyte recycle is not calculated, so S30R is zero and S30P is "
                       "the full purge to neutralisation. HCl is on a 100% basis. Totals use "
                       "a lumped liquid and water balance, not a speciation model.")
ui.footer()
