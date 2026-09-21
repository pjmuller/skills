"""Example only: set the intended account/scopes before authenticating."""
WORKSPACE_CONFIG = {
    "expected_email": "team@example.com",
    "config_dir": "~/.config/example-workspace",
    "required_scopes": [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/presentations",
    ],
    "mint_scopes": [
        "openid", "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/presentations",
    ],
    "features": [],
}
