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
