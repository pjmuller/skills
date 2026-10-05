import runpy
import unittest
from pathlib import Path
from unittest import mock

MODULE = runpy.run_path(str(Path(__file__).with_name("clickup.py")))
G = MODULE["chat_ref"].__globals__


class ChatRefTests(unittest.TestCase):
    def test_channel_and_thread_urls(self):
        self.assertEqual(MODULE["chat_ref"]("https://app.clickup.com/901/chat/r/2kx-72"), ("2kx-72", None))
        self.assertEqual(MODULE["chat_ref"]("https://app.clickup.com/901/chat/r/2kx-72/t/80120072556655"),
                         ("2kx-72", "80120072556655"))
        self.assertEqual(MODULE["chat_ref"]("2kx-72/5"), ("2kx-72", "5"))

    def test_rejects_task_url(self):
        with self.assertRaises(SystemExit):
            MODULE["chat_ref"]("https://app.clickup.com/t/abc123")


class ThreadRootTests(unittest.TestCase):
    def test_reply_id_resolves_to_its_root(self):
        roots = [{"id": "1", "replies_count": 0}, {"id": "2", "replies_count": 2}]
        replies = {"2": [{"id": "21"}, {"id": "22"}]}
        with mock.patch.dict(G, {"chat_messages": lambda c, limit=100: roots,
                                 "chat_replies": lambda m: replies.get(str(m), [])}):
            self.assertEqual(MODULE["chat_root_of"]("c", "22"), "2")
            self.assertEqual(MODULE["chat_root_of"]("c", "1"), "1")
            with self.assertRaises(SystemExit):
                MODULE["chat_root_of"]("c", "99")


class ImagePartTests(unittest.TestCase):
    def test_part_mirrors_web_app_shape(self):
        att = {"id": "abc.png", "name": "x.png", "url": "https://h/x.png", "width": 1122, "height": 1402,
               "extension": "png", "thumbnail_small": "https://h/s.png"}
        part = MODULE["chat_image_part"](att)
        self.assertEqual(part["type"], "image")
        self.assertEqual(part["image"]["id"], "abc.png")
        self.assertEqual(part["image"]["extension"], "image/png")
        self.assertEqual(part["image"]["thumbnail_small"], "https://h/s.png")
        self.assertEqual(part["image"]["thumbnail_large"], "https://h/x.png")
        self.assertTrue(part["image"]["uploaded"])
        self.assertEqual(part["attributes"]["width"], "300")
        self.assertEqual(part["attributes"]["data-natural-height"], "1402")


class SessionTests(unittest.TestCase):
    def test_jwt_payload(self):
        # header.payload.sig with payload {"user":1,"exp":2}
        self.assertEqual(MODULE["_jwt_payload"]("x.eyJ1c2VyIjoxLCJleHAiOjJ9.y"), {"user": 1, "exp": 2})

    def test_missing_profile_explains_both_routes(self):
        with mock.patch.dict(G, {"env_value": lambda name: "", "_refresh_cache": lambda: Path("/nonexistent/refresh-token")}):
            with self.assertRaises(SystemExit) as ctx:
                MODULE["refresh_token"]()
        self.assertIn("CLICKUP_CHROME_PROFILE", str(ctx.exception))
        self.assertIn("CLICKUP_REFRESH_TOKEN", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
