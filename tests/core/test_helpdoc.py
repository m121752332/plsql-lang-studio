from html.parser import HTMLParser

import pytest

from pllangstudio import resources
from pllangstudio.core import helpdoc
from pllangstudio.core.helpdoc import Command


def test_topics_are_unique_and_include_dialog_topics():
    assert len(set(helpdoc.TOPICS)) == len(helpdoc.TOPICS)
    for t in ("replace", "batch", "glossary", "theme-font", "event-log"):
        assert t in helpdoc.TOPICS


def test_normalize_topic():
    assert helpdoc.normalize_topic("glossary") == "glossary"
    assert helpdoc.normalize_topic("nope") is None
    assert helpdoc.normalize_topic("-") is None
    assert helpdoc.normalize_topic(None) is None


def test_help_url_with_topic(tmp_path):
    index = tmp_path / "help" / "index.html"
    url = helpdoc.help_url(index, "glossary", "dark")
    assert url.startswith("file:///")
    assert url.endswith("/help/index.html?theme=dark#glossary")


def test_help_url_unknown_topic_goes_to_top(tmp_path):
    url = helpdoc.help_url(tmp_path / "index.html", "nope", "light")
    assert url.endswith("index.html?theme=light")


@pytest.mark.parametrize("cmd, line", [
    (Command("show", "dark", "glossary"), "show glossary dark"),
    (Command("show", "light", None), "show - light"),
    (Command("theme", "dark"), "theme dark"),
])
def test_command_round_trip(cmd, line):
    assert helpdoc.format_command(cmd) == line
    assert helpdoc.parse_command(line + "\n") == cmd


@pytest.mark.parametrize("line", ["", "show", "show glossary", "show glossary blue", "theme",
                                  "theme blue", "jump glossary dark", "show a b c"])
def test_parse_command_rejects_bad_lines(line):
    assert helpdoc.parse_command(line) is None


def test_parse_command_unknown_topic_shows_top():
    assert helpdoc.parse_command("show nope dark") == Command("show", "dark", None)


def test_find_help_program(tmp_path):
    assert helpdoc.find_help_program(tmp_path) is None
    exe = tmp_path / "PLLangHelp" / "PLLangHelp.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    assert helpdoc.find_help_program(tmp_path) == exe


INDEX = resources.path("help/index.html")


class _Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.srcs, self.links = set(), [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag in ("img", "script") and a.get("src"):
            self.srcs.append(a["src"])
        if tag == "link" and a.get("href"):
            self.links.append(a["href"])
        if tag == "a" and (a.get("href") or "").startswith("#"):
            self.links.append(a["href"])


def _parse() -> _Collect:
    p = _Collect()
    p.feed(INDEX.read_text(encoding="utf-8"))
    return p


def test_every_topic_has_a_section():
    assert set(helpdoc.TOPICS) <= _parse().ids


def test_local_files_exist_and_nothing_remote():
    p = _parse()
    for ref in p.srcs + [h for h in p.links if not h.startswith("#")]:
        assert "://" not in ref, ref  # 不連外、不用 CDN
        assert (INDEX.parent / ref).is_file(), ref


def test_in_page_links_point_to_existing_ids():
    p = _parse()
    for href in (h for h in p.links if h.startswith("#")):
        assert href[1:] in p.ids, href
