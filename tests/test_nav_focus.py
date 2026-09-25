from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from marketing_os.web_app import create_app


class NavFocusTests(unittest.TestCase):
    def test_coverage_and_shadow_live_under_more_tools_not_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp) / "nav-focus.sqlite")
            self.addCleanup(app.config["SESSION_FACTORY"].kw["bind"].dispose)
            client = app.test_client()

            response = client.get("/products")
            self.assertEqual(200, response.status_code)
            html = response.data.decode("utf-8")

            match = re.search(
                r'<div class="nav-section">Workflow</div>(.*?)</nav>',
                html,
                flags=re.S,
            )
            self.assertIsNotNone(match)
            nav = match.group(1)
            primary, _, overflow = nav.partition("More tools")
            self.assertTrue(overflow, "expected More tools overflow section")

            for label in ("Products", "Gallery", "Video Studio"):
                self.assertIn(label, primary)

            self.assertNotIn(">Coverage<", primary)
            self.assertNotIn(">Pinterest Shadow<", primary)
            self.assertIn(">Coverage<", overflow)
            self.assertIn(">Pinterest Shadow<", overflow)

            self.assertEqual(200, client.get("/coverage").status_code)
            self.assertEqual(200, client.get("/shadow-campaigns").status_code)


if __name__ == "__main__":
    unittest.main()
