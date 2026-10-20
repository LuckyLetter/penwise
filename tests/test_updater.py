import io
import json
import subprocess
import zipfile

import pytest

from penwise import updater


class FakeDistribution:
    def __init__(self, direct_url):
        self.direct_url = direct_url

    def read_text(self, name):
        return json.dumps(self.direct_url) if self.direct_url is not None else None


@pytest.mark.parametrize(
    "direct_url, expected",
    [
        ({"url": "file:///Users/me/penwise", "dir_info": {}}, ("directory", "/Users/me/penwise")),
        (  # a wheel installed by hand: updated as it was installed
            {"url": "file:///Users/me/Downloads/penwise-1.0-py3-none-any.whl", "archive_info": {}},
            ("other", "file:///Users/me/Downloads/penwise-1.0-py3-none-any.whl"),
        ),
        (
            {"url": "https://github.com/LuckyLetter/penwise", "vcs_info": {"vcs": "git"}},
            ("git", "https://github.com/LuckyLetter/penwise"),
        ),
        (None, ("other", "")),
    ],
)
def test_install_source(monkeypatch, direct_url, expected):
    monkeypatch.setattr(updater.importlib.metadata, "distribution", lambda name: FakeDistribution(direct_url))
    assert updater.install_source() == expected


@pytest.fixture
def commands(monkeypatch):
    ran = []
    monkeypatch.setattr(updater, "installed_with_uv", lambda: True)
    monkeypatch.setattr(updater, "_run", lambda command: ran.append(command) or True)
    monkeypatch.setattr(updater.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(updater.setup_mac, "penwise_command", lambda: ("/bin/penwise", []))

    class Done:
        stdout = "penwise 9.9.9\n"

    monkeypatch.setattr(updater.subprocess, "run", lambda command, **kwargs: ran.append(command) or Done())
    return ran


def test_update_from_a_downloaded_copy(commands, monkeypatch, tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(updater, "install_source", lambda: ("directory", str(tmp_path)))
    assert updater.run() == 0
    assert commands == [
        ["git", "-C", str(tmp_path), "pull", "--ff-only"],
        ["uv", "tool", "install", "--reinstall", str(tmp_path)],
        ["/bin/penwise", "setup-mac", "--refresh"],
        ["/bin/penwise", "--version"],
    ]
    assert "Updated: penwise 9.9.9" in capsys.readouterr().out


def test_update_from_git(commands, monkeypatch):
    monkeypatch.setattr(updater, "install_source", lambda: ("git", "https://github.com/LuckyLetter/penwise"))
    assert updater.run() == 0
    assert commands[0] == ["uv", "tool", "upgrade", "penwise"]


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


RELEASE = {
    "tag_name": "v9.9.9",
    "assets": [
        {"name": "Penwise.dmg", "browser_download_url": "https://example.org/Penwise.dmg"},
        {
            "name": "penwise-9.9.9-py3-none-any.whl",
            "browser_download_url": "https://example.org/penwise-9.9.9-py3-none-any.whl",
        },
    ],
}


def test_the_newest_release_and_its_wheel(monkeypatch):
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: Response(json.dumps(RELEASE).encode()))
    assert updater.latest_release() == ("9.9.9", "https://example.org/penwise-9.9.9-py3-none-any.whl")

    def private_repository(*args, **kwargs):
        raise updater.urllib.error.HTTPError("", 404, "Not Found", None, None)

    monkeypatch.setattr(updater.urllib.request, "urlopen", private_repository)
    assert updater.latest_release() is None  # nothing to see: no update, no error


def test_without_a_release_to_see_it_says_where_to_download(monkeypatch, capsys):
    monkeypatch.setattr(updater, "install_source", lambda: ("app", "/Applications/Penwise.app"))
    monkeypatch.setattr(updater, "latest_release", lambda: None)
    assert updater.run() == 1
    assert "Download the newest Penwise and put it in Applications" in capsys.readouterr().out


def test_without_uv_it_says_how_to_update(monkeypatch, capsys):
    monkeypatch.setattr(updater, "installed_with_uv", lambda: False)
    monkeypatch.setattr(updater, "install_source", lambda: ("directory", "/Users/me/penwise"))
    assert updater.run() == 1
    assert "pip install --upgrade /Users/me/penwise" in capsys.readouterr().out


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def clones(tmp_path, monkeypatch):
    """An origin repository, the user's download of it, and a second clone to publish from."""
    for name, value in [
        ("GIT_AUTHOR_NAME", "t"),
        ("GIT_AUTHOR_EMAIL", "t@t"),
        ("GIT_COMMITTER_NAME", "t"),
        ("GIT_COMMITTER_EMAIL", "t@t"),
    ]:
        monkeypatch.setenv(name, value)
    origin, download, other = tmp_path / "origin.git", tmp_path / "download", tmp_path / "other"
    git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    git("clone", str(origin), str(other), cwd=tmp_path)
    git("commit", "--allow-empty", "-m", "first", cwd=other)
    git("push", "origin", "main", cwd=other)
    git("clone", str(origin), str(download), cwd=tmp_path)
    monkeypatch.setattr(updater, "install_source", lambda: ("directory", str(download)))
    return other


def test_check_finds_new_commits(clones):
    assert updater.check() is None
    git("commit", "--allow-empty", "-m", "second", cwd=clones)
    git("push", "origin", "main", cwd=clones)
    assert updater.check() == "1 new change"


def test_check_for_a_git_install(monkeypatch):
    monkeypatch.setattr(updater, "install_source", lambda: ("git", "https://example.org/penwise"))
    monkeypatch.setattr(
        updater, "_direct_url", lambda: {"vcs_info": {"commit_id": "aaa", "requested_revision": "main"}}
    )
    monkeypatch.setattr(updater, "_quiet", lambda command: "bbb\trefs/heads/main")
    assert updater.check() == "a new version"
    monkeypatch.setattr(updater, "_quiet", lambda command: "aaa\trefs/heads/main")
    assert updater.check() is None


def test_penwise_app_updates_into_its_own_folder_not_itself(monkeypatch, tmp_path, capsys):
    app = tmp_path / "Applications" / "Penwise.app"
    app.mkdir(parents=True)
    monkeypatch.setenv("PENWISE_APP", str(app))
    monkeypatch.setattr(updater.setup_mac, "SUPPORT", tmp_path / "Support")
    assert updater.install_source() == ("app", str(app))
    monkeypatch.setattr(
        updater, "latest_release", lambda: ("9.9.9", "https://example.org/penwise-9.9.9-py3-none-any.whl")
    )
    assert updater.check() == "version 9.9.9"
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, "w") as zipped:  # a wheel: Python files, zipped
        zipped.writestr("penwise/__init__.py", '__version__ = "9.9.9"\n')
        zipped.writestr("penwise-9.9.9.dist-info/METADATA", "Name: penwise\n")
    site = tmp_path / "Support" / "site"
    (site / "penwise").mkdir(parents=True)
    (site / "penwise" / "__init__.py").write_text('__version__ = "1.0.0"\n')  # an older update
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: Response(wheel.getvalue()))
    refreshed = []
    monkeypatch.setattr(updater, "_refresh_hotkey", lambda: refreshed.append(True))
    assert updater.run() == 0
    assert (site / "penwise" / "__init__.py").read_text() == '__version__ = "9.9.9"\n' and refreshed
    assert list((site / "penwise" / "__pycache__").glob("__init__.*.pyc"))  # compiled: the app writes none
    assert sorted(path.name for path in site.parent.iterdir()) == ["site"]  # nothing left over
    assert "Updated: Penwise 9.9.9" in capsys.readouterr().out
