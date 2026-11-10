"""Term Panel runner (SPEC-028 Phase 2): nominate, judge, aggregate, and write a tiered glossary.

The only output is a glossary file plus its report. The translation path never changes; it reads
the glossary through ``--glossary`` like any other.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ai.core.glossary import GlossaryManager
from ai.core.term_panel import (
    SENTENCE_SELECTION_VERSION,
    RULE_VERSION,
    Candidate,
    Judge,
    JudgeVote,
    Nomination,
    aggregate,
    build_judge_prompt,
    chunk_candidates,
    merge_nominations,
    parse_judge_reply,
    select_sentences,
)
from ai.glossary_extractor import (
    body_documents,
    book_title,
    build_index_extraction_prompt,
    has_usable_index,
    locate_index_and_toc,
    parse_glossary_reply,
)
from ai.model_profiles import (
    Preset,
    ResolvedModel,
    find_preset,
    is_metered,
    refuse_disabled_runtime,
    resolve_preset,
)
from ai.ports.provider import ITranslationProvider

DEFAULT_JUDGE_PROMPT_MAX_CHARS = 200_000
_LETTERS = "ABCDEFGH"
_EXAMPLE_PANEL = (
    '"terminology_panels": {"three-vendor": {"nominators": ["agy-flash-low", '
    '"codex-gpt-6.1-sol-low", "claude-opus-5-5-low"], "judges": ["codex-gpt-6.1-sol-low", '
    '"claude-opus-5-5-low"]}}'
)


class PanelError(ValueError):
    """A panel cannot run as configured; raised before any model call where possible."""


class ProviderFactory(Protocol):
    def create(
        self,
        model: ResolvedModel,
        *,
        protocol: str,
        config: dict[str, object],
        allow_paid_api: bool,
        remaining_chars: int,
    ) -> ITranslationProvider: ...


@dataclass(frozen=True)
class PanelMember:
    preset: Preset
    model: ResolvedModel

    @property
    def vendor(self) -> str:
        return self.preset.vendor


@dataclass(frozen=True)
class ResolvedPanel:
    name: str
    nominators: tuple[PanelMember, ...]
    judges: tuple[PanelMember, ...]
    judge_prompt_max_chars: int


@dataclass(frozen=True)
class PanelOutcome:
    glossary_path: Path
    report_path: Path
    reused: bool


def resolve_panel(name: str, config: Mapping[str, object]) -> ResolvedPanel:
    """Validate a named panel from configuration; every refusal happens before any call."""
    panels = config.get("terminology_panels")
    if not isinstance(panels, dict) or name not in panels:
        known = ", ".join(sorted(panels)) if isinstance(panels, dict) and panels else "none"
        raise PanelError(
            f"Unknown Term Panel {name!r}; configured panels: {known}. Add one to your "
            f"configuration, for example: {_EXAMPLE_PANEL}"
        )
    entry = panels[name]
    if not isinstance(entry, dict):
        raise PanelError(f"Term Panel {name!r} must be an object")

    def members(role: str) -> tuple[PanelMember, ...]:
        listed = entry.get(role, [])
        if not isinstance(listed, list) or not all(isinstance(item, str) for item in listed):
            raise PanelError(f"Term Panel {name!r}: {role} must be a list of preset names")
        resolved: list[PanelMember] = []
        for preset_name in listed:
            try:
                preset = find_preset(preset_name)
            except ValueError as exc:
                raise PanelError(f"Term Panel {name!r}: {exc}") from exc
            if is_metered(preset.provider):
                raise PanelError(
                    f"Term Panel {name!r}: {preset_name} is a paid preset; paid panel members "
                    "are not supported yet (SPEC-028 Phase 3)"
                )
            resolved.append(PanelMember(preset, resolve_preset(preset_name)))
        vendors = [member.vendor for member in resolved]
        repeated = sorted({vendor for vendor in vendors if vendors.count(vendor) > 1})
        if repeated:
            raise PanelError(
                f"Term Panel {name!r}: {role} list two presets of one vendor ({', '.join(repeated)}); "
                "one vendor casts one vote"
            )
        return tuple(resolved)

    nominators = members("nominators")
    judges = members("judges")
    if not nominators:
        raise PanelError(f"Term Panel {name!r} needs at least one nominator")
    if len(nominators) == 1 and judges and {j.vendor for j in judges} == {nominators[0].vendor}:
        raise PanelError(
            f"Term Panel {name!r}: the only judges share the only nominator's vendor, so no keep "
            "vote would count; add a judge from another vendor"
        )
    limit = entry.get("judge_prompt_max_chars", DEFAULT_JUDGE_PROMPT_MAX_CHARS)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise PanelError(f"Term Panel {name!r}: judge_prompt_max_chars must be a positive integer")
    return ResolvedPanel(name, nominators, judges, limit)


def panel_identity(
    panel: ResolvedPanel,
    *,
    source_signature: str | None,
    max_terms: int,
    nominator_terms: int,
    mode: str,
) -> str:
    identity = json.dumps(
        {
            "source": source_signature,
            "mode": mode,
            "max_terms": max_terms,
            "nominator_terms": nominator_terms,
            # Preset and model, so a preset re-pointed to another model misses the cache.
            "nominators": [[m.preset.name, m.model.model_id] for m in panel.nominators],
            "judges": [[m.preset.name, m.model.model_id] for m in panel.judges],
            "extractor_version": 1,
            "judge_prompt_max_chars": panel.judge_prompt_max_chars,
            "sentences": SENTENCE_SELECTION_VERSION,
            "rules": RULE_VERSION,
        },
        sort_keys=True,
    )
    return hashlib.sha256(identity.encode()).hexdigest()


@dataclass(frozen=True)
class PanelPlan:
    """Where a panel's glossary lives and whether it exists; decided without any model call."""

    panel: ResolvedPanel
    identity: str
    directory: Path
    max_terms: int
    nominator_terms: int
    mode: str

    @property
    def glossary_path(self) -> Path:
        return self.directory / "glossary.json"

    @property
    def report_path(self) -> Path:
        return self.directory / "term-panel-report.json"

    @property
    def reused(self) -> bool:
        return self.glossary_path.exists()

    def describe(self) -> list[str]:
        """The Confirm view (SPEC-028 §3.14) for this book, with no call: the cached glossary,
        or each member's preset, vendor, runtime and planned calls."""
        if self.reused:
            return [f"[terms] Panel {self.panel.name}: reusing the saved glossary; no model call."]
        return _plan_text(self.panel, self.nominator_terms, self.max_terms).splitlines()

    def audit(self) -> dict[str, object]:
        """The invocation audit's ``term_panel`` field: which quota pools the panel draws on."""
        return {
            "name": self.panel.name,
            "identity": self.identity,
            "reused": self.reused,
            "members": [
                {"role": role, "preset": m.preset.name, "model": m.model.model_id}
                for role, members in (
                    ("nominator", self.panel.nominators),
                    ("judge", self.panel.judges),
                )
                for m in members
            ],
        }


def plan_panel(
    panel: ResolvedPanel,
    *,
    book_dir: Path,
    source_signature: str | None,
    max_terms: int,
    nominator_terms: int,
    mode: str,
) -> PanelPlan:
    """The panel's cache folder and identity (SPEC-028 §3.7); refusals before any call."""
    if mode != "auto":
        raise PanelError(
            "A Term Panel reads the book's index; Deep Scan with a panel is not supported yet "
            "(SPEC-028 Phase 5)"
        )
    if max_terms <= 0 or nominator_terms <= 0:
        raise PanelError("The term limits must be positive")
    identity = panel_identity(
        panel,
        source_signature=source_signature,
        max_terms=max_terms,
        nominator_terms=nominator_terms,
        mode=mode,
    )
    directory = book_dir / ".bookweaver_glossaries" / "panel" / identity
    return PanelPlan(panel, identity, directory, max_terms, nominator_terms, mode)


def _refuse_disabled_members(
    panel: ResolvedPanel, members: Sequence[PanelMember], config: Mapping[str, object]
) -> None:
    """SPEC-028 §3.12: a member that must be called on a disabled runtime stops the panel."""
    for member in members:
        try:
            refuse_disabled_runtime(member.model, config, f"Term Panel member {member.preset.name}")
        except ValueError as exc:
            raise PanelError(f"Term Panel {panel.name!r}: {exc}") from exc


def run_panel(
    epub_path: Path,
    plan: PanelPlan,
    *,
    config: dict[str, object],
    factory: ProviderFactory,
    log: Callable[[str], None] = print,
) -> PanelOutcome:
    """Run the planned panel once per identity; a cached glossary is reused without any call."""
    panel = plan.panel
    max_terms, nominator_terms = plan.max_terms, plan.nominator_terms
    directory = plan.directory
    glossary_path = plan.glossary_path
    report_path = plan.report_path
    if glossary_path.exists():
        log(f"[terms] Reusing the {panel.name} glossary: {glossary_path}")
        return PanelOutcome(glossary_path, report_path, True)

    located = locate_index_and_toc(epub_path)
    if not has_usable_index(epub_path, located.index_text):
        raise PanelError(
            "Cannot run a Term Panel: this EPUB has no usable back-of-book index "
            f"(found {len(located.index_text)} characters of index text). No model was called."
        )
    log(_plan_text(panel, nominator_terms, max_terms))
    providers = {
        member.preset.name: factory.create(
            member.model,
            protocol="delimiter",
            config=config,
            allow_paid_api=False,
            remaining_chars=0,
        )
        for member in (*panel.nominators, *panel.judges)
    }
    replies = directory / "replies"
    calls = {"made": 0, "reused": 0}
    checked: set[str] = set()

    def ensure_ready(members: Sequence[PanelMember]) -> None:
        """SPEC-028 §3.12: check only members that will be called, all before the next call.

        A member whose replies are all saved is never checked, so its runtime may be disabled.
        """
        _refuse_disabled_members(panel, members, config)
        for member in members:
            if member.preset.name not in checked:
                providers[member.preset.name].check_ready()
                checked.add(member.preset.name)

    try:

        def saved_reply(member: PanelMember, prompt: str, purpose: str) -> Path:
            # Keyed on the model and the exact prompt, so a reused reply is never stale.
            digest = hashlib.sha256(f"{member.model.model_id}\n{prompt}".encode()).hexdigest()
            return replies / f"{member.preset.name}-{purpose}-{digest[:24]}.txt"

        def call(member: PanelMember, prompt: str, purpose: str) -> str:
            saved = saved_reply(member, prompt, purpose)
            if saved.exists():
                calls["reused"] += 1
                return saved.read_text(encoding="utf-8")
            log(f"[terms] {member.preset.name}: {purpose}")
            answer = providers[member.preset.name].translate_batch([prompt], system_prompt="")
            if not answer:
                raise PanelError(f"{member.preset.name} returned no reply for {purpose}")
            calls["made"] += 1
            return answer[0]

        def keep(member: PanelMember, prompt: str, purpose: str, raw: str) -> None:
            # Saved only once parsed, so a broken reply is asked for again on the next run.
            _write_atomic(saved_reply(member, prompt, purpose), raw)

        nominations: list[Nomination] = []
        extraction_prompt = build_index_extraction_prompt(
            located.index_text, located.toc_text, nominator_terms
        )
        pending = [
            m
            for m in panel.nominators
            if not saved_reply(m, extraction_prompt, "nominate").exists()
        ]
        # New nominations change every judge prompt, so every judge will then be called too.
        ensure_ready([*pending, *panel.judges] if pending else [])
        for letter, member in zip(_LETTERS, panel.nominators, strict=False):
            raw = call(member, extraction_prompt, "nominate")
            try:
                parsed = parse_glossary_reply(raw)
            except ValueError as exc:
                raise PanelError(f"{member.preset.name} nomination is unusable: {exc}") from exc
            try:
                # The shared glossary validator (a list of objects), then the two fields a
                # candidate needs.
                terms = GlossaryManager.from_dict(parsed, source=member.preset.name).terms
                for position, entry in enumerate(terms):
                    for field_name in ("term", "suggested_translation"):
                        value = entry.get(field_name)
                        if not isinstance(value, str) or not value.strip():
                            raise ValueError(
                                f"term {position} needs a non-empty string {field_name}"
                            )
            except ValueError as exc:
                raise PanelError(f"{member.preset.name} nomination is unusable: {exc}") from exc
            keep(member, extraction_prompt, "nominate", raw)
            nominations.append(Nomination(member.vendor, letter, terms))

        documents = body_documents(epub_path, located.index_href)
        candidates = [
            Candidate(c.id, c.term, c.key, c.proposals, select_sentences(c.term, documents))
            for c in merge_nominations(nominations)
        ]
        title = book_title(epub_path)
        letters = [n.letter for n in nominations]

        def render(chunk: Sequence[Candidate]) -> str:
            return build_judge_prompt(title, letters, chunk, located.toc_text, located.index_text)

        chunks = (
            chunk_candidates(
                candidates, lambda chunk: len(render(chunk)) <= panel.judge_prompt_max_chars
            )
            if panel.judges
            else []
        )
        if panel.judges:
            log(f"[terms] {len(candidates)} candidates; each judge makes {len(chunks)} call(s).")
        ensure_ready(
            [
                judge
                for judge in panel.judges
                if any(
                    not saved_reply(judge, render(chunk), f"judge{number}").exists()
                    for number, chunk in enumerate(chunks, start=1)
                )
            ]
        )
        judges: list[Judge] = []
        for member in panel.judges:
            votes: dict[int, JudgeVote] = {}
            for number, chunk in enumerate(chunks, start=1):
                prompt = render(chunk)
                raw = call(member, prompt, f"judge{number}")
                try:
                    votes.update(parse_judge_reply(raw, [c.id for c in chunk]))
                except ValueError as exc:
                    raise PanelError(
                        f"{member.preset.name} judge reply {number} is unusable: {exc}"
                    ) from exc
                keep(member, prompt, f"judge{number}", raw)
            judges.append(Judge(member.vendor, votes))
    except Exception as exc:
        _write_atomic(
            report_path,
            json.dumps(
                {
                    "panel": panel.name,
                    "failed": f"{type(exc).__name__}: {exc}",
                    "calls": calls,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        raise

    result = aggregate(candidates, [m.vendor for m in panel.nominators], judges, max_terms)
    report = {
        "panel": panel.name,
        "book": title,
        "letters": {
            letter: member.preset.name
            for letter, member in zip(_LETTERS, panel.nominators, strict=False)
        },
        "nominators": [_describe(m) for m in panel.nominators],
        "judges": [_describe(m) for m in panel.judges],
        "calls": calls,
        **result.report,
    }
    _write_atomic(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    _write_atomic(glossary_path, json.dumps(result.glossary, ensure_ascii=False, indent=2))
    summary = result.report["summary"]
    log(f"[terms] {summary}; tie-break judge: {result.tie_break_vendor}")
    log(f"[terms] Glossary: {glossary_path}")
    return PanelOutcome(glossary_path, report_path, False)


def _describe(member: PanelMember) -> dict[str, str]:
    return {
        "preset": member.preset.name,
        "runtime": member.preset.runtime,
        "vendor": member.vendor,
        "model": member.preset.model_id,
    }


def _plan_text(panel: ResolvedPanel, nominator_terms: int, max_terms: int) -> str:
    """The Confirm view (SPEC-028 §3.14), printed before any call."""
    lines = [
        f"[terms] Panel {panel.name}: up to {nominator_terms} terms per nominator, "
        f"at most {max_terms} in the glossary; no paid calls."
    ]
    for role, members in (("nominator", panel.nominators), ("judge", panel.judges)):
        for member in members:
            calls = "1 call" if role == "nominator" else "1 call per chunk"
            lines.append(
                f"[terms]   {role}: {member.preset.name} ({member.vendor}, runtime "
                f"{member.preset.runtime}), {calls}, plus a one-time compatibility probe if "
                "this model and runtime version are not yet certified"
            )
    return "\n".join(lines)


def _write_atomic(path: Path, text: str) -> None:
    """Write through a synced temporary file, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
