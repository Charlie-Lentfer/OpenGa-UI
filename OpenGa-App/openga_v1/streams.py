"""Build the flowsheet register from V1's resolved parameters and MEB result.

The original stream IDs are retained, but numeric snapshot values are never
loaded. This is a reporting extension: it does not replace the V1 MEB or feed
new quantities into equipment, costs or carbon. Assumptions follow the supplied
stream register (all Al eluted, V retained for regeneration; no acid mist).

Totals conserve mass using a lumped liquid/water balance, as in the supplied
adapter. This is not a full chemical speciation or hydrogen/oxygen balance.
"""
from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path

from .meb import MEBResult

# Which temperature each stream is carried at. Tier-1 sensible heat only.
TEMPERATURE_OF = {
    "S1": "T_HOST", "S2": "T_IX", "S3": "T_IX", "S4": "T_IX", "S5": "T_IX",
    "S6": "T_AMB", "S7": "T_IX", "S8": "T_IX", "S9": "T_AMB", "S10": "T_AMB",
    "S11": "T_AMB", "S12": "T_AMB", "S13": "T_AMB", "S14": "T_ELU", "S15": "T_ELU",
    "S16": "T_AMB", "S17": "T_AMB", "S18": "T_ELU", "S19": "T_AMB", "S20": "T_AMB",
    "S21": "T_PREC", "S22": "T_PREC", "S23": "T_PREC", "S24": "T_AMB", "S25": "T_AMB",
    "S25b": "T_AMB", "S26": "T_PUR", "S27": "T_PUR", "S28": "T_EW", "S29": "T_EW",
    "S30": "T_EW", "S30R": "T_EW", "S30P": "T_EW", "S31": "T_EW", "S32": "T_AMB",
    "S33": "T_REF", "S34": "T_REF",
}


def total_load_ga_equiv(p: dict, m: MEBResult) -> float:
    """Ga-equivalent metal on the resin, kg/h. Mirrors meb.run."""
    return (m.ga_load_kg_h + p.get("BurdenV", 1.0) * m.v_load_kg_h
            + p.get("BurdenAl", 0.0) * m.al_load_kg_h)


@lru_cache(maxsize=1)
def _metadata():
    data = json.loads(Path(__file__).with_name("stream_metadata.json").read_text())
    return {s["id"]: s for s in data["streams"]}


# Explicit treatment interface: S30P terminates at neutralisation, rather than
# being claimed as treated effluent. Never add S30 to its two child streams.
INPUT_IDS = ("S1", "S9", "S10", "S17", "S20", "S24", "S25", "S32")
OUTPUT_IDS = ("S2", "S4", "S7", "S11", "S12", "S18", "S19", "S22", "S26",
              "S27", "S29", "S30P", "S33", "S34")
UNIT_STREAMS = {
    "UP1": (("S1",), ("S2", "S3")),
    "UP2": (("S3",), ("S4", "S5")),
    "UP3": (("S5", "S6"), ("S7", "S8")),
    "UP4": (("S9", "S10"), ("S6", "S11", "S12", "S13", "S16", "S25b")),
    "UP5": (("S8", "S13"), ("S14", "S15")),
    "UP6": (("S15", "S16", "S17"), ("S18", "S19")),
    "UP7": (("S14", "S20"), ("S21",)),
    "UP8": (("S21",), ("S22", "S23")),
    "UP9": (("S23", "S24", "S25", "S25b", "S30R"), ("S26", "S27", "S28")),
    "UP10": (("S28",), ("S29", "S30", "S31")),
    "UP11": (("S31", "S32"), ("S33", "S34")),
    "Electrolyte split": (("S30",), ("S30R", "S30P")),
    "Reported boundary": (INPUT_IDS, OUTPUT_IDS),
}


def build_streams(p: dict, m: MEBResult) -> dict:
    """Return current amounts on the V1 basis of kg per kg 4N gallium product.

    V1 has no electrolyte recycle calculation. S30R is therefore zero and S30P
    is the full spent electrolyte. Do not infer a recycle benefit from this
    reporting extension. HCl retains V1's 100% equivalent cost/mass basis.
    """
    s: dict[str, dict[str, float]] = {}
    recy = min(p.get("EWRecycle", 0.0), 99.9) / 100.0
    ga_ratio = (p["MGa"] + 3 * p["MOH"]) / p["MGa"]
    al_ratio = (p["MAl"] + 3 * p["MOH"]) / p["MAl"]

    def put(sid, **values):
        s[sid] = {k: float(v) for k, v in values.items()}

    def total(sid):
        return math.fsum(s[sid].values())

    def sub(a, b):
        return {k: s[a].get(k, 0) - s[b].get(k, 0) for k in sorted(s[a].keys() | s[b].keys())}

    # Host liquor and solids removal. The Ga loss follows the actual MEB cascade.
    thru, rho = m.liquor_kg_per_kg, p["LiqDensity"]
    al = thru * p["AlFeed"] / (1000 * rho)
    v = thru * p["VFeed"] / (1e6 * rho)
    ss = thru * p["SSLoad"] / 1000
    entrained = ss * p["FiltCakeMoist"] / (100 - p["FiltCakeMoist"])
    ga_frac = p["GaFeed"] / (1e6 * rho)
    al_frac, v_frac = p["AlFeed"] / (1000 * rho), p["VFeed"] / (1e6 * rho)
    put("S1", Ga=m.feed_ga_kg, Al=al, V=v, SS=ss,
        LiqBal=thru - m.feed_ga_kg - al - v - ss)
    put("S2", SS=ss, Ga=m.feed_ga_kg - m.ga_out["UP1"], Al=entrained * al_frac,
        V=entrained * v_frac, LiqBal=entrained * (1 - ga_frac - al_frac - v_frac))
    s["S3"] = sub("S1", "S2")

    # V1's Al/V uptake quantities are used directly to match its downstream cake.
    uptake_scale = p["OpHours"] / p["CapProd"]
    al_ads, v_ads = m.al_load_kg_h * uptake_scale, m.v_load_kg_h * uptake_scale
    put("S5", Ga=m.ga_out["UP2"], Al=al_ads, V=v_ads)
    s["S4"] = sub("S3", "S5")
    # Interstitial liquor in the bed. Zero at RetainLiq = 0, which is the v3.4
    # behaviour; above zero S5/S8 carry it and S7 displaces it into the wash waste.
    bed_L = (total_load_ga_equiv(p, m) * p["OpHours"] / p["CapProd"]
             / (p["ResinBulk"] * p["ResinCap"] / 1000.0))
    ret = bed_L * p.get("RetainLiq", 0.0) * rho
    s["S5"]["Ga"] += ret * ga_frac
    s["S5"]["V"] += ret * v_frac
    s["S5"]["Al"] += ret * al_frac
    s["S5"]["LiqBal"] = ret * (1 - ga_frac - al_frac - v_frac)
    s["S4"] = sub("S3", "S5")
    put("S6", Water=m.w_wash_kg)
    put("S7", Water=m.w_wash_kg, Ga=m.ga_out["UP2"] - m.ga_out["UP3"] + ret * ga_frac,
        V=ret * v_frac, Al=ret * al_frac,
        LiqBal=ret * (1 - ga_frac - al_frac - v_frac))
    put("S8", Ga=m.ga_out["UP3"], Al=al_ads, V=v_ads)

    # Water treatment and acid preparation; V1 does not calculate an acid mist.
    put("S9", H2SO4=m.h2so4_contained, Water=m.h2so4_delivered - m.h2so4_contained)
    put("S10", Water=m.w_raw_kg)
    put("S11", Water=m.w_rej_kg)
    # Acid mist: V2 hard-coded zero, which left the sulfur ledger with no outlet.
    mist = m.h2so4_delivered * p.get("MistFrac", 0.0)
    put("S12", H2SO4=mist)
    put("S13", H2SO4=m.h2so4_contained - mist,
        Water=m.w_elu_kg + s["S9"]["Water"])
    put("S14", Ga=m.ga_out["UP5"], Al=al_ads, V=0,
        H2SO4=s["S13"]["H2SO4"], Water=s["S13"]["Water"])
    put("S15", Ga=m.ga_out["UP3"] - m.ga_out["UP5"], Al=0, V=v_ads)
    put("S16", Water=m.w_regen_kg)
    put("S17", Resin=m.resin_makeup)
    put("S18", Water=m.w_regen_kg, Ga=s["S15"]["Ga"], V=v_ads)
    put("S19", Resin=m.resin_makeup)

    put("S20", NaOH=m.naoh_up7, Water=m.naoh_up7 * (100 / p["NaOHConc"] - 1))
    ga_hydroxide = m.ga_out["UP7"] * ga_ratio
    # Dissolved Ga stays in centrate when precipitation recovery is below 100%.
    ga_dissolved = m.ga_out["UP5"] - m.ga_out["UP7"]
    al_hydroxide = al_ads * al_ratio
    put("S21", GaOH3=ga_hydroxide, Ga=ga_dissolved, AlOH3=al_hydroxide,
        Na2SO4=m.na2so4,
        Water=total("S14") + total("S20") - ga_hydroxide - ga_dissolved - al_hydroxide - m.na2so4)
    # Cake moisture is mother liquor, not pure water, once CakeLiqSol is above zero.
    liq_sol = (m.na2so4 / s["S21"]["Water"]) if s["S21"]["Water"] > 0 else 0.0
    cake_so4 = m.cake_h2o * liq_sol * p.get("CakeLiqSol", 0.0)
    put("S23", GaOH3=m.ga_cake * ga_ratio, AlOH3=m.al_cake * al_ratio,
        Water=m.cake_h2o, Na2SO4=cake_so4)
    s["S22"] = sub("S21", "S23")

    put("S24", NaOH=m.naoh_up9, Water=m.naoh_up9 * (100 / p["NaOHConc"] - 1))
    put("S25", CaO=m.cao)
    put("S25b", Water=m.w_makeup_kg)
    put("S26", Water=m.evap_kg_h * p["OpHours"] / p["CapProd"])
    # v3.4 assumed perfect Al rejection at UP9. AlRemUP9 makes it an input, and
    # whatever is not rejected is what the electrolyte screen actually tests.
    al_rej = p.get("AlRemUP9", 100.0) / 100.0
    al_oh3_cake = m.al_cake * al_ratio
    put("S27", AlOH3=al_oh3_cake * al_rej, CaO=m.cao,
        GaOH3=m.ga_pur_cake * ga_ratio)
    # Anything the loop does not remove accumulates until the purge carries out
    # what the fresh feed brings in: circulating = fresh / (1 - r). That applies
    # to the caustic, to the aluminium that survives purification and to the
    # sulfate the cake moisture brings with it. It is the reason a 100% return
    # is not a steady state.
    al_28 = al_oh3_cake * (1 - al_rej) / al_ratio / (1 - recy)
    cake_so4 = cake_so4 / (1 - recy)
    naoh_28 = m.naoh_up9 / (1 - recy)
    in9a = (total("S23") + total("S24") + total("S25") + total("S25b")
            - total("S26") - total("S27"))
    charge_kmol = 3 * (m.ga_crude / p["MGa"]) / (p["EWCE"] / 100)
    oxygen = charge_kmol / 4 * p.get("MO2", 31.998)
    hydrogen = charge_kmol * (1 - p["EWCE"] / 100) / 2 * p.get("MH2", 2.016)
    # The loop solved algebraically so no stream refers back to itself:
    #   T = A + r(T - O2 - H2 - Ga deposited)
    elyte_total = (in9a - recy * (oxygen + hydrogen + m.ga_crude)) / (1 - recy)
    put("S28", Ga=m.ga_elyte, NaOH=naoh_28, Al=al_28, Na2SO4=cake_so4,
        Water=elyte_total - m.ga_elyte - naoh_28 - al_28 - cake_so4)

    put("S29", O2=oxygen, H2=hydrogen)
    put("S31", Ga=m.ga_crude)
    # S30 carries EVERY component of S28, not only Ga/NaOH/Water: aluminium and
    # sulfate that reach the cell have to leave it again or the balance breaks.
    s["S30"] = dict(s["S28"])
    s["S30"]["Ga"] -= m.ga_crude
    s["S30"]["Water"] -= oxygen + hydrogen
    s["S30R"] = {k: v * recy for k, v in s["S30"].items()}
    s["S30P"] = {k: v * (1 - recy) for k, v in s["S30"].items()}
    put("S32", HCl=m.hcl)
    put("S33", Ga=m.ga_crude - m.ga_out["UP11"], HCl=m.hcl)
    put("S34", Ga=m.ga_out["UP11"])

    m_o = p.get("MOH", 17.008) - 1.008
    m_hcl = p.get("MCl", 35.45) + 1.008
    m_cao = p.get("MCa", 40.078) + m_o
    t_amb = p.get("T_AMB", 25.0)
    result = {}
    for sid, components in s.items():
        md = _metadata()[sid]
        tot = math.fsum(components.values())
        water = components.get("Water", 0.0)
        liqbal = components.get("LiqBal", 0.0)
        temp = p.get(TEMPERATURE_OF.get(sid, "T_AMB"), t_amb)
        cp_mass = (water * p.get("CP_W", 4.18) + liqbal * p.get("CP_LIQ", 3.4)
                   + (tot - water - liqbal) * p.get("CP_NW", 1.5))
        result[sid] = {
            **md, "components": components,
            "total_kg_per_kg_Ga": tot,
            "Ga": components.get("Ga", 0) + components.get("GaOH3", 0) / ga_ratio,
            "Al": components.get("Al", 0) + components.get("AlOH3", 0) / al_ratio,
            "V": components.get("V", 0),
            # Reagent-derived elements. The host liquor is not speciated, so its
            # sodium sits inside LiqBal and is excluded: this is the ledger for
            # PURCHASED sodium, which is the one the caustic question turns on.
            "Na": (components.get("NaOH", 0) * p.get("MNa", 22.99) / p["MNaOH"]
                   + components.get("Na2SO4", 0) * 2 * p.get("MNa", 22.99) / p["MNa2SO4"]),
            "S": (components.get("H2SO4", 0) * p.get("MS", 32.06) / p["MH2SO4"]
                  + components.get("Na2SO4", 0) * p.get("MS", 32.06) / p["MNa2SO4"]),
            "Cl": components.get("HCl", 0) * p.get("MCl", 35.45) / m_hcl,
            "Ca": components.get("CaO", 0) * p.get("MCa", 40.078) / m_cao,
            # Tier 1 only: sensible heat referenced to the fresh-feed temperature.
            # No reaction, dilution or mixing heat, and no recovery credited.
            "T_degC": temp,
            "H_kWh_th": cp_mass * (temp - t_amb) / 3600.0,
        }
    return result


def balance_rows(streams):
    """Check the reported total mass and elemental Ga/Al/V at each interface."""
    rows = []
    for unit, (ins, outs) in UNIT_STREAMS.items():
        for label, key in (("Total mass", "total_kg_per_kg_Ga"), ("Ga", "Ga"), ("Al", "Al"),
                           ("V", "V"), ("Na", "Na"), ("S", "S"), ("Cl", "Cl"), ("Ca", "Ca")):
            incoming = math.fsum(streams[sid][key] for sid in ins)
            outgoing = math.fsum(streams[sid][key] for sid in outs)
            residual = incoming - outgoing
            # Rounded molar masses cannot close mass AND atoms at once: the workbook
            # carries M(Na2SO4) = 142.043 so sulfate MASS closes exactly, which leaves
            # about 1.3e-5 relative on the atom ledger. Elements get a relative
            # tolerance; mass and the metals keep the tight absolute one.
            if label in ("Na", "S", "Cl", "Ca"):
                tolerance = max(1e-8, abs(incoming) * 1e-4)
            else:
                tolerance = max(1e-8, abs(incoming) * 1e-10)
            rows.append({"Unit / boundary": unit, "Quantity": label, "In": incoming,
                         "Out": outgoing, "Residual": residual,
                         "Status": "PASS" if math.isfinite(residual) and abs(residual) <= tolerance else "FAIL"})
    return rows


def stream_issues(streams):
    """Report physically invalid constituents; mass closure alone is insufficient."""
    issues = []
    for sid, record in streams.items():
        for name, value in record["components"].items():
            if not math.isfinite(value) or value < -1e-8:
                issues.append(f"{sid}: {name} = {value:.6g} kg/kg Ga; check process inputs.")
    return issues
