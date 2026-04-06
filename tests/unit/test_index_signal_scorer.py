from __future__ import annotations

from ai.core.index_signal_scorer import IndexSignalScorer


def test_epub_type_index_scores_as_strong_candidate() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="backmatter.xhtml",
        xhtml='<section epub:type="index"><h2>Index</h2><p>Adapter, 10</p></section>',
    )
    assert scorer.is_strong_candidate(score) is True
    assert "epub_type" in score.reasons


def test_css_glossary_class_scores_as_candidate() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="backmatter.xhtml",
        xhtml='<div class="glossary"><h2>Glossary</h2><p>Connascence, 42</p></div>',
    )
    assert scorer.is_strong_candidate(score) is True
    assert "css_class" in score.reasons


def test_ix_filename_and_anchor_ids_score_as_candidate() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="ix01.xhtml",
        xhtml='<div><a id="index_term_102"></a><p>Hexagonal Architecture, 112</p></div>',
    )
    assert scorer.is_strong_candidate(score) is True
    assert "href_hint" in score.reasons


def test_visual_only_bold_lines_stay_below_threshold_without_supporting_signals() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="appendix.xhtml",
        xhtml="<p><b>Concurrency</b>&nbsp;&nbsp;&nbsp;45, 112<br/></p>",
    )
    assert scorer.is_strong_candidate(score) is False


def test_role_doc_index_scores_as_strong_candidate() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="backmatter.xhtml",
        xhtml='<nav role="doc-index"><h2>Index</h2><p>Adapter, 10</p></nav>',
    )
    assert scorer.is_strong_candidate(score) is True
    assert "epub_type" in score.reasons


def test_data_type_index_scores_as_strong_candidate() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="backmatter.xhtml",
        xhtml='<section data-type="index"><h2>Index</h2><p>Adapter, 10</p></section>',
    )
    assert scorer.is_strong_candidate(score) is True
    assert "epub_type" in score.reasons


def test_heading_hint_contributes_score() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="end.xhtml",
        xhtml="<div><h2>Searchable Terms</h2><p>Adapter, 10</p></div>",
    )
    assert "heading" in score.reasons


def test_line_shape_contributes_score() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="end.xhtml",
        xhtml="<p>Adapter pattern, 10-15, 42</p><p>Bridge pattern, 22</p>",
    )
    assert "line_shape" in score.reasons


def test_combined_signals_exceed_threshold() -> None:
    scorer = IndexSignalScorer()
    score = scorer.score_document(
        href="glossary.xhtml",
        xhtml='<div class="index"><h2>Index</h2><p>Adapter, 10</p></div>',
    )
    assert scorer.is_strong_candidate(score) is True
    assert len(score.reasons) >= 2
