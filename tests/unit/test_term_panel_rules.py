"""SPEC-028 §3.3-§3.6 rules, through the pure Term Panel functions."""

from __future__ import annotations

import pytest

from ai.core.glossary import GlossaryManager
from ai.core.term_panel import (
    Candidate,
    Judge,
    JudgeVote,
    Nomination,
    Proposal,
    aggregate,
    build_judge_prompt,
    chunk_candidates,
    merge_nominations,
    parse_judge_reply,
    select_sentences,
    term_key,
)


def _proposal(vendor: str, translation: str, **extra: str) -> Proposal:
    letter = {"google": "A", "openai": "B", "anthropic": "C"}[vendor]
    return Proposal(
        letter,
        vendor,
        translation,
        extra.get("priority"),
        "",
        extra.get("negative", ""),
    )


def _candidate(number: int, term: str, *proposals: Proposal) -> Candidate:
    return Candidate(number, term, term_key(term), tuple(proposals))


def _vote(
    translation: str,
    *,
    keep: bool = True,
    enforce: str = "fixed",
    duplicate_of: int | None = None,
) -> JudgeVote:
    return JudgeVote(
        keep, translation, "fixed" if enforce == "fixed" else "preferred", duplicate_of, "high", ""
    )


def _terms(result_glossary: dict[str, object]) -> dict[str, dict[str, object]]:
    entries = result_glossary["critical_terminology"]
    assert isinstance(entries, list)
    return {str(entry["term"]): entry for entry in entries}


# ── candidates ───────────────────────────────────────────────


def test_term_key_folds_case_hyphens_punctuation_and_a_leading_article() -> None:
    assert term_key("The Interest of the Stronger") == term_key("interest of the stronger")
    assert term_key("God-man") == "god man"
    assert term_key("Ortega y Gasset, Jose") == "ortega y gasset jose"


def test_nominations_merge_as_a_union_with_shared_terms_first() -> None:
    nominations = [
        Nomination("google", "A", [{"term": "Unity", "suggested_translation": "统一"}]),
        Nomination(
            "openai",
            "B",
            [
                {"term": "Leap of faith", "suggested_translation": "信仰的飞跃"},
                {"term": "unity", "suggested_translation": "统一性"},
                {"term": "Unity", "suggested_translation": "合一"},  # a vendor's second entry
            ],
        ),
    ]

    candidates = merge_nominations(nominations)

    assert [c.term for c in candidates] == ["Unity", "Leap of faith"]
    assert [c.id for c in candidates] == [1, 2]
    unity = candidates[0]
    assert [(p.vendor, p.translation) for p in unity.proposals] == [
        ("google", "统一"),
        ("openai", "统一性"),
    ]


# ── sentences ────────────────────────────────────────────────


def test_sentences_match_the_phrase_across_hyphens_and_plurals_one_per_document_first() -> None:
    documents = [
        "A long preface. The social contract binds us. Social contracts differ.",
        "Nothing here.",
        "Rousseau wrote of the social-contract tradition.",
    ]

    sentences = select_sentences("Social contract", documents)

    assert sentences == (
        "The social contract binds us.",
        "Rousseau wrote of the social-contract tradition.",
        "Social contracts differ.",
    )


def test_sentences_fall_back_to_word_stems_when_the_phrase_is_absent() -> None:
    documents = ["This is the doctrine of the two swords, set forth by Gelasius."]

    assert select_sentences("Two swords doctrine", documents) == (documents[0],)


def test_a_long_sentence_is_clipped_around_the_term() -> None:
    sentence = "x " * 300 + "the general will appears here " + "y " * 300 + "end."

    (clipped,) = select_sentences("General will", [sentence])

    assert "general will" in clipped
    assert len(clipped) <= 402 and clipped.startswith("…")


def test_no_match_gives_no_sentences() -> None:
    assert select_sentences("Cosmic morale", ["Nothing relevant."]) == ()


# ── judge prompt and replies ─────────────────────────────────


def test_the_judge_prompt_names_lists_by_letter_never_by_vendor() -> None:
    candidate = Candidate(
        1,
        "Unity",
        "unity",
        (_proposal("google", "统一"), _proposal("openai", "统一性")),
        ("Unity matters.",),
    )

    prompt = build_judge_prompt("Political Thinking", ["A", "B"], [candidate], "Contents", "")

    assert '"list": "A"' in prompt and '"list": "B"' in prompt
    assert "google" not in prompt and "openai" not in prompt
    assert "Unity matters." in prompt and "Political Thinking" in prompt
    assert "INDEX:\n(none)" in prompt


def test_a_judge_reply_parses_with_fences_and_missing_ids_abstain() -> None:
    raw = (
        "```json\n"
        '[{"id": 1, "keep": true, "translation": "统一", "enforce": "fixed",'
        ' "duplicate_of": null, "confidence": "high", "note": "n"},'
        ' {"id": 9, "keep": false, "translation": "x", "enforce": "preferred",'
        ' "duplicate_of": null}]\n```'
    )

    votes = parse_judge_reply(raw, [1, 2])

    assert set(votes) == {1}
    assert votes[1] == JudgeVote(True, "统一", "fixed", None, "high", "n")


@pytest.mark.parametrize(
    "raw,message",
    [
        ("not json", "not JSON"),
        ('{"id": 1}', "JSON array"),
        ('[{"id": 1, "keep": "yes", "translation": "a", "enforce": "fixed"}]', "keep"),
        ('[{"id": 1, "keep": true, "translation": " ", "enforce": "fixed"}]', "translation"),
        ('[{"id": 1, "keep": true, "translation": "a", "enforce": "soft"}]', "enforce"),
        (
            '[{"id": 1, "keep": true, "translation": "a", "enforce": "fixed", "duplicate_of": 1}]',
            "duplicate_of",
        ),
    ],
)
def test_a_malformed_judge_reply_fails(raw: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_judge_reply(raw, [1])


# ── chunks ───────────────────────────────────────────────────


def test_candidates_go_in_one_chunk_when_they_fit_and_keep_a_head_word_together_otherwise() -> None:
    candidates = [
        _candidate(1, "Natural law", _proposal("google", "自然法")),
        _candidate(2, "Natural harmony", _proposal("google", "自然和谐")),
        _candidate(3, "Unity", _proposal("google", "统一")),
    ]

    assert chunk_candidates(candidates, lambda chunk: True) == [candidates]
    chunks = chunk_candidates(candidates, lambda chunk: len(chunk) <= 2)
    assert [[c.id for c in chunk] for chunk in chunks] == [[1, 2], [3]]
    with pytest.raises(ValueError, match="natural"):
        chunk_candidates(candidates, lambda chunk: len(chunk) <= 1)


# ── vote rules ───────────────────────────────────────────────


def test_an_own_only_keep_does_not_count_but_an_own_drop_does() -> None:
    candidates = [
        _candidate(1, "Power", _proposal("openai", "权力")),
        _candidate(2, "Being", _proposal("openai", "存在")),
    ]
    judges = [
        Judge("openai", {1: _vote("权力"), 2: _vote("存在")}),
        Judge("anthropic", {1: _vote("权力", keep=False), 2: _vote("存在")}),
    ]

    result = aggregate(candidates, ["google", "openai", "anthropic"], judges, 100)

    assert set(_terms(result.glossary)) == {"Being"}


def test_a_keep_drop_tie_keeps_the_term() -> None:
    candidates = [
        _candidate(1, "Liberty", _proposal("google", "自由"), _proposal("openai", "自由"))
    ]
    judges = [
        Judge("openai", {1: _vote("自由")}),
        Judge("anthropic", {1: _vote("自由", keep=False)}),
    ]

    result = aggregate(candidates, ["google", "openai"], judges, 100)

    assert "Liberty" in _terms(result.glossary)


def test_without_judges_every_term_stays_and_two_agreeing_vendors_make_it_fixed() -> None:
    candidates = [
        _candidate(1, "Unity", _proposal("google", "统一"), _proposal("openai", "统一")),
        _candidate(2, "Uniformity", _proposal("google", "一律化"), _proposal("openai", "整齐划一")),
        _candidate(3, "Power", _proposal("openai", "权力")),
    ]

    terms = _terms(aggregate(candidates, ["google", "openai"], [], 100).glossary)

    assert terms["Unity"]["tier"] == "fixed"
    assert terms["Uniformity"]["tier"] == "preferred"
    assert (
        terms["Uniformity"]["suggested_translation"] == "一律化"
    )  # first nominator breaks the tie
    assert terms["Uniformity"]["alternatives"] == ["整齐划一"]
    assert terms["Power"]["tier"] == "preferred"


def test_one_nominator_and_one_other_judge_fix_a_term_only_when_they_agree() -> None:
    candidates = [
        _candidate(1, "Estrangement", _proposal("google", "疏离")),
        _candidate(2, "Transcendentalism", _proposal("google", "先验论")),
    ]
    judges = [Judge("openai", {1: _vote("疏离"), 2: _vote("超验主义")})]

    terms = _terms(aggregate(candidates, ["google"], judges, 100).glossary)

    assert terms["Estrangement"]["tier"] == "fixed"
    corrected = terms["Transcendentalism"]
    assert corrected["tier"] == "preferred"
    assert corrected["suggested_translation"] == "超验主义"  # the judge breaks the 1-1 tie
    assert corrected["alternatives"] == ["先验论"]


def test_two_nominators_and_one_nominating_judge_keep_its_own_only_terms() -> None:
    candidates = [_candidate(1, "Power", _proposal("openai", "权力"))]
    judges = [Judge("openai", {1: _vote("权力")})]

    terms = _terms(aggregate(candidates, ["google", "openai"], judges, 100).glossary)

    assert terms["Power"]["tier"] == "preferred"


def test_a_preferred_vote_or_a_dissenting_keeper_prevents_the_fixed_tier() -> None:
    both = (_proposal("google", "疏离"), _proposal("openai", "疏离"))
    candidates = [_candidate(1, "Estrangement", *both), _candidate(2, "Alienation", *both)]
    judges = [
        Judge("openai", {1: _vote("疏离"), 2: _vote("疏离")}),
        Judge("anthropic", {1: _vote("疏离", enforce="preferred"), 2: _vote("隔阂")}),
    ]

    terms = _terms(aggregate(candidates, ["google", "openai", "anthropic"], judges, 100).glossary)

    assert terms["Estrangement"]["tier"] == "preferred"
    assert terms["Alienation"]["suggested_translation"] == "疏离"
    assert terms["Alienation"]["tier"] == "preferred"


def test_the_tie_break_judge_is_the_least_self_preferring_measured_one() -> None:
    own_openai = [_candidate(n, f"o{n}", _proposal("openai", "甲")) for n in range(1, 11)]
    own_anthropic = [_candidate(n, f"a{n}", _proposal("anthropic", "乙")) for n in range(11, 21)]
    split = _candidate(21, "Cosmic morale", _proposal("google", "宇宙意志风貌"))
    candidates = [*own_openai, *own_anthropic, split]
    # openai keeps all its own terms and drops anthropic's: self-preference 1.0.
    openai = {c.id: _vote("甲", keep=c in own_openai) for c in [*own_openai, *own_anthropic]}
    anthropic = {c.id: _vote("乙") for c in [*own_openai, *own_anthropic]}
    openai[21] = _vote("宇宙信念", enforce="preferred")
    anthropic[21] = _vote("宇宙士气", enforce="preferred")
    judges = [Judge("openai", openai), Judge("anthropic", anthropic)]

    result = aggregate(candidates, ["google", "openai", "anthropic"], judges, 100)

    assert result.tie_break_vendor == "anthropic"
    morale = _terms(result.glossary)["Cosmic morale"]
    assert morale["suggested_translation"] == "宇宙士气"
    assert morale["alternatives"] == ["宇宙信念", "宇宙意志风貌"]


def test_unmeasured_judges_break_ties_in_configured_order() -> None:
    candidates = [_candidate(1, "Cosmopolis", _proposal("google", "世界之城"))]
    judges = [
        Judge("openai", {1: _vote("宇宙城邦")}),
        Judge("anthropic", {1: _vote("世界城邦")}),
    ]

    result = aggregate(candidates, ["google"], judges, 100)

    assert result.tie_break_vendor == "openai"
    assert _terms(result.glossary)["Cosmopolis"]["suggested_translation"] == "宇宙城邦"


def test_duplicates_merge_into_their_target_through_chains_but_not_cycles() -> None:
    candidates = [
        _candidate(1, "Ortega y Gasset", _proposal("google", "奥尔特加")),
        _candidate(2, "Ortega y Gasset, Jose", _proposal("openai", "何塞·奥尔特加")),
        _candidate(3, "Jose Ortega", _proposal("anthropic", "奥尔特加")),
        _candidate(4, "God-man", _proposal("google", "神人")),
        _candidate(5, "Man-god", _proposal("google", "人神")),
    ]
    votes = {
        1: _vote("奥尔特加"),
        2: _vote("奥尔特加", duplicate_of=3),
        3: _vote("奥尔特加", duplicate_of=1),
        4: _vote("神人", duplicate_of=5),
        5: _vote("人神", duplicate_of=4),
    }
    judges = [Judge("openai", votes), Judge("anthropic", votes)]

    result = aggregate(candidates, ["google", "openai", "anthropic"], judges, 100)

    assert result.merged == {2: 1, 3: 1}
    terms = _terms(result.glossary)
    assert "Ortega y Gasset" in terms and "Jose Ortega" not in terms
    assert {"God-man", "Man-god"} <= set(terms)


def test_the_cap_keeps_fixed_terms_first_then_more_vendors() -> None:
    candidates = [
        _candidate(1, "Alpha", _proposal("google", "甲")),
        _candidate(2, "Beta", _proposal("google", "乙"), _proposal("openai", "乙")),
        _candidate(3, "Gamma", _proposal("google", "丙"), _proposal("openai", "丁")),
    ]

    result = aggregate(candidates, ["google", "openai"], [], 2)

    assert list(_terms(result.glossary)) == ["Beta", "Gamma"]
    assert result.report["cut_by_limit"] == ["Alpha"]


def test_priority_takes_the_highest_and_a_negative_constraint_naming_a_choice_is_dropped() -> None:
    candidates = [
        _candidate(
            1,
            "Alienation",
            _proposal("google", "异化", priority="medium", negative="NOT 疏离"),
            _proposal("openai", "疏离", priority="critical"),
        ),
        _candidate(
            2,
            "Connascence",
            _proposal("google", "共生性", negative="NOT 并发性"),
            _proposal("openai", "共生性"),
        ),
    ]

    terms = _terms(aggregate(candidates, ["google", "openai"], [], 100).glossary)

    assert terms["Alienation"]["priority"] == "critical"
    assert "negative_constraint" not in terms["Alienation"]  # it names the alternative 疏离
    assert terms["Connascence"]["negative_constraint"] == "NOT 并发性"


def test_the_panel_glossary_loads_as_a_tiered_glossary() -> None:
    candidates = [
        _candidate(1, "Unity", _proposal("google", "统一"), _proposal("openai", "统一")),
        _candidate(2, "Uniformity", _proposal("google", "一律化"), _proposal("openai", "整齐划一")),
    ]

    glossary = aggregate(candidates, ["google", "openai"], [], 100).glossary
    block = GlossaryManager.from_dict(glossary).format_block()

    assert "Unity → 统一" in block
    assert "【建议术语】" in block and "Uniformity → 一律化（也可：整齐划一）" in block


def test_a_hyphenated_term_matches_its_spaced_form() -> None:
    assert select_sentences("God-man", ["The god man is a concept."]) == (
        "The god man is a concept.",
    )


def test_clipping_keeps_the_actual_match_not_an_earlier_word() -> None:
    sentence = "General observations come first. " * 8 + "x " * 150 + "and the general will rules."
    sentence = sentence.replace(". ", ", ")

    (clipped,) = select_sentences("General will", [sentence])

    assert "general will" in clipped and len(clipped) <= 402


def test_one_nominator_without_judges_keeps_every_term_strict_without_a_tier() -> None:
    candidates = [_candidate(1, "Estrangement", _proposal("google", "疏离"))]

    glossary = aggregate(candidates, ["google"], [], 100).glossary

    entries = glossary["critical_terminology"]
    assert isinstance(entries, list) and len(entries) == 1
    assert "tier" not in entries[0]
    assert "必须严格遵守" in GlossaryManager.from_dict(glossary).format_block()


def test_the_report_gives_each_judge_its_sample_and_own_list_keep_rate() -> None:
    candidates = [
        _candidate(1, "Power", _proposal("openai", "权力")),
        _candidate(2, "Unity", _proposal("google", "统一"), _proposal("openai", "统一")),
    ]
    judges = [Judge("openai", {1: _vote("权力", keep=False), 2: _vote("统一")})]

    reports = aggregate(candidates, ["google", "openai"], judges, 100).report["judges"]
    assert isinstance(reports, list) and len(reports) == 1
    report = reports[0]

    assert report["own_only_sample"] == 1
    assert report["own_list_keep_rate"] == 0.5
    assert report["self_preference"] is None  # fewer than ten own-only candidates
