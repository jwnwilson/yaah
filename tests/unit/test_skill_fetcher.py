import os
import tempfile

from adapters.skills.fake import FakeSkillFetcher
from adapters.skills.fetcher import SkillFetcher


def test_fake_records_fetches():
    f = FakeSkillFetcher()
    f.fetch("git@x/s.git", "/ws/.claude/skills/pytest")
    assert f.fetched == [("git@x/s.git", "/ws/.claude/skills/pytest")]


def test_local_path_source_is_copied():
    src = tempfile.mkdtemp()
    open(os.path.join(src, "SKILL.md"), "w").write("# skill")
    dest = os.path.join(tempfile.mkdtemp(), "pytest")
    SkillFetcher().fetch(src, dest)
    assert os.path.exists(os.path.join(dest, "SKILL.md"))
