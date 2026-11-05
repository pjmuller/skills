"""Delete-for-everyone: offline, against a fake Neonize client (no real chats, no network)."""
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from whatsapp_bridge import main, revoke_message
from whatsapp_bridge.store import Store

try:  # the repository-root test env has no built Neonize; the API tests below still run there
    from neonize.builder import build_revoke
    from neonize.utils.jid import build_jid
except ImportError:
    build_revoke = build_jid = None

OWN, PEER, GROUP, LID = "32470123456", "32470123457", "120363421529066560@g.us", "123@lid"
PEER_JID = PEER + "@s.whatsapp.net"


class FakeClient:
    """Only what revoke may touch: any other call (e.g. a delete-for-me app-state patch) raises AttributeError."""

    def __init__(self, error=None, sender_override=None):
        self.error, self.sender_override, self.sent, self.built = error, sender_override, [], []

    def get_me(self):
        return type("Me", (), {"JID": build_jid(OWN, "s.whatsapp.net")})()

    def build_revoke(self, chat, sender, message_id, with_go=False):
        self.built.append((chat, sender, message_id, with_go))
        return build_revoke(chat, self.sender_override or sender, message_id, self.get_me().JID)

    def send_message(self, chat, message):
        self.sent.append((chat, message))
        if self.error:
            raise self.error
        return type("Resp", (), {"ID": "REVOKE1", "Timestamp": 1789721600})()


@unittest.skipIf(build_jid is None, "needs the built Neonize (scripts/build-neonize)")
class RevokeTests(unittest.TestCase):
    def setUp(self):
        from whatsapp_bridge.worker import revoke
        self.revoke = revoke
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "history.sqlite")
        now = int(time.time())
        self.store.put(GROUP, "OWNMSG1", now, OWN + "@s.whatsapp.net", True, "obsolete", "sent")
        self.store.put(GROUP, "OTHER1", now, "999@lid", False, "theirs", "live")
        self.store.put(PEER_JID, "PEERMSG", now, OWN + "@s.whatsapp.net", True, "1:1", "sent")
        self.store.alias(LID, PEER_JID)
        self.store.put(LID, "LIDMSG", now, OWN + "@s.whatsapp.net", True, "via lid", "history")
        self.env = patch.dict(os.environ, {"WA_ALLOWED_RECIPIENTS": f"{GROUP},+{PEER}"})
        self.env.start()
        self.sleep = patch("whatsapp_bridge.store.time.sleep")
        self.sleep.start()

    def tearDown(self):
        self.sleep.stop()
        self.env.stop()
        self.tmp.cleanup()

    def attempts(self):
        with sqlite3.connect(self.store.path) as db:
            return db.execute("SELECT chat, id, status, revoke_id FROM revocations ORDER BY rowid").fetchall()

    def run_revoke(self, client, target=GROUP, msg_id="OWNMSG1"):
        return self.revoke(client, self.store, {"target": target, "id": msg_id}, OWN)

    def test_accepted_sends_one_sender_revoke_and_keeps_audit_trail(self):
        client = FakeClient()
        result = self.run_revoke(client)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual((result["chat"], result["id"], result["revoke_id"]), (GROUP, "OWNMSG1", "REVOKE1"))
        self.assertNotIn("warning", result)
        (chat, sender, msg_id, with_go), = client.built
        self.assertEqual((chat.User, chat.Server, sender.User, msg_id, with_go), (GROUP[:-5], "g.us", OWN, "OWNMSG1", False))
        (jid, message), = client.sent
        key = message.protocolMessage.key
        self.assertEqual(message.protocolMessage.type, message.protocolMessage.REVOKE)
        self.assertEqual((jid.Server, key.remoteJID, key.ID, key.fromMe, key.participant), ("g.us", GROUP, "OWNMSG1", True, ""))
        self.assertEqual(self.attempts(), [(GROUP, "OWNMSG1", "accepted", "REVOKE1")])
        self.assertEqual([m["text"] for m in self.store.read(GROUP, 5, OWN) if m["id"] == "OWNMSG1"], ["obsolete"])
        with self.assertRaisesRegex(ValueError, "Already revoked"):  # replay never re-sends
            self.run_revoke(client)
        self.assertEqual(len(client.sent), 1)

    def test_refuses_unknown_mismatched_and_foreign_ids_before_sending(self):
        client = FakeClient()
        for target, msg_id, error in [(GROUP, "NOPE99", "not in local history"),
                                      (GROUP, "PEERMSG", "another chat"),
                                      ("+" + PEER, "OWNMSG1", "another chat"),
                                      (GROUP, "OTHER1", "no admin deletes")]:
            with self.subTest(msg_id=msg_id), self.assertRaisesRegex(ValueError, error):
                self.run_revoke(client, target, msg_id)
        self.assertEqual((client.sent, client.built, self.attempts()), ([], [], []))

    def test_allowlist_still_applies(self):
        client = FakeClient()
        with patch.dict(os.environ, {"WA_ALLOWED_RECIPIENTS": ""}), self.assertRaisesRegex(ValueError, "blocked"):
            self.run_revoke(client)
        self.assertEqual(client.sent, [])

    def test_lid_alias_of_the_same_chat_counts_as_that_chat(self):
        result = self.run_revoke(FakeClient(), "+" + PEER, "LIDMSG")
        self.assertEqual((result["status"], result["chat"]), ("accepted", PEER_JID))

    def test_admin_shaped_revoke_is_never_sent(self):
        client = FakeClient(sender_override=build_jid("999", "s.whatsapp.net"))
        for target, msg_id in [(GROUP, "OWNMSG1"), ("+" + PEER, "PEERMSG")]:  # 1:1 keys carry no participant
            with self.subTest(target=target), self.assertRaisesRegex(RuntimeError, "not a sender revoke"):
                self.run_revoke(client, target, msg_id)
        self.assertEqual((client.sent, self.attempts()), ([], []))

    def test_server_rejection_is_failed_and_may_be_retried_manually(self):
        client = FakeClient(error=Exception("server returned error 479"))
        result = self.run_revoke(client)
        self.assertEqual(result["status"], "failed")
        self.assertIn("479", result["error"])
        client.error = None
        self.assertEqual(self.run_revoke(client)["status"], "accepted")
        self.assertEqual([a[2] for a in self.attempts()], ["failed", "accepted"])

    def test_unknown_outcome_is_uncertain_and_blocks_replay(self):
        client = FakeClient(error=TimeoutError("context deadline exceeded"))
        result = self.run_revoke(client)
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(self.attempts(), [(GROUP, "OWNMSG1", "pending", None)])
        client.error = None
        with self.assertRaisesRegex(ValueError, "unknown outcome"):
            self.run_revoke(client)
        self.assertEqual(len(client.sent), 1)

    def test_old_message_is_sent_with_explicit_warning(self):
        self.store.put(GROUP, "OLDMSG", int(time.time()) - 3 * 24 * 3600, OWN + "@s.whatsapp.net", True, "x", "sent")
        result = self.run_revoke(FakeClient(), msg_id="OLDMSG")
        self.assertEqual(result["status"], "accepted")
        self.assertIn("2-day", result["warning"])


class RevokeApiTests(unittest.TestCase):
    def test_malformed_input_never_starts_worker(self):
        with patch("whatsapp_bridge._call") as call:
            for target, msg_id in [("me", "OWN123"), ("Alice", "OWN123"), (GROUP, ""), (GROUP, "a b c d"),
                                   (GROUP, "x" * 65), (GROUP, "OWN1;--"), (GROUP, ["OWN123"]), (GROUP, "ab")]:
                with self.subTest(target=target, msg_id=msg_id), self.assertRaises(ValueError):
                    revoke_message(target, msg_id)
            call.assert_not_called()
            revoke_message(GROUP, "3EB0-ABC123")
            call.assert_called_once_with("revoke", target=GROUP, id="3EB0-ABC123")

    def test_cli_exits_nonzero_unless_accepted(self):
        for status, code in [("accepted", None), ("failed", 1), ("uncertain", 1)]:
            with self.subTest(status=status), patch("whatsapp_bridge._call", return_value={"status": status}), \
                    patch("sys.argv", ["wa", "revoke", GROUP, "OWN123"]), patch("builtins.print"):
                if code is None:
                    main()
                else:
                    with self.assertRaises(SystemExit) as exit_:
                        main()
                    self.assertEqual(exit_.exception.code, code)
