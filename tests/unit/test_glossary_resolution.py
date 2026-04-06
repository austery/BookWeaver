"""Unit tests for glossary request resolution."""

from __future__ import annotations

from ai.core.glossary_resolution import resolve_glossary_request


class TestGlossaryRequestResolution:
    """Test glossary request precedence policy."""

    def test_manual_glossary_wins_over_auto_flags(self) -> None:
        """--glossary <path> takes precedence over all other flags."""
        # Manual glossary wins over --extract-glossary
        result = resolve_glossary_request(
            glossary="/path/to/glossary.json",
            extract_glossary=True,
        )
        assert result.mode == "manual"
        assert result.glossary_path == "/path/to/glossary.json"
        assert result.explicit is True

        # Manual glossary wins over --glossary-mode auto
        result = resolve_glossary_request(
            glossary="/path/to/glossary.json",
            glossary_mode="auto",
        )
        assert result.mode == "manual"
        assert result.glossary_path == "/path/to/glossary.json"
        assert result.explicit is True

        # Manual glossary wins over --glossary-mode deep-scan
        result = resolve_glossary_request(
            glossary="/path/to/glossary.json",
            glossary_mode="deep-scan",
        )
        assert result.mode == "manual"
        assert result.glossary_path == "/path/to/glossary.json"
        assert result.explicit is True

    def test_extract_glossary_maps_to_auto_mode(self) -> None:
        """--extract-glossary resolves to auto mode (legacy compatibility)."""
        result = resolve_glossary_request(extract_glossary=True)
        assert result.mode == "auto"
        assert result.glossary_path is None
        assert result.explicit is False  # Legacy flag is not explicit

    def test_deep_scan_requires_explicit_glossary_mode(self) -> None:
        """--glossary-mode deep-scan is the only way to get deep-scan mode."""
        result = resolve_glossary_request(glossary_mode="deep-scan")
        assert result.mode == "deep-scan"
        assert result.glossary_path is None
        assert result.explicit is True

    def test_glossary_mode_auto_is_explicit(self) -> None:
        """--glossary-mode auto is explicit, unlike --extract-glossary."""
        result = resolve_glossary_request(glossary_mode="auto")
        assert result.mode == "auto"
        assert result.glossary_path is None
        assert result.explicit is True

    def test_no_glossary_resolves_to_none(self) -> None:
        """No glossary flags → none mode."""
        result = resolve_glossary_request()
        assert result.mode == "none"
        assert result.glossary_path is None
        assert result.explicit is False

    def test_glossary_mode_auto_wins_over_extract_glossary(self) -> None:
        """--glossary-mode auto takes precedence over --extract-glossary."""
        result = resolve_glossary_request(
            glossary_mode="auto",
            extract_glossary=True,
        )
        assert result.mode == "auto"
        assert result.explicit is True  # Explicit because of glossary_mode
