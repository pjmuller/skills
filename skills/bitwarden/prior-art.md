# Prior art: agent credential brokers and Touch ID CLIs

Comparable open-source work, reviewed 2026-10-28 from source (read-only clones, pinned versions). Purpose: follow
these up when they change, borrow ideas, never adopt a layer just because one has it. Verdict then: none replaces
bw-once, because each is weaker on one of these:
- the touch is cryptographic (it is needed to decrypt, not just a yes/no dialog);
- one field per destination host;
- the approval is bound to the exact request.

| Repo @ version | Interesting | Less | Revisit when |
|---|---|---|---|
| [bitwarden/agent-access](https://github.com/bitwarden/agent-access) v0.11.0, `5127562` | Bitwarden's open protocol for agents asking for one credential; Noise tunnel; per-request human approval; [OneCLI](https://github.com/onecli/onecli) injects by hostname on top | y/n in a terminal UI, no biometrics; `bw get item <search>`, not URI rules; returns the whole item incl. TOTP seed; vault unlocked with the master password; unsigned; "purpose" text still open (protocol §5.4) | URI-based query, field-only reply and a purpose string land: then bw-once could serve its protocol |
| [bitwarden/clients](https://github.com/bitwarden/clients) CLI biometric unlock, CLI 2026.10.0 ([PR #22448](https://github.com/bitwarden/clients/pull/22448)) | Could remove the stored master passwords (enrolment, renewal) | Server flag `biometrics-sdk-ipc` off on US and EU clouds (2026-10-28); returns the **full user key**; IPC without peer authentication (Noise NN); macOS Desktop side is a UI gate over a plain keychain item; needs Desktop running | `bw-once doctor` → `touch_id_flag: true` |
| [maxgoedjen/secretive](https://github.com/maxgoedjen/secretive) v4.0.0, `164aacc` | Reference Secure Enclave + Touch ID implementation (SSH keys); sheet names app and key; requester traced via `SecCode`; XPC code-signing requirement; notarized releases with GitHub attestations | SSH signing only; PID-based peer lookup (racy vs audit token) | We set up Developer ID signing: copy its release pipeline |
| [remko/age-plugin-se](https://github.com/remko/age-plugin-se) v0.2.1, `57ccea1` | Same CryptoKit enclave key-agreement pattern as our seal; proves it works unsigned | Default allows passcode instead of biometry; not notarized; no request text in the sheet | Never as a dependency; reference only |
| [jmeh-sindikata/grantpin](https://github.com/jmeh-sindikata/grantpin) v0.2.4, `303c451` | `reason.go` `BuildReason`: exact action in the Touch ID sheet (idea adopted 2026-10-28); signing/notarize scripts | Touch ID is a UI gate with Mac-password fallback; enclave key without biometry; secrets in the child's env; repo 2 days old | It matures (security review, users) |
| [kovyrin/agent-secret](https://github.com/kovyrin/agent-secret) v0.0.33, `fe9c2dd` | Strongest caller check (getpeereid + LOCAL_PEERCRED + PID path + Team ID); approval bound to command, cwd, refs, expiry, use count; [post](https://kovyrin.net/2026/06/04/agent-secret/) "Touch ID is not enough" | Click, not biometry; Bitwarden Secrets Manager, not logins; env injection | We need caller identity (only matters once signed) |
| [vkend/briefcred](https://github.com/vkend/briefcred) v0.1.3, `a6a0142` | Agent holds a placeholder token, a local proxy swaps in the real API key per request (Cedar policy): the agent never sees API keys | Alpha; plain keychain items; Touch ID per profile, cached 300 s | Agents need API keys, not web logins |
| [NathanielInman/credential-broker](https://github.com/NathanielInman/credential-broker) v2.0.1, `6736e4f` | Crypto-bound touch via age-plugin-se; output redaction | Sheet carries no request text; Mac build from source; secrets in env | — |
| [gabrielkoerich/passbox](https://github.com/gabrielkoerich/passbox) v2.0.5, `573ccdf` | Exact-name, expiring grants; enclave-wrapped store key; works without Developer ID | Separate vault (duplicates Bitwarden); caches the store key; agent labels unverified | — |
| [tvanreenen/key](https://github.com/tvanreenen/key) v0.2.0, `58dccbc` | Shows what Developer ID allows: `.userPresence` keychain item, XPC signing requirement | Whole vault key for 15 min; clipboard neither concealed nor cleared | Developer ID signing |
| [doy/rbw](https://github.com/doy/rbw) `77464d4` | Mature unofficial Bitwarden CLI with an agent | Full vault in the agent, no peer check, no Touch ID | Issues #320 / #324 (Touch ID) move |
| 1Password `op` ([app integration](https://www.1password.dev/cli/app-integration-security/)), [for AI agents](https://1password.com/blog/1password-for-ai-agents) | Mutual code-signing over XPC; agent autofill to approved destinations | Closed source; whole account per terminal (10 min idle, 12 h max) | An open protocol appears |

Checked, nothing to borrow: [bitwarden/mcp-server](https://github.com/bitwarden/mcp-server) (full vault, plaintext to
the model), [jeanregisser/bitwarden-cli-bio](https://github.com/jeanregisser/bitwarden-cli-bio) (superseded by the
official PR), goldwarden (paused; Touch ID off on macOS), pinentry-touchid (UI gate over an ordinary keychain item),
sekey (dead), envchain and 99designs/keyring (no biometry).
