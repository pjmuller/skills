"""Local credential readiness only: no network, token output, or refresh."""
from t3_limits import SETTINGS, claude_credentials, codex_credentials, provider_profiles


def check():
    failures = 0
    for driver, reader in (("claudeAgent", claude_credentials), ("codex", codex_credentials)):
        for instance, _label, home in provider_profiles(SETTINGS, driver):
            try:
                reader(home)
            except (LookupError, OSError, ValueError, TypeError, AttributeError):
                # Deliberately omit exception text: malformed credentials must not leak.
                print(f"MISSING {driver} login credential ({instance}); sign in to that profile")
                failures += 1
            else:
                print(f"ok      {driver} local login credential ({instance})")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(check())
