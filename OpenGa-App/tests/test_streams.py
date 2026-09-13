import copy
import dataclasses
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openga_v1.config import ModelInputs, ModelConfig
from openga_v1.engine import run
from openga_v1 import validation
from openga_v1.streams import UNIT_STREAMS, build_streams, balance_rows, stream_issues, INPUT_IDS, OUTPUT_IDS
from openga_flowsheet.flowsheet import INPUTS, OUTPUTS, overview_rows, render_svg


class LiveStreamTests(unittest.TestCase):
    def test_baseline_preserves_v1_results(self):
        groups = validation.run_all(ModelInputs())
        self.assertEqual(len(groups['internal']), 14)
        self.assertEqual(len(groups['regression']), 10)
        self.assertTrue(all(c.verdict == 'PASS' for g in ('internal', 'regression') for c in groups[g]))

    def test_balances_and_nonnegative_values_across_scenarios(self):
        scenarios = [({}, 1), ({'GaFeed': 48}, 1), ({'GaFeed': 185}, 1),
                     ({'WashRec': 90}, 1), ({'PrecRec': 85}, 1),
                     ({'NaOH_UP9': 30}, 1), ({'CapProd': 200000}, 1),
                     ({}, 2), ({}, 3), ({'IXRec': 60, 'CoAdsAl': 2}, 4),
                     # V3 inputs: each must close on its own and in combination
                     ({'EWRecycle': 50}, 1), ({'EWRecycle': 90}, 1),
                     ({'ResinMode': 2}, 1), ({'BurdenAl': 1}, 1),
                     ({'RetainLiq': 0.4}, 1), ({'AlRemUP9': 99}, 1),
                     ({'CakeLiqSol': 1}, 1),
                     ({'ResinMode': 2, 'BurdenAl': 1, 'RetainLiq': 0.4,
                       'AlRemUP9': 99, 'CakeLiqSol': 1, 'EWRecycle': 90}, 1)]
        for params, resin in scenarios:
            with self.subTest(params=params, resin=resin):
                r = run(ModelInputs(cfg=ModelConfig(resin_preset=resin)).with_overrides(params))
                self.assertEqual(len(r.streams), 37)
                checks = balance_rows(r.streams)
                self.assertEqual(len(checks), 8 * len(UNIT_STREAMS))
                self.assertTrue(all(row['Status'] == 'PASS' for row in checks))
                self.assertFalse(stream_issues(r.streams))

    def test_streams_agree_with_existing_meb(self):
        r = run(ModelInputs().with_overrides({'WashRec': 95, 'PrecRec': 85}))
        s, m = r.streams, r.meb
        for stream, value in [('S1', m.feed_ga_kg), ('S3', m.ga_out['UP1']),
                              ('S5', m.ga_out['UP2']), ('S8', m.ga_out['UP3']),
                              ('S14', m.ga_out['UP5']), ('S23', m.ga_cake),
                              ('S28', m.ga_elyte), ('S31', m.ga_crude), ('S34', 1)]:
            self.assertAlmostEqual(s[stream]['Ga'], value)
        self.assertAlmostEqual(s['S1']['total_kg_per_kg_Ga'], m.liquor_kg_per_kg)
        self.assertAlmostEqual(s['S10']['total_kg_per_kg_Ga'], m.w_raw_kg)
        self.assertAlmostEqual(s['S20']['components']['NaOH'] + s['S24']['components']['NaOH'], m.naoh_total)

    def test_wash_and_precipitation_losses_are_retained(self):
        r = run(ModelInputs().with_overrides({'WashRec': 90, 'PrecRec': 80}))
        s, m = r.streams, r.meb
        self.assertAlmostEqual(s['S7']['Ga'], m.ga_out['UP2'] - m.ga_out['UP3'])
        self.assertAlmostEqual(s['S22']['Ga'], m.ga_out['UP5'] - m.ga_out['UP8'])
        self.assertGreater(s['S21']['components']['Ga'], 0)

    def test_no_boundary_double_counting(self):
        ids = [sid for g in INPUTS + OUTPUTS for sid in g.ids]
        self.assertEqual(set(ids), set(INPUT_IDS + OUTPUT_IDS))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn('S30', ids)
        self.assertNotIn('S30R', ids)
        r = run(ModelInputs())
        self.assertEqual(r.streams['S30R']['total_kg_per_kg_Ga'], 0)
        self.assertEqual(r.streams['S30']['components'], r.streams['S30P']['components'])

    def test_rendered_values_follow_changed_feed(self):
        a = run(ModelInputs())
        b = run(ModelInputs().with_overrides({'GaFeed': 140}))
        self.assertAlmostEqual(b.streams['S1']['total_kg_per_kg_Ga'], a.streams['S1']['total_kg_per_kg_Ga'] / 2)
        self.assertNotEqual(overview_rows(a.streams), overview_rows(b.streams))
        self.assertIn('71,943 kg', render_svg(a.streams))
        self.assertIn('35,972 kg', render_svg(b.streams))

    def test_all_display_variants_parse(self):
        s = run(ModelInputs()).streams
        for component in ('total', 'Ga', 'Al', 'V'):
            for theme in ('light', 'dark'):
                for interactive in (True, False):
                    svg = render_svg(s, component=component, theme=theme, interactive=interactive)
                    ET.fromstring(svg)
                    self.assertEqual('Hover cards' in svg, interactive)

    def test_reporting_does_not_mutate_model(self):
        r = run(ModelInputs())
        before = (copy.deepcopy(r.params), dataclasses.asdict(r.meb))
        build_streams(r.params, r.meb)
        self.assertEqual(before, (r.params, dataclasses.asdict(r.meb)))

    def test_invalid_stream_is_flagged_even_when_a_total_can_close(self):
        s = run(ModelInputs()).streams
        s['S30']['components']['Water'] = -1
        self.assertTrue(stream_issues(s))

    def test_electrolyte_recycle_is_modelled_and_splits_the_parent(self):
        """V2 refused any recycle. V3 solves the UP9-UP10 loop, so the test is now
        that the branches split the parent and that recovery actually rises."""
        base = run(ModelInputs())
        rec = run(ModelInputs().with_overrides({'EWRecycle': 90}))
        self.assertGreater(rec.meb.recovery_overall, base.meb.recovery_overall)
        self.assertAlmostEqual(base.streams['S30R']['total_kg_per_kg_Ga'], 0.0)
        for key in ('total_kg_per_kg_Ga', 'Ga', 'Na'):
            self.assertAlmostEqual(
                rec.streams['S30'][key],
                rec.streams['S30R'][key] + rec.streams['S30P'][key], places=9)
        # the purge carries a tenth of the parent at a 90% return
        self.assertAlmostEqual(
            rec.streams['S30P']['total_kg_per_kg_Ga']
            / rec.streams['S30']['total_kg_per_kg_Ga'], 0.10, places=9)

    def test_solid_residue_agrees_with_the_stream_table(self):
        """The V2 MEB carried the purification-cake gallium as an ELEMENT mass while
        the aluminium and lime terms were compound masses, so the disposal tonnage
        OPEX buys disagreed with the cake the stream table produces."""
        r = run(ModelInputs())
        self.assertAlmostEqual(
            r.meb.solid_residue,
            r.streams['S27']['total_kg_per_kg_Ga'] + r.streams['S19']['total_kg_per_kg_Ga'],
            places=9)

    def test_reagent_element_ledgers_close(self):
        r = run(ModelInputs().with_overrides({'CakeLiqSol': 1, 'AlRemUP9': 99}))
        rows = [x for x in balance_rows(r.streams) if x['Quantity'] in ('Na', 'S', 'Cl', 'Ca')]
        self.assertTrue(rows)
        self.assertTrue(all(x['Status'] == 'PASS' for x in rows))

    def test_stream_temperatures_and_tier1_heat_are_present(self):
        r = run(ModelInputs())
        self.assertAlmostEqual(r.streams['S1']['T_degC'], r.params['T_HOST'])
        self.assertAlmostEqual(r.streams['S10']['H_kWh_th'], 0.0)   # enters at T_AMB
        self.assertGreater(r.streams['S1']['H_kWh_th'], 0.0)

    def test_scenario_is_not_compared_to_unchanged_workbook_baseline(self):
        for mi in [ModelInputs().with_overrides({'GaFeed': 100}),
                   ModelInputs(cfg=ModelConfig(policy_package=2))]:
            checks = validation.regression(mi)
            self.assertTrue(all(c.kind == 'info' for c in checks))


if __name__ == '__main__':
    unittest.main()
