"""Term Panel domain rules (SPEC-028 §3.3-§3.6): candidates, sentences, votes, tiers.

No I/O and no model calls. Vendors are plain strings; the runner supplies them.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

Enforce = Literal["fixed", "preferred"]
_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2}
_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_SENTENCE_LIMIT = 400
_SENTENCES_PER_TERM = 3
# Below this many candidates only the judge's vendor nominated, its self-preference is unmeasured.
_MIN_BIAS_SAMPLE = 10
MAX_ALTERNATIVES = 2
SENTENCE_SELECTION_VERSION = 1
RULE_VERSION = 1


@dataclass(frozen=True)
class Proposal:
    """One nominating vendor's entry for a candidate."""

    letter: str
    vendor: str
    translation: str
    priority: str | None
    reason: str
    negative_constraint: str


@dataclass(frozen=True)
class Candidate:
    id: int
    term: str
    key: str
    proposals: tuple[Proposal, ...]
    sentences: tuple[str, ...] = ()

    @property
    def vendors(self) -> frozenset[str]:
        return frozenset(proposal.vendor for proposal in self.proposals)


@dataclass(frozen=True)
class Nomination:
    """The terms one nominator returned, in the extraction schema."""

    vendor: str
    letter: str
    terms: Sequence[Mapping[str, object]]


@dataclass(frozen=True)
class JudgeVote:
    keep: bool
    translation: str
    enforce: Enforce
    duplicate_of: int | None
    confidence: str
    note: str


@dataclass(frozen=True)
class Judge:
    """One judge's votes; a candidate id missing from ``votes`` is an abstention."""

    vendor: str
    votes: Mapping[int, JudgeVote]


@dataclass(frozen=True)
class PanelResult:
    glossary: dict[str, object]
    report: dict[str, object]
    tie_break_vendor: str | None = None
    merged: dict[int, int] = field(default_factory=dict)


def term_key(term: str) -> str:
    """Lower case, hyphens as spaces, punctuation removed, a leading article removed."""
    lowered = term.lower().replace("-", " ")
    cleaned = re.sub(r"[^a-z0-9 ]", "", lowered)
    collapsed = " ".join(cleaned.split())
    return _LEADING_ARTICLE.sub("", collapsed)


def merge_nominations(nominations: Sequence[Nomination]) -> list[Candidate]:
    """The union of all nominations, never an intersection (SPEC-028 §3.3).

    Candidates nominated by more vendors come first, then first appearance; ids start at 1.
    """
    order: list[str] = []
    terms: dict[str, str] = {}
    proposals: dict[str, list[Proposal]] = {}
    for nomination in nominations:
        for entry in nomination.terms:
            term = str(entry.get("term", "")).strip()
            translation = str(entry.get("suggested_translation", "")).strip()
            key = term_key(term)
            if not key or not translation:
                continue
            if key not in proposals:
                order.append(key)
                terms[key] = term
                proposals[key] = []
            if any(item.vendor == nomination.vendor for item in proposals[key]):
                continue  # one proposal per vendor; the first one stands
            priority = entry.get("priority")
            proposals[key].append(
                Proposal(
                    nomination.letter,
                    nomination.vendor,
                    translation,
                    priority if isinstance(priority, str) else None,
                    str(entry.get("reason", "") or ""),
                    str(entry.get("negative_constraint", "") or ""),
                )
            )
    ranked = sorted(
        order, key=lambda key: (-len({p.vendor for p in proposals[key]}), order.index(key))
    )
    return [
        Candidate(index, terms[key], key, tuple(proposals[key]))
        for index, key in enumerate(ranked, start=1)
    ]


def select_sentences(term: str, documents: Sequence[str]) -> tuple[str, ...]:
    """Up to three body sentences that contain the term (SPEC-028 §3.3).

    Whole phrase first, case-insensitive, words joined by spaces or hyphens, optional plural.
    If that finds nothing, every word of four or more letters must occur (as a stem) in one
    sentence. Different documents first, then book order. Long sentences are clipped.
    """
    words = [word for word in re.split(r"[\s/-]+", re.sub(r"\(.*?\)", "", term)) if word]
    if not words:
        return ()
    phrase = re.compile(
        r"(?<!\w)" + r"[\s-]+".join(re.escape(word) for word in words) + r"(?:s|es)?(?!\w)",
        re.IGNORECASE,
    )
    stems = [word.lower()[: max(4, len(word) - 3)] for word in words if len(word) >= 4]
    split = [[s for s in _SENTENCE_END.split(" ".join(text.split())) if s] for text in documents]

    def matches(by_phrase: bool) -> list[tuple[int, str, int]]:
        """(document, sentence, position of the match)."""
        found: list[tuple[int, str, int]] = []
        for number, sentences in enumerate(split):
            for sentence in sentences:
                if by_phrase:
                    hit = phrase.search(sentence)
                    if hit:
                        found.append((number, sentence, hit.start()))
                elif stems and all(stem in sentence.lower() for stem in stems):
                    found.append((number, sentence, sentence.lower().index(stems[0])))
        return found

    hits = matches(True) or matches(False)
    chosen: list[tuple[str, int]] = []
    seen_documents: set[int] = set()
    for number, sentence, position in hits:
        if number not in seen_documents:
            chosen.append((sentence, position))
            seen_documents.add(number)
        if len(chosen) == _SENTENCES_PER_TERM:
            break
    for _, sentence, position in hits:
        if len(chosen) == _SENTENCES_PER_TERM:
            break
        if (sentence, position) not in chosen:
            chosen.append((sentence, position))
    return tuple(_clip(sentence, position) for sentence, position in chosen)


def _clip(sentence: str, position: int) -> str:
    """At most 400 characters around the match."""
    if len(sentence) <= _SENTENCE_LIMIT:
        return sentence
    start = max(0, min(position - 180, len(sentence) - _SENTENCE_LIMIT))
    end = start + _SENTENCE_LIMIT
    return ("…" if start else "") + sentence[start:end] + ("…" if end < len(sentence) else "")


JUDGE_INSTRUCTIONS = """\
You are reviewing a translation glossary for the book "{title}". The target is Simplified \
Chinese for a general educated reader.

Independent lists ({letters}) proposed terms. Below are {count} candidate terms with every \
proposal. For each candidate, "sentences" holds up to three sentences from the book's body where \
the term occurs. Judge each term by how the book actually uses it in those sentences; use the \
table of contents and index as further evidence of what matters in this book. An empty \
"sentences" list means the term was not found verbatim in the body.

For EACH candidate decide:
- keep: true if a reader of a translation needs this term rendered consistently (a concept, \
doctrine, coined phrase, or name central to this book); false if it is too generic, marginal, or \
a duplicate.
- translation: the single best Simplified Chinese rendering for the sense used in the sentences. \
Prefer an established scholarly Chinese term when one exists. You may propose a new rendering if \
all proposals are wrong. Exactly one rendering, no slashes or alternatives.
- enforce: "fixed" only for an author's coined concept, a person's name, a title of a work, or an \
established doctrine or school, where every occurrence must use this rendering. "preferred" for \
every other term: a translator should normally use it but may adapt it to the sentence.
- duplicate_of: the id of another candidate that names the same thing, or null.
- confidence: high, medium, or low.
- note: one short sentence in Chinese explaining the choice, citing the sentences when they \
decided the rendering.

Return ONLY a JSON array, one object per candidate, in id order: {{"id": <int>, "keep": <bool>, \
"translation": "<zh>", "enforce": "<fixed|preferred>", "duplicate_of": <int|null>, \
"confidence": "<high|medium|low>", "note": "<zh>"}}. No markdown fences, no commentary.
"""


def build_judge_prompt(
    title: str,
    letters: Sequence[str],
    candidates: Sequence[Candidate],
    toc_text: str,
    index_text: str,
) -> str:
    """Anonymous: proposals carry letters, never vendors."""
    payload = [
        {
            "id": candidate.id,
            "term": candidate.term,
            "proposals": [
                {
                    "list": proposal.letter,
                    "translation": proposal.translation,
                    "priority": proposal.priority,
                    "reason": proposal.reason,
                }
                for proposal in candidate.proposals
            ],
            "sentences": list(candidate.sentences),
        }
        for candidate in candidates
    ]
    head = JUDGE_INSTRUCTIONS.format(title=title, letters=", ".join(letters), count=len(candidates))
    return (
        f"{head}\nCANDIDATES:\n{json.dumps(payload, ensure_ascii=False, indent=1)}\n\n"
        f"TABLE OF CONTENTS:\n{toc_text or '(none)'}\n\nINDEX:\n{index_text or '(none)'}\n"
    )


ChunkFits = Callable[[Sequence[Candidate]], bool]


def chunk_candidates(candidates: Sequence[Candidate], fits: ChunkFits) -> list[list[Candidate]]:
    """One chunk when everything fits; otherwise chunks that keep a head word together."""
    if fits(candidates):
        return [list(candidates)]
    groups: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        head = candidate.key.split(" ")[0]
        groups.setdefault(head, []).append(candidate)
    chunks: list[list[Candidate]] = []
    current: list[Candidate] = []
    for group in groups.values():
        if current and not fits([*current, *group]):
            chunks.append(current)
            current = []
        if not fits(group):
            raise ValueError(
                f"Candidates sharing the head word {group[0].key.split(' ')[0]!r} do not fit one "
                "judge call; lower the term limit"
            )
        current.extend(group)
    if current:
        chunks.append(current)
    return chunks


def parse_judge_reply(raw: str, ids: Sequence[int]) -> dict[int, JudgeVote]:
    """Votes by candidate id. A reply that is not a JSON array of valid votes fails.

    Ids absent from the reply are abstentions; ids not asked for are ignored.
    """
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Judge reply is not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("Judge reply must be a JSON array")
    wanted = set(ids)
    votes: dict[int, JudgeVote] = {}
    for position, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Judge reply item {position} is not an object")
        number = item.get("id")
        if not isinstance(number, int) or isinstance(number, bool):
            raise ValueError(f"Judge reply item {position} has no integer id")
        if number not in wanted:
            continue
        keep = item.get("keep")
        translation = item.get("translation")
        enforce = item.get("enforce")
        duplicate = item.get("duplicate_of")
        if not isinstance(keep, bool):
            raise ValueError(f"Judge vote {number}: keep must be true or false")
        if not isinstance(translation, str) or not translation.strip():
            raise ValueError(f"Judge vote {number}: translation must be a non-empty string")
        if enforce not in ("fixed", "preferred"):
            raise ValueError(f"Judge vote {number}: enforce must be fixed or preferred")
        if duplicate is not None and (
            not isinstance(duplicate, int) or isinstance(duplicate, bool) or duplicate == number
        ):
            raise ValueError(f"Judge vote {number}: duplicate_of must be another id or null")
        votes[number] = JudgeVote(
            keep,
            translation.strip(),
            "fixed" if enforce == "fixed" else "preferred",
            duplicate,
            str(item.get("confidence", "") or ""),
            str(item.get("note", "") or ""),
        )
    return votes


def aggregate(
    candidates: Sequence[Candidate],
    nominator_vendors: Sequence[str],
    judges: Sequence[Judge],
    max_terms: int,
) -> PanelResult:
    """Apply SPEC-028 §3.4 rules 1-7 and build the glossary and the report."""
    by_id = {candidate.id: candidate for candidate in candidates}
    merged = _duplicate_merges(candidates, judges)
    groups: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        groups.setdefault(merged.get(candidate.id, candidate.id), []).append(candidate)
    bias = _self_preference(candidates, judges)
    tie_order = _tie_break_order(judges, bias)
    tie_break = tie_order[0] if tie_order else None
    # One nominator and no judge is today's single extraction: every term strict, no tier.
    untiered = not judges and len(set(nominator_vendors)) == 1
    vendor_counts: dict[str, int] = {}

    entries: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    for target_id, members in groups.items():
        target = by_id[target_id]
        proposals = [proposal for member in members for proposal in member.proposals]
        vendors = frozenset(proposal.vendor for proposal in proposals)
        votes = {
            judge.vendor: judge.votes[target_id] for judge in judges if target_id in judge.votes
        }
        keep_count = drop_count = 0
        for vendor, vote in votes.items():
            if vote.keep:
                if vendors != {vendor}:  # own-term rule: an own-only keep does not count
                    keep_count += 1
            else:
                drop_count += 1
        kept = not judges or drop_count <= keep_count
        decision: dict[str, object] = {
            "id": target_id,
            "term": target.term,
            "merged_ids": [member.id for member in members if member.id != target_id],
            "nominated_by": sorted(vendors),
            "votes": {
                vendor: {
                    "keep": vote.keep,
                    "translation": vote.translation,
                    "enforce": vote.enforce,
                    "duplicate_of": vote.duplicate_of,
                    "confidence": vote.confidence,
                    "note": vote.note,
                }
                for vendor, vote in votes.items()
            },
            "counted_keep": keep_count,
            "counted_drop": drop_count,
            "kept": kept,
        }
        if not kept:
            decisions.append(decision)
            continue
        judge_vendors = {judge.vendor for judge in judges}
        keepers = [vendor for vendor, vote in votes.items() if vote.keep]
        sources: Counter[str] = Counter()
        for vendor in keepers:
            sources[votes[vendor].translation] += 1
        for vendor in nominator_vendors:
            if vendor in vendors and vendor not in judge_vendors:
                sources[_proposal_of(proposals, vendor).translation] += 1
        if not sources:  # stayed by a tie although no judge kept it
            for vote in votes.values():
                sources[vote.translation] += 1
        if not sources:  # no judge voted at all: the nominators' proposals
            for vendor in nominator_vendors:
                if vendor in vendors:
                    sources[_proposal_of(proposals, vendor).translation] += 1
        ranked = sources.most_common()
        chosen = ranked[0][0]
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            # Rule 4: the tie-break judge's translation; with no judge vote, the first nominator.
            voting = [vendor for vendor in tie_order if vendor in votes]
            if voting:
                chosen = votes[voting[0]].translation
            else:
                first = next(v for v in nominator_vendors if v in vendors)
                chosen = _proposal_of(proposals, first).translation
        fixed = (
            sources[chosen] >= 2
            and all(votes[vendor].translation == chosen for vendor in keepers)
            and all(votes[vendor].enforce == "fixed" for vendor in keepers)
        )
        alternatives = [text for text, _ in ranked if text != chosen][:MAX_ALTERNATIVES]
        entry: dict[str, object] = {
            "term": target.term,
            "suggested_translation": chosen,
            "priority": _priority(proposals),
            "tier": "fixed" if fixed else "preferred",
            "reason": _reason(vendors, keepers, len(judges)),
        }
        if untiered:
            del entry["tier"]
        if alternatives:
            entry["alternatives"] = alternatives
        negative = _negative(proposals, {chosen, *alternatives})
        if negative:
            entry["negative_constraint"] = negative
        entries.append(entry)
        vendor_counts[target.term] = len(vendors)
        decision.update(
            {
                "translation": chosen,
                "sources": dict(ranked),
                "tier": entry.get("tier", "fixed"),
                "alternatives": alternatives,
            }
        )
        decisions.append(decision)

    ordered = sorted(
        entries,
        key=lambda item: (
            item.get("tier", "fixed") != "fixed",
            -vendor_counts[str(item["term"])],
            _PRIORITY_RANK.get(str(item["priority"]), 2),
            term_key(str(item["term"])),
        ),
    )
    capped = ordered[:max_terms]
    cut = [str(item["term"]) for item in ordered[max_terms:]]
    report: dict[str, object] = {
        "rule_version": RULE_VERSION,
        "summary": {
            "candidates": len(candidates),
            "merged": len(merged),
            "dropped": sum(1 for d in decisions if not d["kept"]),
            "fixed": sum(1 for e in capped if e.get("tier", "fixed") == "fixed"),
            "preferred": sum(1 for e in capped if e.get("tier") == "preferred"),
            "cut_by_limit": len(cut),
        },
        "judges": [
            {
                "vendor": judge.vendor,
                "self_preference": bias.get(judge.vendor),
                "own_only_sample": sum(
                    1 for c in candidates if c.vendors == {judge.vendor} and c.id in judge.votes
                ),
                "own_list_keep_rate": _keep_rate(
                    judge, [c for c in candidates if judge.vendor in c.vendors]
                ),
                "abstained": sorted(set(by_id) - set(judge.votes)),
            }
            for judge in judges
        ],
        "tie_break_vendor": tie_break,
        "cut_by_limit": cut,
        "decisions": decisions,
    }
    return PanelResult({"critical_terminology": capped}, report, tie_break, merged)


def _keep_rate(judge: Judge, candidates: Sequence[Candidate]) -> float | None:
    voted = [c for c in candidates if c.id in judge.votes]
    if not voted:
        return None
    return round(sum(judge.votes[c.id].keep for c in voted) / len(voted), 4)


def _proposal_of(proposals: Sequence[Proposal], vendor: str) -> Proposal:
    return next(proposal for proposal in proposals if proposal.vendor == vendor)


def _priority(proposals: Sequence[Proposal]) -> str:
    ranks = [_PRIORITY_RANK.get(p.priority or "", 2) for p in proposals]
    best = min(ranks) if ranks else 2
    return next(name for name, rank in _PRIORITY_RANK.items() if rank == best)


def _negative(proposals: Sequence[Proposal], allowed: set[str]) -> str:
    for proposal in proposals:
        text = proposal.negative_constraint.strip()
        if text and not any(item and item in text for item in allowed):
            return text
    return ""


def _reason(vendors: frozenset[str], keepers: Sequence[str], judge_count: int) -> str:
    nominated = ", ".join(sorted(vendors))
    if not judge_count:
        return f"Term Panel: nominated by {nominated}."
    return f"Term Panel: nominated by {nominated}; kept by {len(keepers)} of {judge_count} judges."


def _duplicate_merges(candidates: Sequence[Candidate], judges: Sequence[Judge]) -> dict[int, int]:
    """Rule 1: a candidate merges into a target at least half of the judges name.

    Chains resolve to their end; a cycle, an unknown target or a self-target merges nothing.
    """
    if not judges:
        return {}
    known = {candidate.id for candidate in candidates}
    direct: dict[int, int] = {}
    for candidate in candidates:
        named = Counter(
            judge.votes[candidate.id].duplicate_of
            for judge in judges
            if candidate.id in judge.votes and judge.votes[candidate.id].duplicate_of is not None
        )
        if not named:
            continue
        target, count = named.most_common(1)[0]
        if target is not None and target in known and count * 2 >= len(judges):
            direct[candidate.id] = target
    resolved: dict[int, int] = {}
    for start in direct:
        seen = {start}
        current = direct[start]
        while current in direct:
            if current in seen:
                break
            seen.add(current)
            current = direct[current]
        else:
            resolved[start] = current
    return resolved


def _self_preference(
    candidates: Sequence[Candidate], judges: Sequence[Judge]
) -> dict[str, float | None]:
    """Rule 5: keep rate on own-vendor-only candidates minus keep rate on the rest, floored at 0."""
    result: dict[str, float | None] = {}
    for judge in judges:
        own = [c for c in candidates if c.vendors == {judge.vendor} and c.id in judge.votes]
        other = [c for c in candidates if c.vendors != {judge.vendor} and c.id in judge.votes]
        if len(own) < _MIN_BIAS_SAMPLE or not other:
            result[judge.vendor] = None
            continue
        own_rate = sum(judge.votes[c.id].keep for c in own) / len(own)
        other_rate = sum(judge.votes[c.id].keep for c in other) / len(other)
        result[judge.vendor] = round(max(0.0, own_rate - other_rate), 4)
    return result


def _tie_break_order(judges: Sequence[Judge], bias: Mapping[str, float | None]) -> list[str]:
    """Rule 5: smallest self-preference first, unmeasured judges after, then configured order."""
    order = [judge.vendor for judge in judges]
    return sorted(
        order,
        key=lambda vendor: (
            bias.get(vendor) is None,
            bias.get(vendor) or 0.0,
            order.index(vendor),
        ),
    )
