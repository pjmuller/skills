# Browser onboarding

Keep authenticated work in T3; retain the user's normal browser as fallback.
Browser profiles are separate from AI provider/billing profiles.

1. Offer: “Reuse selected browser logins in T3, or sign in separately?” Ask which
   profiles and which work/personal/client tasks belong to each; don't infer ownership
   from an AI account label. Reuse an existing mapping when available.
2. For import, explain that it copies signed-in cookies once, without ongoing sync.
   Use **Settings → Integrations → Browser profiles → Add profile → Import from**.
   Arrange a moment to quit the source browser; let the user handle OS unlock prompts.
   Use supported sources on that OS; if unavailable, sign in inside T3 instead.
   Never export cookie values to scripts, chat or git.
3. Open one tab per selected T3 profile. Visit a user-chosen service (Gmail, for example);
   inspect only the visible account identity. A successful import count isn't proof of
   login. Record pass / needs sign-in; let the user complete login or MFA when needed.
4. Test native `preview_status` → `preview_open {profileId, reuseExistingTab:false}` (a reused tab keeps its old profile) → focused snapshot/DOM read in each
   installed harness (T3 ≥ 0.1.0: `profileId` works; the Settings default profile may be empty, so
   agents always pass it). Profile cookies are shared by every thread; `incognito` is isolated.
   Google accounts: imported Google sessions die on recent Chrome (device-bound session
   credentials) → sign in to Google inside each T3 profile once.
   Windows: Chromium browsers can't be imported (app-bound encryption) → sign in inside T3 once.
   Login page later → the agent asks the user to log in inside the visible T3 tab with their
   password manager app. Passkey-only sites: sign in in the normal browser, then re-import.
   Real browser over CDP is a last resort: Chrome ≥ 144 shows a focus-stealing consent modal per
   attach; if those pop up, turn off `chrome://inspect/#remote-debugging`.
5. Merge one routing line into the user's canonical global AGENTS.md/CLAUDE.md:
   `Browser: T3 first. {purpose} → {profile} ({verified account}); verify identity. Fallback: {browser/profile}. Details: {absolute guide path}.`
   Keep IDs, version-specific workarounds and test results in their private setup repo's
   browser guide. Preserve existing Chrome mappings; never copy another person's accounts.

No custom cookie or profile-selection script needed. Re-run the identity check after
re-import or profile changes; mark any untested harness/profile explicitly.

Sources: [T3 import](https://github.com/pingdotgg/t3code/blob/v0.1.0/docs/user/browser-import.md),
[Chrome consent per attach](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session).
