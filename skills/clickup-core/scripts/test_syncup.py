import runpy
import unittest
from pathlib import Path

M = runpy.run_path(str(Path(__file__).with_name("syncup.py")))
WS = "https://app.clickup.com/9001"
MEDIA = "https://t9001.p.clickup-attachments.com/t9001/aaaa-1/aaaa-1.mp4"


class SyncUpTests(unittest.TestCase):
    def test_parse_url_forms(self):
        parse = M["parse_url"]
        self.assertEqual(parse(f"{WS}/chat/r/ab12-3/t/800"),
                         {"kind": "message", "ws": "9001", "channel": "ab12-3", "message_id": "800"})
        self.assertEqual(parse(f"{WS}/chat/r/ab12-3")["kind"], "channel")
        for url in (f"{WS}/docs/ab12-592/ab12-92", f"{WS}/v/dc/ab12-592/ab12-92", f"{WS}/docs/ab12-592"):
            self.assertEqual(parse(url), {"kind": "doc", "ws": "9001", "doc_id": "ab12-592"})
        with self.assertRaises(ValueError):
            parse("https://example.com/x")

    def test_notes_doc_prefers_ai_bot_reply(self):
        replies = [
            {"user_id": "42", "content": f"see [old]({WS}/docs/ab12-1)"},
            {"user_id": "-4", "content": f"✨ Here are the AI Notes: x ([{WS}/docs/ab12-592/ab12-92]({WS}/docs/ab12-592/ab12-92))"},
        ]
        self.assertEqual(M["notes_doc"](replies), ("9001", "ab12-592"))
        self.assertIsNone(M["notes_doc"]([{"user_id": "42", "content": "thanks"}]))

    def test_split_pages_and_media_links(self):
        pages = [
            {"id": "p1", "name": "SyncUp Notes: 25/09/2026", "content": f"[{MEDIA}]({MEDIA})\n\n### Overview",
             "pages": [{"id": "p1a", "name": "Sub", "content": "audio https://t9001.p.clickup-attachments.com/t9001/b/b.M4A"}]},
            {"id": "p2", "name": "Meeting Transcript", "content": "**Alex**: hello"},
        ]
        notes, transcript = M["split_pages"](pages)
        self.assertEqual([p["id"] for p in notes], ["p1", "p1a"])
        self.assertEqual([p["id"] for p in transcript], ["p2"])
        links = M["media_links"]("\n".join(p["content"] for p in notes))
        self.assertEqual(links, [(MEDIA, "mp4"), ("https://t9001.p.clickup-attachments.com/t9001/b/b.M4A", "m4a")])


if __name__ == "__main__":
    unittest.main()
