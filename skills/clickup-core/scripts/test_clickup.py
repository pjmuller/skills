import json
import runpy
import unittest
from pathlib import Path

MODULE = runpy.run_path(str(Path(__file__).with_name("clickup.py")))
MODULE["md_to_delta"].__globals__["USERS"].update({"author":101,"reviewer":102})
MODULE["md_to_delta"].__globals__["USER_NAMES"].update({"author":"Alex Example","reviewer":"Sam Example"})
FIXTURE = json.loads((Path(__file__).parent / "fixtures/task_content_rich.json").read_text())
comment_parts = MODULE["comment_parts"]
embed_ops = MODULE["embed_ops"]
append_ops_to_content = MODULE["append_ops_to_content"]
append_markdown_to_content = MODULE["append_markdown_to_content"]


class RichDescriptionTests(unittest.TestCase):
    def test_task_and_user_mentions_compile_to_embeds(self):
        delta = json.loads(
            MODULE["md_to_delta"](
                "See [[abc123]], https://app.clickup.com/t/abc123 and @author"
            )
        )
        inserts = [op["insert"] for op in delta["ops"]]
        self.assertEqual(inserts[1], {"task_mention": {"task_id": "abc123"}})
        self.assertEqual(inserts[3], {"task_mention": {"task_id": "abc123"}})
        self.assertEqual(
            inserts[5],
            {"user_mention": {"id": 101, "name": "Alex Example"}},
        )

    def test_full_block_subset_compiles_to_nested_delta_attributes(self):
        md = (
            "- top\n  - genest\n- [x] klaar\n- [ ] open\n"
            "> citaat\n"
            "```python\nx = 1\n```\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n"
            "---\n"
            "![i](https://x.test/a.jpg)\n"
            "*cursief* en ~~door~~ en snake_case_blijft"
        )
        ops = json.loads(MODULE["md_to_delta"](md))["ops"]
        attrs = [op.get("attributes") for op in ops if op.get("insert") == "\n"]
        self.assertIn({"list": {"list": "bullet"}}, attrs)
        self.assertIn({"list": {"list": "bullet"}, "indent": 1}, attrs)
        self.assertIn({"list": {"list": "checked"}}, attrs)
        self.assertIn({"list": {"list": "unchecked"}}, attrs)
        self.assertIn({"blockquote": {}}, attrs)
        self.assertIn({"code-block": {"code-block": "python"}}, attrs)
        embeds = [op["insert"] for op in ops if isinstance(op["insert"], dict)]
        self.assertIn({"divider": True}, embeds)
        self.assertIn({"image": "https://x.test/a.jpg"}, embeds)
        self.assertEqual(
            [e["table-embed"]["cells"]["2:1"]["content"][0] for e in embeds if "table-embed" in e],
            [{"insert": "1"}],
        )
        self.assertIn({"insert": "cursief", "attributes": {"italic": True}}, ops)
        self.assertIn({"insert": "door", "attributes": {"strike": True}}, ops)
        self.assertIn({"insert": " en snake_case_blijft"}, ops)

    def test_append_preserves_every_existing_op(self):
        before = json.loads(FIXTURE["content"])
        result = json.loads(
            MODULE["append_markdown_to_content"](
                FIXTURE["content"], "Added [[abc123]] for @author"
            )
        )
        self.assertEqual(result["ops"][: len(before["ops"])], before["ops"])
        appended = result["ops"][len(before["ops"]) :]
        self.assertEqual(appended[0], {"insert": "\n"})
        self.assertIn({"insert": {"task_mention": {"task_id": "abc123"}}}, appended)
        self.assertIn(
            {"insert": {"user_mention": {"id": 101, "name": "Alex Example"}}},
            appended,
        )

    def test_invalid_existing_content_refuses_to_append(self):
        with self.assertRaisesRegex(TypeError, "Quill"):
            MODULE["append_markdown_to_content"]("{}", "extra")

    def test_signature_tolerates_clickup_plain_text_normalization(self):
        split = json.dumps(
            {
                "ops": [
                    {"insert": "one"},
                    {"insert": "two"},
                    {"insert": "\n", "attributes": {"header": 2}},
                ]
            }
        )
        merged = json.dumps(
            {
                "ops": [
                    {"insert": "onetwo"},
                    {"insert": "\n", "attributes": {"header": 2}},
                ]
            }
        )
        self.assertEqual(
            MODULE["content_signature"](split), MODULE["content_signature"](merged)
        )

    def test_signature_ignores_clickup_autolinks(self):
        url = "https://example.com/a_b"
        sent = json.dumps({"ops": [{"insert": f"Bron: {url}\n"}]})
        stored = json.dumps({"ops": [{"insert": "Bron: "}, {"insert": url, "attributes": {"link": url}}, {"insert": "\n"}]})
        relinked = json.dumps({"ops": [{"insert": "Bron: "}, {"insert": url, "attributes": {"link": "https://evil.example"}}, {"insert": "\n"}]})
        sig = MODULE["content_signature"]
        self.assertEqual(sig(sent), sig(stored))
        self.assertNotEqual(sig(sent), sig(relinked))

    def test_signature_tolerates_merged_code_block_newlines(self):
        code = {"code-block": {"code-block": "md"}}
        sent = json.dumps({"ops": [{"insert": "a"}, {"insert": "\n", "attributes": code},
                                   {"insert": "\n", "attributes": code}]})
        stored = json.dumps({"ops": [{"insert": "a"}, {"insert": "\n\n", "attributes": code}]})
        sig = MODULE["content_signature"]
        self.assertEqual(sig(sent), sig(stored))
        self.assertNotEqual(sig(sent), sig(json.dumps({"ops": [{"insert": "a\n\n"}]})))

    def test_signature_preserves_text_position_around_embeds(self):
        embed = {"insert": {"task_mention": {"task_id": "abc123"}}}
        expected = json.dumps(
            {"ops": [{"insert": "before "}, embed, {"insert": " after"}]}
        )
        moved = json.dumps({"ops": [{"insert": "before  after"}, embed]})
        self.assertNotEqual(
            MODULE["content_signature"](expected), MODULE["content_signature"](moved)
        )


class RichCommentTests(unittest.TestCase):
    def test_user_and_task_shorthands_become_structured_parts(self):
        parts_fn = MODULE["comment_parts"]
        original = parts_fn.__globals__["task_mention_part"]
        parts_fn.__globals__["task_mention_part"] = lambda task_id: {
            "type": "task_mention",
            "text": "Target task",
            "task_mention": {"task_id": task_id, "team_id": "123456"},
        }
        try:
            parts = parts_fn(
                "@author see [[abc123]] and [target](https://app.clickup.com/t/abc123)"
            )
        finally:
            parts_fn.__globals__["task_mention_part"] = original
        self.assertEqual(parts[0], {"type": "tag", "user": {"id": 101}})
        task_parts = [part for part in parts if part.get("type") == "task_mention"]
        self.assertEqual(
            [p["task_mention"]["task_id"] for p in task_parts],
            ["abc123", "abc123"],
        )

    def test_explicit_markdown_user_mention_becomes_tag(self):
        parts = MODULE["comment_parts"]("[@Sam Example](#user_mention#102)")
        self.assertEqual(parts, [{"type": "tag", "user": {"id": 102}}])




class CommentPartsTests(unittest.TestCase):
    def test_inline_bold_code_link_and_user_tag(self):
        parts = comment_parts("**Klaar**: `x` zie [site](https://example.org) @reviewer")
        self.assertEqual(parts[0], {"text": "Klaar", "attributes": {"bold": True}})
        self.assertIn({"text": "x", "attributes": {"code": True}}, parts)
        self.assertIn({"text": "site", "attributes": {"link": "https://example.org"}}, parts)
        self.assertEqual(parts[-1], {"type": "tag", "user": {"id": 102}})

    def test_bullets_headers_and_indent(self):
        parts = comment_parts("## Kop\n- een\n  - sub\n1. eerst\nplain")
        self.assertEqual(parts[1], {"text": "\n", "attributes": {"header": 2}})
        self.assertEqual(parts[3], {"text": "\n", "attributes": {"list": "bullet"}})
        self.assertEqual(parts[5], {"text": "\n", "attributes": {"list": "bullet", "indent": 1}})
        self.assertEqual(parts[7], {"text": "\n", "attributes": {"list": "ordered"}})
        self.assertEqual(parts[-1], {"text": "plain"})  # no trailing newline on the last plain line

    def test_fenced_code_block_and_native_table(self):
        parts = comment_parts("```\na = 1\n```\n| kol | n |\n|---|---:|\n| lang woord | 2 |\nna")
        self.assertEqual(parts[0], {"text": "a = 1"})
        self.assertEqual(parts[1], {"text": "\n", "attributes": {"code-block": "plain"}})
        table = parts[2]["table-embed"]
        self.assertEqual(parts[2]["type"], "table-embed")
        self.assertEqual((len(table["rows"]), len(table["columns"])), (2, 2))
        self.assertEqual(table["cells"]["2:1"]["content"][0], {"insert": "lang woord"})
        self.assertEqual(parts[3], {"text": "na"})

    def test_table_cells_keep_inline_markdown_and_show_images(self):
        # Cells used to be plain text: a link or an attachment showed as its raw markdown (2026-10-23).
        table = comment_parts("| a | b |\n|---|---|\n| [x](https://e.x) **b** | ![](https://e.x/1.png) ![](https://e.x/2.png) |")[0]["table-embed"]
        self.assertEqual(table["cells"]["2:1"]["content"][:3],
                         [{"insert": "x", "attributes": {"link": "https://e.x"}}, {"insert": " "},
                          {"insert": "b", "attributes": {"bold": True}}])
        self.assertEqual(table["cells"]["2:2"]["content"],
                         [{"insert": {"image": "https://e.x/1.png"}}, {"insert": {"image": "https://e.x/2.png"}}, {"insert": "\n"}])

    def test_table_widths_fit_short_columns_and_share_budget(self):
        widths = MODULE["_column_widths"]
        self.assertEqual(widths([["ID", "x" * 200]], 2, 840), [60, 420])  # long column capped
        short, long_a, long_b = widths([["Step", "y" * 120, "z" * 120]], 3, 840)
        self.assertEqual(short, 68)  # short column keeps its natural width
        self.assertLessEqual(short + long_a + long_b, 840)

    def test_checklists_quotes_and_fenced_lang_stay_flat(self):
        parts = comment_parts("- [x] klaar\n- [ ] open\n> citaat\n```python\nx = 1\n```")
        attrs = [p["attributes"] for p in parts if p.get("attributes")]
        self.assertIn({"list": "checked"}, attrs)
        self.assertIn({"list": "unchecked"}, attrs)
        self.assertIn({"blockquote": True}, attrs)
        self.assertIn({"code-block": "python"}, attrs)

    def test_italic_strike_and_image_degradation(self):
        parts = comment_parts("*cursief* ~~door~~ snake_case\n![i](https://x.test/a.jpg)")
        self.assertEqual(parts[0], {"text": "cursief", "attributes": {"italic": True}})
        self.assertEqual(parts[2], {"text": "door", "attributes": {"strike": True}})
        self.assertEqual(parts[3], {"text": " snake_case"})
        self.assertEqual(parts[-1], {"text": "https://x.test/a.jpg",
                                     "attributes": {"link": "https://x.test/a.jpg"}})




VIDEO_UPLOAD = {
    "id": "d3bf807f-1111-2222-3333-444455556666.mp4",
    "title": "demo.mp4",
    "mimetype": "video/mp4",
    "extension": "mp4",
    "date": "1757318400000",
    "url": "https://t123456.p.clickup-attachments.com/t123456/x/demo.mp4",
    "url_w_host": "https://t123456.p.clickup-attachments.com/t123456/x/demo.mp4",
    "url_w_query": "https://t123456.p.clickup-attachments.com/t123456/x/demo.mp4?view=open",
}
PDF_UPLOAD = {**VIDEO_UPLOAD, "id": "aaaa-bbbb.pdf", "title": "report.pdf",
              "mimetype": "application/pdf", "extension": "pdf"}


class EmbedOpsTest(unittest.TestCase):
    def test_video_becomes_an_inline_player_frame(self):
        kind, ops = embed_ops(VIDEO_UPLOAD)

        self.assertEqual(kind, "video")
        self.assertEqual(ops, [
            {"insert": {"frame": {"id": VIDEO_UPLOAD["id"], "service": "clickup_video",
                                  "url": VIDEO_UPLOAD["url_w_query"],
                                  "src": VIDEO_UPLOAD["url_w_query"], "source": 1}},
             "attributes": {"width": "420", "data-size": "large", "data-origin": "attachment"}},
            {"insert": "\n"},
        ])

    def test_other_file_becomes_an_attachment_chip_with_epoch_ms_int(self):
        kind, ops = embed_ops(PDF_UPLOAD)

        self.assertEqual(kind, "file")
        self.assertEqual(ops[0]["insert"]["attachment"], {
            "name": "report.pdf", "source": 1, "date": 1757318400000,
            "url": PDF_UPLOAD["url"], "url_w_host": PDF_UPLOAD["url_w_host"],
            "url_w_query": PDF_UPLOAD["url_w_query"], "id": PDF_UPLOAD["id"],
            "type": "application/pdf", "extension": "pdf"})
        self.assertEqual(ops[1], {"insert": "\n"})

    def test_missing_url_w_query_falls_back_to_view_open(self):
        _, ops = embed_ops({k: v for k, v in VIDEO_UPLOAD.items() if k != "url_w_query"})

        self.assertEqual(ops[0]["insert"]["frame"]["url"], VIDEO_UPLOAD["url"] + "?view=open")


class AppendOpsTest(unittest.TestCase):
    def test_unknown_embeds_are_preserved_byte_for_byte_and_separated(self):
        existing = json.dumps({"ops": [
            {"insert": {"some_future_embed": {"id": "x"}}},
            {"insert": "body"},
        ]})

        _, ops = embed_ops(VIDEO_UPLOAD)
        result = json.loads(append_ops_to_content(existing, ops))

        self.assertEqual(result["ops"][:2], json.loads(existing)["ops"])
        self.assertEqual(result["ops"][2], {"insert": "\n\n"})
        self.assertEqual(result["ops"][3:], ops)

    def test_markdown_append_still_routes_through_the_same_seam(self):
        result = json.loads(append_markdown_to_content(
            json.dumps({"ops": [{"insert": "body\n"}]}), "extra"))

        self.assertEqual(result["ops"][0], {"insert": "body\n"})
        self.assertIn("extra", json.dumps(result["ops"][1:]))


class CommentMentionGuardTests(unittest.TestCase):
    def test_mention_first_without_mention_is_an_error(self):
        # --mention-first is a prefix, not the recipient: posting a "ping" with no tag must fail loudly.
        from types import SimpleNamespace
        a = SimpleNamespace(id="t1", text="hi", mention=None, mention_first="", json=False)
        with self.assertRaisesRegex(SystemExit, "--mention-first needs --mention"):
            MODULE["cmd_comment"](a)


URL = "https://app.clickup.com/t/2602930/869ej1uy0?comment=901&threadedComment=902"


class CommentThreadTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        g = MODULE["post_comment"].__globals__
        self.addCleanup(g.__setitem__, "api", g["api"])
        g["api"] = self.fake_api

    def fake_api(self, method, path, **kw):
        self.calls.append((method, path))
        if method == "POST":
            return {"id": "r9"}
        if path == "/comment/901/reply":
            return {"comments": [{"id": "r9", "comment": [{"text": "hi "}, {"type": "tag", "user": {"id": 101}}]}]}
        return {"comments": [{"id": "900", "comment": []}, {"id": "901", "comment": [{"text": "root"}]}]}

    def test_comment_id_of_prefers_thread_root(self):
        cid = MODULE["comment_id_of"]
        self.assertEqual(cid(URL), "901")
        self.assertEqual(cid("https://app.clickup.com/t/869ej1uy0?threadedComment=902"), "902")
        self.assertEqual(cid("901"), "901")
        with self.assertRaises(SystemExit):
            cid("https://app.clickup.com/t/869ej1uy0")

    def test_reply_posts_to_root_and_reads_back_thread(self):
        MODULE["post_comment"]("869ej1uy0", "hi", 101, False, quiet=True, reply_to="901")
        self.assertEqual(self.calls, [("POST", "/comment/901/reply"), ("GET", "/comment/901/reply")])

    def posted_parts(self, **kw):
        sent = []
        orig = self.fake_api
        def api(method, path, **k):
            if method == "POST":
                sent.append(json.loads(k["data"]))
            return orig(method, path, **k)
        MODULE["post_comment"].__globals__["api"] = api
        MODULE["post_comment"]("869ej1uy0", kw.pop("text", "hi"), kw.pop("mention", 101), False, quiet=True,
                               reply_to="901", **kw)
        return sent[0]

    def test_ai_comment_leads_with_sparkle_once_and_keeps_mention_and_notify(self):
        body = self.posted_parts(text="**Ready** to test: [demo](https://example.com)")
        self.assertEqual(body["comment"][0], {"text": "✨ "})
        self.assertFalse(body["notify_all"])
        self.assertIn({"text": "Ready", "attributes": {"bold": True}}, body["comment"])
        self.assertIn({"type": "tag", "user": {"id": 101}}, body["comment"])
        marked = MODULE["ai_marked"]
        self.assertEqual(marked(body["comment"]), body["comment"])  # idempotent
        self.assertEqual(self.posted_parts(text="✨ already marked")["comment"][0], {"text": "✨ already marked "})

    def test_mention_first_and_block_starts(self):
        lead = self.posted_parts(text="please check", prefix="")["comment"]
        self.assertEqual(lead[:2], [{"text": "✨ "}, {"type": "tag", "user": {"id": 101}}])
        code = self.posted_parts(text="```\nmake test\n```", mention=None)["comment"]
        self.assertEqual(code[0], {"text": "✨\n"})
        table = self.posted_parts(text="| a | b |\n|---|---|\n| 1 | 2 |", mention=None)["comment"]
        self.assertEqual((table[0], table[1]["type"]), ({"text": "✨\n"}, "table-embed"))
        heading = self.posted_parts(text="# Review\nok", mention=None)["comment"]
        self.assertEqual(heading[:2], [{"text": "✨ "}, {"text": "Review"}])

    def test_human_comment_is_unmarked(self):
        body = self.posted_parts(text="my own words", ai=False)
        self.assertNotIn("✨", json.dumps(body, ensure_ascii=False))

    def test_comments_thread_prints_root_then_replies(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        buf = StringIO()
        with redirect_stdout(buf):
            MODULE["cmd_comments"](SimpleNamespace(id="869ej1uy0", thread=URL, json=True))
        self.assertEqual([c["id"] for c in json.loads(buf.getvalue())], ["901", "r9"])


class TaskDiscussionTests(unittest.TestCase):
    """`task` reads the discussion by default: comments often carry the decisions the body lacks."""

    def setUp(self):
        self.calls = []
        g = MODULE["cmd_task"].__globals__
        for name in ("api", "get_task", "get_task_content"):
            self.addCleanup(g.__setitem__, name, g[name])
        g["api"] = self.fake_api
        g["get_task"] = lambda tid, markdown=False: {"id": tid, "name": "T"}
        g["get_task_content"] = lambda tid: {"ops": []}

    @staticmethod
    def comment(cid, date, text="x", replies=0, user="Alex Example"):
        return {"id": str(cid), "date": str(date), "reply_count": replies, "user": {"username": user},
                "comment": [{"text": text}], "comment_text": text}

    def fake_api(self, method, path, params=None, **kw):
        self.calls.append((path, dict(params or {})))
        if path == "/comment/c1/reply":
            return {"comments": [self.comment("r2", 1_700_000_300_000, "second", user="Sam Example"),
                                 self.comment("r1", 1_700_000_200_000, "first")]}
        if not params:  # page 1: 25 newest, the oldest of them repeats on page 2
            return {"comments": [self.comment(f"n{i}", 1_700_001_000_000 - i) for i in range(24)]
                    + [self.comment("c1", 1_700_000_100_000, "root", replies=2)]}
        return {"comments": [self.comment("c1", 1_700_000_100_000, "root", replies=2),
                             self.comment("c0", 1_700_000_000_000, "see [demo]")]}

    def run_task(self, **flags):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        args = dict(id="t1", json=True, comments=False, no_comments=False,
                    download_attachments=False, download_looms=False, dir=None) | flags
        buf = StringIO()
        with redirect_stdout(buf):
            MODULE["cmd_task"](SimpleNamespace(**args))
        return json.loads(buf.getvalue())

    def test_default_includes_full_discussion_oldest_first_with_replies(self):
        out = self.run_task()
        thread = out["discussion"]
        self.assertNotIn("comments", out)
        self.assertEqual(len(thread), 26)  # both pages, the repeated cursor comment once
        self.assertEqual([c["id"] for c in thread[:2]], ["c0", "c1"])
        self.assertEqual(thread[0], {"id": "c0", "date": "2023-11-14T22:13:20.000Z",
                                     "author": "Alex Example", "text": "see [demo]"})
        self.assertEqual([(r["id"], r["author"]) for r in thread[1]["replies"]],
                         [("r1", "Alex Example"), ("r2", "Sam Example")])
        self.assertNotIn("replies_missing", thread[1])
        self.assertEqual(self.calls[1][1], {"start": "1700000100000", "start_id": "c1"})

    def test_no_comments_is_metadata_only_and_never_calls_the_comment_api(self):
        self.assertEqual(self.run_task(no_comments=True), {"task": {"id": "t1", "name": "T", "content": {"ops": []}}})
        self.assertEqual(self.calls, [])

    def test_comments_flag_keeps_raw_objects_next_to_discussion(self):
        out = self.run_task(comments=True)
        self.assertEqual(out["comments"][0]["comment_text"], "x")
        self.assertEqual(len(out["comments"]), 26)
        self.assertIn("discussion", out)

    def test_short_reply_page_is_flagged_not_silently_dropped(self):
        orig = self.fake_api
        def api(method, path, params=None, **kw):
            res = orig(method, path, params, **kw)
            return {"comments": res["comments"][:1]} if path == "/comment/c1/reply" else res
        MODULE["cmd_task"].__globals__["api"] = api
        from contextlib import redirect_stderr
        from io import StringIO
        with redirect_stderr(StringIO()) as err:
            root = self.run_task()["discussion"][1]
        self.assertEqual(root["replies_missing"], 1)
        self.assertIn("reports 2 replies", err.getvalue())

    def test_render_keeps_link_targets_and_mentions_in_part_order(self):
        c = {"comment": [{"type": "tag", "user": {"username": "Sam Example"}}, {"text": " see "},
                         {"text": "the Loom", "attributes": {"link": "https://www.loom.com/share/abc"}},
                         {"text": " and "}, {"text": "https://x.test", "attributes": {"link": "https://x.test"}}]}
        self.assertEqual(MODULE["render"](c), "@Sam Example see [the Loom](https://www.loom.com/share/abc) and https://x.test")

    def test_render_keeps_table_cells_and_marks_unknown_parts(self):
        parts = comment_parts("| Item | State |\n|---|---|\n| Ship | blocked |\n\nafter")
        self.assertEqual(MODULE["render"]({"comment": parts}),
                         "| Item | State |\n|---|---|\n| Ship | blocked |\n\nafter")
        self.assertEqual(MODULE["render"]({"comment": [{"type": "frame"}]}), "[frame]")
        cells = {"1:1": {"content": [{"insert": {"user_mention": {"id": 102, "name": "Sam Example"}}}]},
                 "1:2": {"content": [{"insert": {"task_mention": {"task_id": "abc123"}}}]},
                 "1:3": {"content": [{"insert": "Loom", "attributes": {"link": "https://www.loom.com/share/abc"}}]},
                 "1:4": {"content": [{"insert": {"image": "https://x.test/a.png"}}, {"insert": "\n"}]}}
        rich = [{"type": "table-embed", "table-embed": {"cells": cells}}]  # cell ops as comment_parts writes them
        self.assertEqual(MODULE["render"]({"comment": rich}).splitlines()[0],
                         "| @Sam Example | [[abc123]] | [Loom](https://www.loom.com/share/abc) | ![](https://x.test/a.png) |")

    def test_no_comments_with_looms_scans_body_only(self):
        g = MODULE["cmd_task"].__globals__
        self.addCleanup(g.__setitem__, "download_looms", g["download_looms"])
        g["download_looms"] = lambda t, thread, d: [len(thread)]
        self.assertEqual(self.run_task(no_comments=True, download_looms=True)["looms"], [0])
        self.assertEqual(self.calls, [])

    def test_cli_rejects_comments_with_no_comments(self):
        from contextlib import redirect_stderr
        from io import StringIO
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            MODULE["main"](["task", "t1", "--comments", "--no-comments"])


class PickAttachmentTests(unittest.TestCase):
    ROWS = [{"id": "aaa-1.md", "title": "brief.md"}, {"id": "bbb-2.md", "title": "brief.md"},
            {"id": "ccc-3.jpg", "title": "shot.jpg"}]

    def test_matches_full_id_bare_uuid_and_unique_title(self):
        pick = MODULE["pick_attachment"]
        self.assertEqual(pick(self.ROWS, "aaa-1.md")["id"], "aaa-1.md")
        self.assertEqual(pick(self.ROWS, "bbb-2")["id"], "bbb-2.md")
        self.assertEqual(pick(self.ROWS, "shot.jpg")["id"], "ccc-3.jpg")

    def test_duplicate_title_or_unknown_ref_refuses(self):
        pick = MODULE["pick_attachment"]
        with self.assertRaises(SystemExit):
            pick(self.ROWS, "brief.md")
        with self.assertRaises(SystemExit):
            pick(self.ROWS, "nope")


ATT_URL = "https://t1.p.clickup-attachments.com/t1/a/"
FILE_TASK = {"id": "t1", "attachments": [
    {"id": "a1.md", "title": "de-kies-retro.md", "url": ATT_URL + "old.md", "date": "1000"},
    {"id": "a2.md", "title": "de-kies-retro.md", "url": ATT_URL + "new.md", "date": "2000"},
    {"id": "a3.pdf", "title": "Report.PDF", "url": ATT_URL + "report.pdf", "date": "1500"},
    {"id": "a4", "title": "notes", "url": ATT_URL + "notes", "date": "1"},
]}


class FileReferenceTests(unittest.TestCase):
    link = staticmethod(MODULE["link_attachments"])

    def test_exact_and_case_insensitive_match(self):
        self.assertEqual(self.link("zie [[file:Report.PDF]]", FILE_TASK), f"zie [Report.PDF]({ATT_URL}report.pdf)")
        self.assertEqual(self.link("zie [[file:report.pdf]]", FILE_TASK), f"zie [Report.PDF]({ATT_URL}report.pdf)")

    def test_newest_version_wins(self):
        self.assertEqual(self.link("[[file:de-kies-retro.md]]", FILE_TASK), f"[de-kies-retro.md]({ATT_URL}new.md)")
        # bold stays bold text: auto-linking inside it nested a link in bold and ClickUp split the URL
        self.assertEqual(self.link("open **de-kies-retro.md** now", FILE_TASK), "open **de-kies-retro.md** now")

    def test_unknown_name_fails_listing_titles(self):
        with self.assertRaisesRegex(SystemExit, "no attachment.*de-kies-retro.md, notes"):
            self.link("[[file:nope.md]]", FILE_TASK)
        with self.assertRaisesRegex(SystemExit, "does not exist yet"):
            self.link("[[file:nope.md]]", None)

    def test_bare_filename_is_auto_linked(self):
        self.assertEqual(self.link("zie de bijlage de-kies-retro.md.", FILE_TASK),
                         f"zie de bijlage [de-kies-retro.md]({ATT_URL}new.md).")
        # renders as a real link part, not ClickUp's domain autolink
        parts = comment_parts(self.link("zie de-kies-retro.md", FILE_TASK))
        self.assertIn({"text": "de-kies-retro.md", "attributes": {"link": ATT_URL + "new.md"}}, parts)

    def test_bare_filename_in_code_link_url_or_extensionless_title_untouched(self):
        for text in ("`de-kies-retro.md`", "[retro](https://x.test/de-kies-retro.md)",
                     "[de-kies-retro.md](https://x.test/a)", "https://x.test/de-kies-retro.md",
                     "```\nde-kies-retro.md\n[[file:nope]]\n```", "my-de-kies-retro.md", "take notes",
                     "`[[file:nope]]`", "[[abc123]]"):
            self.assertEqual(self.link(text, FILE_TASK), text)


class FileReferenceCommandTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        g = MODULE["cmd_update"].__globals__
        for name in ("api", "api_v1"):
            self.addCleanup(g.__setitem__, name, g[name])
        g["api"] = self.fake_api
        g["api_v1"] = lambda method, path, **kw: self.calls.append((method, path)) or {"content": ""}

    def fake_api(self, method, path, **kw):
        self.calls.append((method, path))
        return {**FILE_TASK, "status": {"status": "open"}, "list": {"id": "1"}, "description": ""}

    def test_unknown_name_fails_before_any_write(self):
        from types import SimpleNamespace
        a = SimpleNamespace(id="t1", text="zie [[file:nope.md]]", mention=None, mention_first=None, json=False)
        with self.assertRaises(SystemExit):
            MODULE["cmd_comment"](a)
        a = SimpleNamespace(id="t1", name=None, status=None, priority=None, customer=None, description=None,
                            description_file=None, append_description="[[file:nope.md]]",
                            append_description_file=None, add_assignee=None, rem_assignee=None, json=False)
        with self.assertRaises(SystemExit):
            MODULE["cmd_update"](a)
        self.assertEqual([c for c in self.calls if c[0] != "GET"], [])

    def test_attach_prints_reference_last(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        g = MODULE["cmd_attach"].__globals__
        self.addCleanup(g.__setitem__, "upload_attachment", g["upload_attachment"])
        g["upload_attachment"] = lambda tid, f, name=None: dict(PDF_UPLOAD)
        for as_json in (False, True):
            buf = StringIO()
            with redirect_stdout(buf):
                MODULE["cmd_attach"](SimpleNamespace(id="t1", file="/tmp/x.pdf", name=None, embed=False, json=as_json))
            if as_json:
                self.assertEqual(json.loads(buf.getvalue())["reference"], "[[file:report.pdf]]")
            else:
                self.assertEqual(buf.getvalue().strip().splitlines()[-1], "reference: [[file:report.pdf]]")


    def test_attach_several_uploads_last_first_so_clickup_shows_given_order(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        g = MODULE["cmd_attach"].__globals__
        self.addCleanup(g.__setitem__, "upload_attachment", g["upload_attachment"])
        uploaded = []
        g["upload_attachment"] = lambda tid, f, name=None: uploaded.append(f) or {"title": f.rsplit("/", 1)[-1], "url": "u"}
        buf = StringIO()
        with redirect_stdout(buf):
            MODULE["cmd_attach"](SimpleNamespace(id="t1", file=["/tmp/1.png", "/tmp/2.png", "/tmp/3.png"],
                                                 name=None, embed=False, json=True))
        self.assertEqual(uploaded, ["/tmp/3.png", "/tmp/2.png", "/tmp/1.png"])
        self.assertEqual([r["reference"] for r in json.loads(buf.getvalue())],
                         ["![[file:1.png]]", "![[file:2.png]]", "![[file:3.png]]"])  # images: inline form
        with self.assertRaises(SystemExit):
            MODULE["cmd_attach"](SimpleNamespace(id="t1", file=["/tmp/1.png", "/tmp/2.png"], name="x", embed=False, json=True))


class MediaTests(unittest.TestCase):
    """Local images and ```mermaid blocks become attachments shown inline (2026-10-27)."""

    def setUp(self):
        import tempfile
        self.dir = Path(tempfile.mkdtemp())
        self.png = self.dir / "shot.png"
        self.png.write_bytes(b"png")
        g = MODULE["collect_media"].__globals__
        self.addCleanup(g.__setitem__, "render_mermaid", g["render_mermaid"])
        self.rendered = []
        g["render_mermaid"] = lambda src: self.rendered.append(src) or self.png.with_name("diagram-abc.png")

    def test_local_image_and_mermaid_become_inline_file_refs(self):
        md = f"Voor:\n![voor]({self.png})\n```mermaid\nflowchart TD\n  A-->B\n```\nklaar"
        text, uploads = MODULE["collect_media"](md)
        self.assertEqual(text, "Voor:\n![[file:shot.png]]\n![[file:diagram-abc.png]]\nklaar")
        self.assertEqual([n for _, n in uploads], ["shot.png", "diagram-abc.png"])
        self.assertEqual(self.rendered, ["flowchart TD\n  A-->B\n"])

    def test_urls_code_and_same_basename(self):
        other = self.dir / "sub"
        other.mkdir()
        (other / "shot.png").write_bytes(b"x")
        md = (f"![a]({self.png})\n![b]({other / 'shot.png'})\n![c]({self.png})\n"
              "![web](https://x.test/a.png) `![code](nope.png)`\n```\n![fenced](nope.png)\n```")
        text, uploads = MODULE["collect_media"](md)
        self.assertEqual(text.splitlines()[:3], ["![[file:shot.png]]", "![[file:shot-2.png]]", "![[file:shot.png]]"])
        self.assertIn("![web](https://x.test/a.png) `![code](nope.png)`", text)
        self.assertIn("![fenced](nope.png)", text)
        self.assertEqual([n for _, n in uploads], ["shot.png", "shot-2.png"])

    def test_missing_local_image_fails_closed(self):
        with self.assertRaises(SystemExit):
            MODULE["collect_media"]("![x](/nope/missing.png)")
        with self.assertRaises(SystemExit):
            MODULE["collect_media"]("```mermaid\nflowchart TD")
        for inline in (f"voor ![s]({self.png}) na", f"- ![s]({self.png})"):
            with self.assertRaises(SystemExit):
                MODULE["collect_media"](inline)

    def test_create_rejects_unknown_file_ref_before_post(self):
        from types import SimpleNamespace
        g = MODULE["cmd_create"].__globals__
        calls = []
        for name in ("api", "upload_attachment", "LISTS", "CONFIG"):
            self.addCleanup(g.__setitem__, name, g[name])
        g["api"] = lambda method, path, **kw: calls.append(method) or {"id": "t9", "attachments": []}
        g["upload_attachment"] = lambda *x, **k: calls.append("UPLOAD")
        g["LISTS"], g["CONFIG"] = {"dev": "1"}, {}
        a = SimpleNamespace(list="dev", status=None, assignee=None, priority=None, customer=None, tag=None, parent=None,
                            name="n", description=f"![s]({self.png})\nzie [[file:nope.pdf]]", description_file=None, json=False)
        with self.assertRaises(SystemExit):
            MODULE["cmd_create"](a)
        self.assertEqual(calls, [])

    def test_create_with_image_creates_uploads_then_writes_body(self):
        from types import SimpleNamespace
        g = MODULE["cmd_create"].__globals__
        calls = []
        for name in ("api", "upload_attachment", "verify_task_content", "read_back", "LISTS", "CONFIG"):
            self.addCleanup(g.__setitem__, name, g[name])
        task = {"id": "t9", "url": "u", "attachments": []}

        def fake_api(method, path, **kw):
            calls.append((method, path))
            return task
        g["api"] = fake_api
        g["upload_attachment"] = lambda tid, f, name=None: calls.append(("UPLOAD", name)) or task["attachments"].append(
            {"title": name, "url": "https://att.test/shot.png", "date": "1"})
        g["verify_task_content"] = lambda tid, content: calls.append(("VERIFY", json.loads(content)))
        g["read_back"] = lambda tid, as_json: None
        g["LISTS"] = {"dev": "1"}
        g["CONFIG"] = {}
        a = SimpleNamespace(list="dev", status=None, assignee=None, priority=None, customer=None, tag=None,
                            parent=None, name="n", description=f"zie\n![s]({self.png})", description_file=None, json=False)
        MODULE["cmd_create"](a)
        self.assertEqual([c[0] for c in calls], ["POST", "UPLOAD", "GET", "PUT", "VERIFY"])
        self.assertIn({"insert": {"image": "https://att.test/shot.png"}}, calls[-1][1]["ops"])


class LinksBeforeCodeBlockTests(unittest.TestCase):
    """ClickUp strips explicit description links that precede a code block (readback 2026-10-05)."""

    guard = staticmethod(MODULE["guard_links_before_code"])
    delta = staticmethod(MODULE["md_to_delta"])

    def test_link_before_code_block_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            self.guard(self.delta("See [retro](https://example.com/r).\n\n```\nhello\n```"))
        self.assertIn("'retro'", str(cm.exception))

    def test_links_without_code_block_are_fine(self):
        self.guard(self.delta("See [retro](https://example.com/r) and [plan](https://example.com/p)."))

    def test_code_block_before_link_is_fine(self):
        self.guard(self.delta("```\nhello\n```\n\nSee [retro](https://example.com/r)."))

    def test_autolinks_clickup_rebuilds_are_fine(self):
        content = json.dumps({"ops": [
            {"insert": "info@x.be", "attributes": {"link": "mailto:info@x.be"}},
            {"insert": "SKILL.md", "attributes": {"link": "http://SKILL.md"}},
            {"insert": "hello"}, {"insert": "\n", "attributes": {"code-block": {"code-block": "plain"}}}]})
        self.guard(content)
