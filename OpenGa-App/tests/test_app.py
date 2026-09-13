"""Exercise the complete V2 UI and verify that image data changes on input edits."""
import base64
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'app'))


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Install requirements.txt for UI tests')
class AppTests(unittest.TestCase):
    def test_live_inputs_image_and_interactive_modes(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / 'app' / 'streamlit_app.py'), default_timeout=60).run()
        self.assertFalse(app.exception)
        self.assertIn('Flowsheet', [t.label for t in app.tabs])

        def image_svg():
            url = app.get('image')[0].proto.imgs[0].url
            self.assertTrue(url.startswith('data:image/svg+xml;base64,'))
            return base64.b64decode(url.split(',', 1)[1]).decode()

        self.assertIn('71,943 kg', image_svg())
        next(r for r in app.radio if r.label == 'Mode').set_value('User').run()
        self.assertFalse(app.exception)
        next(n for n in app.number_input if (n.key or '').endswith('_GaFeed')).set_value(100.0).run()
        self.assertFalse(app.exception)
        self.assertIn('50,360 kg', image_svg())
        self.assertEqual(app.session_state['overrides']['GaFeed'], 100)

        # Duplicate IX recovery widgets share one parameter without duplicate keys.
        next(s for s in app.selectbox if s.label == 'Resin preset').select(4).run()
        self.assertFalse(app.exception)
        ix = [n for n in app.number_input if (n.key or '').endswith('_IXRec')]
        self.assertEqual(len(ix), 2)
        ix[0].set_value(50.0).run()
        self.assertFalse(app.exception)
        self.assertTrue(all(n.value == 50 for n in app.number_input if (n.key or '').endswith('_IXRec')))

        next(b for b in app.button if b.label == 'Reset all inputs to baseline').click().run()
        self.assertFalse(app.exception)
        self.assertIn('71,943 kg', image_svg())
        self.assertEqual(next(n for n in app.number_input if (n.key or '').endswith('_GaFeed')).value, 70)

        for component in ('Ga', 'Al', 'V', 'total'):
            app.selectbox(key='v2_flowsheet_component').select(component).run()
            self.assertFalse(app.exception)
            self.assertIn('<svg', image_svg())
        app.selectbox(key='v2_flowsheet_theme').select('dark').run()
        self.assertFalse(app.exception)
        self.assertIn('#111C27', image_svg())
        app.radio(key='flowsheet_display').set_value('Interactive').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('iframe')), 1)


if __name__ == '__main__':
    unittest.main()
