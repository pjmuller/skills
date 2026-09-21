## Access checks

Distinguish account identity, offline refresh, granted scopes, and access to the requested resource.
A successful profile request proves neither refreshability nor write access. To test offline access,
call `gws_core.credentials(config)` (it refreshes and verifies in memory); never print tokens.
Report writes as untested unless the task included a verified write. Don't mutate user data just
to test permissions. A resource 404 can mean missing access or an obsolete ID; reauthentication
alone is not a demonstrated fix. Access-token expiry normally refreshes automatically.

## Existing Gmail drafts (either account)

- Fetch the current draft before composing an edit. Treat its latest text as the base; preserve
  the user's wording and make the requested change locally. A tone guide is not permission to
  rewrite unrelated passages. If the user supplies replacement text, use that as the base.
- Keep the draft ID (`gmail-draft-get`, or `api GET /gmail/v1/users/me/drafts/<id>?format=raw`).
  Read raw MIME so recipients, subject, reply headers, attachments, and
  multipart bodies can be preserved. Avoid `set_content` on the whole message when it would
  discard HTML alternatives or attachments; edit the relevant body parts.
- Re-fetch immediately before updating and compare with the version read. If it changed,
  rebase the intended edit on the new version. This reduces races; it is not an atomic lock.
- Update the existing draft, retaining `message.threadId` for replies. Don't recreate it or send
  it. If a create request times out, check drafts before retrying to avoid duplicates.
- Read back and verify the intended text, retained fields/attachments, and `DRAFT` label.
  Report the verified outcome, not merely that the update request succeeded.
