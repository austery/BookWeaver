"""SPEC-028 Phase 2 through `bookweaver terms` and the application function, with fake members."""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from ai import cli
from ai.core.glossary import GlossaryManager
from ai.model_profiles import ResolvedModel
from ai.orchestration import PanelError, run_term_panel
from ai.ports.provider import ITranslationProvider, ProviderAuthenticationError

_PANEL = {
    "terminology_panels": {
        "three-vendor": {
            "nominators": ["agy-flash-low", "codex-gpt-6.1-sol-low", "claude-opus-5-5-low"],
            "judges": ["codex-gpt-6.1-sol-low", "claude-opus-5-5-low"],
        }
    }
}
_NOMINATIONS = {
    "gemini": [("garden", "花园"), ("moon", "月亮")],
    "gpt": [("Garden", "花园"), ("gate", "大门")],
    "claude": [("the garden", "园子"), ("hill", "山丘")],
}
_JUDGED = {"garden": "花园", "moon": "月亮", "gate": "大门", "hill": "山冈"}


def _book(path: Path, *, index_file: str = "back07.xhtml") -> None:
    """A two-chapter EPUB whose index file is not named "index"."""
    index_lines = "".join(
        f"<p>{word}, {page}</p>"
        for page, word in enumerate(
            [
                "Garden gate in the index",
                "Hill country, views from",
                "Moon, phases of the",
                "Gate, wooden and iron",
                "Garden, walled and open",
                "Path, gravel",
                "Wall, stone",
            ],
            start=11,
        )
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="content.opf"/></rootfiles></container>',
        )
        archive.writestr(
            "content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>The Garden Book</dc:title>'
            '</metadata><manifest><item id="c1" href="chapter1.xhtml" '
            'media-type="application/xhtml+xml"/><item id="c2" href="chapter2.xhtml" '
            f'media-type="application/xhtml+xml"/><item id="ix" href="{index_file}" '
            'media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/>'
            '<itemref idref="c2"/><itemref idref="ix"/></spine></package>',
        )
        archive.writestr(
            "chapter1.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>The garden gate was open. '
            "The moon rose above the hill.</p></body></html>",
        )
        archive.writestr(
            "chapter2.xhtml",
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>A garden needs a wall.</p>'
            "</body></html>",
        )
        archive.writestr(
            index_file,
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>Index</h1>'
            f"{index_lines}</body></html>",
        )


class FakeMembers:
    """Answers as three vendors would; records every call and readiness check."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.checked: list[str] = []
        self.logged_out: set[str] = set()
        self.broken_judge: str | None = None

    def create(
        self,
        model: ResolvedModel,
        *,
        protocol: str,
        config: dict[str, object],
        allow_paid_api: bool,
        remaining_chars: int,
    ) -> ITranslationProvider:
        assert protocol == "delimiter" and not allow_paid_api
        members = self
        family = next(f for f in _NOMINATIONS if model.model_id.startswith(f))

        class Member(ITranslationProvider):
            def check_ready(self) -> None:
                members.checked.append(model.model_id)
                if family in members.logged_out:
                    raise ProviderAuthenticationError(f"{family} is signed out")

            def translate_batch(self, segments: Sequence[str], *, system_prompt: str) -> list[str]:
                (prompt,) = segments
                judging = prompt.startswith("You are reviewing a translation glossary")
                members.calls.append((family, "judge" if judging else "nominate"))
                if not judging:
                    terms = [
                        {"term": term, "suggested_translation": text, "priority": "high"}
                        for term, text in _NOMINATIONS[family]
                    ]
                    return [json.dumps({"critical_terminology": terms}, ensure_ascii=False)]
                if members.broken_judge == family:
                    return ["I cannot answer in JSON."]
                block = prompt.split("CANDIDATES:\n", 1)[1].split("\n\nTABLE OF CONTENTS:", 1)[0]
                votes = [
                    {
                        "id": item["id"],
                        "keep": True,
                        "translation": _JUDGED[item["term"].lower().removeprefix("the ")],
                        "enforce": "fixed",
                        "duplicate_of": None,
                        "confidence": "high",
                        "note": "依据例句。",
                    }
                    for item in json.loads(block)
                ]
                return [json.dumps(votes, ensure_ascii=False)]

        return Member()


def _run(tmp_path: Path, members: FakeMembers, **options: object) -> Path:
    book = tmp_path / "book.epub"
    if not book.exists():
        _book(book)
    return run_term_panel(
        book,
        "three-vendor",
        config=_PANEL,
        provider_factory=members,  # type: ignore[arg-type]
        max_terms=10,
        **options,  # type: ignore[arg-type]
    )


def test_a_three_vendor_panel_writes_a_tiered_glossary_and_a_report(tmp_path: Path) -> None:
    members = FakeMembers()

    path = _run(tmp_path, members)

    glossary = json.loads(path.read_text(encoding="utf-8"))
    terms = {entry["term"]: entry for entry in glossary["critical_terminology"]}
    assert terms["garden"]["suggested_translation"] == "花园"
    assert terms["garden"]["tier"] == "fixed"  # judges agree; two vendors gave it
    assert terms["hill"]["suggested_translation"] == "山冈"  # judges correct 山丘
    assert terms["hill"]["tier"] == "fixed"
    assert "Hill" not in terms  # one candidate per key
    GlossaryManager.from_dict(glossary)  # loads as a tiered glossary
    report = json.loads((path.parent / "term-panel-report.json").read_text(encoding="utf-8"))
    assert report["letters"] == {
        "A": "agy-flash-low",
        "B": "codex-gpt-6.1-sol-low",
        "C": "claude-opus-5-5-low",
    }
    assert report["calls"] == {"made": 5, "reused": 0}
    assert report["book"] == "The Garden Book"
    # One readiness check per preset; Sol and Opus serve as nominator and judge.
    assert sorted(members.checked) == [
        "claude-opus-5-5-low",
        "gemini-3.8-flash-low",
        "gpt-6.1-sol-low",
    ]
    assert [kind for _, kind in members.calls] == ["nominate"] * 3 + ["judge"] * 2


def test_judges_see_letters_and_body_sentences_never_the_index_or_vendors(tmp_path: Path) -> None:
    prompts: list[str] = []
    members = FakeMembers()
    create = members.create

    def recording(model: ResolvedModel, **kwargs: object) -> ITranslationProvider:
        provider = create(model, **kwargs)  # type: ignore[arg-type]
        original = provider.translate_batch

        def spy(segments: Sequence[str], *, system_prompt: str) -> list[str]:
            prompts.append(segments[0])
            return original(segments, system_prompt=system_prompt)

        provider.translate_batch = spy  # type: ignore[method-assign]
        return provider

    members.create = recording  # type: ignore[method-assign]
    _run(tmp_path, members)

    judge_prompt = next(p for p in prompts if p.startswith("You are reviewing"))
    candidates = json.loads(
        judge_prompt.split("CANDIDATES:\n", 1)[1].split("\n\nTABLE OF CONTENTS:", 1)[0]
    )
    garden = next(item for item in candidates if item["term"].lower() == "garden")
    assert garden["sentences"] == ["The garden gate was open.", "A garden needs a wall."]
    assert not any("in the index" in s for item in candidates for s in item["sentences"])
    assert (
        re.search(
            r"\b(google|openai|anthropic|gemini|gpt|claude)\b",
            judge_prompt.split("INDEX:")[0].split("CANDIDATES:")[1],
            re.I,
        )
        is None
    )
    assert '"list": "C"' in judge_prompt and "The Garden Book" in judge_prompt


def test_a_rerun_reuses_the_glossary_without_creating_a_member(tmp_path: Path) -> None:
    first = _run(tmp_path, FakeMembers())
    members = FakeMembers()
    members.logged_out = {"gpt"}  # a cached glossary needs no member at all

    assert _run(tmp_path, members) == first
    assert members.calls == [] and members.checked == []


def test_a_signed_out_member_stops_the_panel_before_any_model_call(tmp_path: Path) -> None:
    members = FakeMembers()
    members.logged_out = {"claude"}

    with pytest.raises(ProviderAuthenticationError, match="claude is signed out"):
        _run(tmp_path, members)
    assert members.calls == []
    report = next(tmp_path.rglob("term-panel-report.json"))
    assert "signed out" in json.loads(report.read_text(encoding="utf-8"))["failed"]


def test_a_broken_judge_reply_stops_and_the_rerun_reuses_the_good_replies(tmp_path: Path) -> None:
    members = FakeMembers()
    members.broken_judge = "claude"

    with pytest.raises(PanelError, match="claude-opus-5-5-low judge reply 1 is unusable"):
        _run(tmp_path, members)
    assert not list(tmp_path.rglob("glossary.json"))

    repaired = FakeMembers()
    path = _run(tmp_path, repaired)

    assert repaired.calls == [("claude", "judge")]
    report = json.loads((path.parent / "term-panel-report.json").read_text(encoding="utf-8"))
    assert report["calls"] == {"made": 1, "reused": 4}


@pytest.mark.parametrize(
    "panel,message",
    [
        ({"nominators": ["agy-flash-low", "agy-pro-low"]}, "two presets of one vendor"),
        ({"nominators": ["anthropic-pro"]}, "paid preset"),
        ({"nominators": ["no-such-preset"]}, "Unknown preset"),
        ({"nominators": []}, "Too few items"),
        (
            {"nominators": ["codex-gpt-6.1-sol-low"], "judges": ["codex-gpt-6-luna-low"]},
            "no keep vote would count",
        ),
    ],
)
def test_a_misconfigured_panel_fails_before_any_member_exists(
    tmp_path: Path, panel: dict[str, object], message: str
) -> None:
    book = tmp_path / "book.epub"
    _book(book)
    members = FakeMembers()

    # PanelError is a ValueError; an empty list already fails the configuration schema.
    with pytest.raises(ValueError, match=message):
        run_term_panel(
            book,
            "bad",
            config={"terminology_panels": {"bad": panel}},
            provider_factory=members,  # type: ignore[arg-type]
        )
    assert members.calls == [] and members.checked == []


def test_an_unknown_panel_names_the_configured_ones_and_shows_an_example(tmp_path: Path) -> None:
    book = tmp_path / "book.epub"
    _book(book)

    with pytest.raises(PanelError, match=r"configured panels: three-vendor.*terminology_panels"):
        run_term_panel(book, "missing", config=_PANEL)


@pytest.mark.parametrize(
    "options,message",
    [({"mode": "deep-scan"}, "Deep Scan"), ({"allow_paid_api": True}, "Paid Term Panel")],
)
def test_deep_scan_and_paid_members_are_refused_before_any_call(
    tmp_path: Path, options: dict[str, object], message: str
) -> None:
    members = FakeMembers()

    with pytest.raises(PanelError, match=message):
        _run(tmp_path, members, **options)
    assert members.calls == []


def test_a_book_without_an_index_stops_before_any_call(tmp_path: Path) -> None:
    book = tmp_path / "book.epub"
    _book(book)
    with zipfile.ZipFile(book) as archive:
        members_bytes = {name: archive.read(name) for name in archive.namelist()}
    members_bytes["back07.xhtml"] = (
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>End.</p></body></html>'
    )
    with zipfile.ZipFile(book, "w") as archive:
        for name, content in members_bytes.items():
            archive.writestr(name, content)
    members = FakeMembers()

    with pytest.raises(PanelError, match="no usable back-of-book index"):
        _run(tmp_path, members)
    assert members.calls == [] and members.checked == []


def test_the_terms_command_reports_a_panel_error_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    book = tmp_path / "book.epub"
    _book(book)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    with pytest.raises(SystemExit) as stopped:
        cli.main(["terms", str(book), "--panel", "nope", "--allow-paid-api"])

    assert stopped.value.code == 2
    assert "Paid Term Panel members" in capsys.readouterr().err
