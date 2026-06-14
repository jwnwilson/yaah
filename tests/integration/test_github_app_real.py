import os

import pytest

from adapters.git.github_app import GitHubApp

_have = all(os.environ.get(k) for k in
            ("YAAH_GITHUB_APP_ID", "YAAH_GITHUB_PRIVATE_KEY",
             "YAAH_GITHUB_INSTALLATION_ID", "YAAH_GITHUB_REPO"))


@pytest.mark.skipif(not _have, reason="GitHub App creds not configured")
def test_real_installation_token():
    app = GitHubApp(
        app_id=os.environ["YAAH_GITHUB_APP_ID"],
        private_key=os.environ["YAAH_GITHUB_PRIVATE_KEY"],
        installation_id=os.environ["YAAH_GITHUB_INSTALLATION_ID"],
        repo=os.environ["YAAH_GITHUB_REPO"],
    )
    assert app.installation_token()
