import os
import re
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from marketing_os.db import session_scope
from marketing_os.secure_app import CSRF_COOKIE, create_secure_app, login_csrf_cookie_name
from marketing_os.services.auth import create_principal


ORIGIN = "https://mmm.digicolony.net"


class HostedStudioGatewayTest(TestCase):
    def test_existing_admin_login_protects_the_studio_and_preserves_csrf(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, {
            "MARKETING_OS_DB_URL": f"sqlite:///{Path(folder) / 'test.db'}",
            "MARKETING_OS_SECRET": "test-only-signing-secret-000000",
            "MARKETING_OS_ENV": "",
            "STUDIO_HOSTED_GATEWAY": "1",
        }), patch("marketing_os.studio_gateway.HTTPConnection") as http:
            app = create_secure_app(bootstrap_data=False)
            client = app.test_client()
            password = secrets.token_urlsafe(24)
            with session_scope(app.config["SESSION_FACTORY"]) as db:
                create_principal(db, username="test-admin", password=password, roles={"admin"})

            self.assertEqual(client.get("/studio/", base_url=ORIGIN).location, "/auth/login")
            self.assertEqual(client.get("/studio/api/studio/products", base_url=ORIGIN).status_code, 401)
            anonymous_state = client.get("/studio/api/studio/state", base_url=ORIGIN)
            self.assertEqual(anonymous_state.status_code, 401)
            self.assertNotIn("X-CSRF-Token", anonymous_state.headers)
            http.assert_not_called()

            first_form = client.get("/auth/login", base_url=ORIGIN)
            login_token = re.search(r'name="_login_csrf" value="([^"]+)"', first_form.text)[1]
            self.assertEqual(first_form.headers["Cache-Control"], "no-store")
            second_tab = app.test_client()
            second_form = second_tab.get("/auth/login", base_url=ORIGIN)
            second_token = re.search(r'name="_login_csrf" value="([^"]+)"', second_form.text)[1]
            self.assertNotEqual(login_token, second_token)
            cookie = second_tab.get_cookie(login_csrf_cookie_name(second_token), domain="mmm.digicolony.net", path="/auth/login")
            client.set_cookie(cookie.key, cookie.value, domain=cookie.domain, path=cookie.path)

            data = {
                "username": "test-admin", "password": password, "_login_csrf": login_token,
            }
            bad_form = second_tab.post("/auth/login", data=data, base_url=ORIGIN)
            self.assertEqual(bad_form.status_code, 403)
            self.assertIn("This sign-in form expired", bad_form.text)
            self.assertIn('name="_login_csrf"', bad_form.text)
            self.assertEqual(bad_form.headers["Cache-Control"], "no-store")
            result = client.post("/auth/login", data=data, base_url=ORIGIN)
            self.assertEqual(result.status_code, 302)
            self.assertEqual(client.get("/", base_url=ORIGIN).location, "/studio/")

            upstream = http.return_value.getresponse.return_value
            upstream.read.return_value = b'{"products":[]}'
            upstream.status = 200
            upstream.getheaders.return_value = [("Content-Type", "application/json")]
            products = client.get("/studio/api/studio/products", base_url=ORIGIN)
            self.assertEqual(products.json, {"products": []})
            self.assertEqual(products.headers["Cache-Control"], "no-store")
            self.assertNotIn("X-CSRF-Token", products.headers)
            self.assertEqual(http.return_value.request.call_args.args[:2], ("GET", "/studio/api/studio/products"))
            legacy = client.get("/legacy", base_url=ORIGIN)
            self.assertEqual(legacy.status_code, 200)
            self.assertIn('href="/legacy">Today', legacy.text)
            self.assertIn('href="/studio/">Back to Social Studio', legacy.text)

            path = "/studio/api/studio/assignment"
            self.assertEqual(client.post(path, json={"title": "Fixture"}, base_url=ORIGIN).status_code, 403)
            state = client.get("/studio/api/studio/state", base_url=ORIGIN)
            self.assertEqual(state.headers["Cache-Control"], "no-store")
            self.assertIn("Cookie", state.vary)
            csrf = state.headers["X-CSRF-Token"]
            cookie = client.get_cookie(CSRF_COOKIE, domain="mmm.digicolony.net")
            self.assertTrue(cookie.http_only)
            self.assertEqual(csrf, cookie.value)
            headers = {"X-CSRF-Token": csrf, "Origin": "https://example.invalid"}
            self.assertEqual(client.post(path, json={"title": "Fixture"}, headers=headers, base_url=ORIGIN).status_code, 403)
            headers["Origin"] = ORIGIN
            self.assertEqual(client.post(path, json={"title": "Fixture"}, headers=headers, base_url=ORIGIN).status_code, 200)
            self.assertEqual(http.return_value.request.call_args.kwargs["headers"]["Origin"], "http://127.0.0.1:3037")
