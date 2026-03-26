"""Test that epub_translate_roundtrip can be imported without google-genai when using CLI provider."""

from __future__ import annotations

import sys
from unittest.mock import patch


def test_can_import_without_google_genai_for_cli_provider() -> None:
    """
    Verify that epub_translate_roundtrip module can be imported
    even when google-genai package is not available,
    as long as we're using CLI provider (not API provider).
    
    This is critical because:
    - CLI users don't need google-genai installed
    - GeminiAPIProvider should only be imported when actually needed
    - Import failure blocks the entire EPUB workflow unnecessarily
    """
    import builtins
    
    # Simulate google-genai package not being available
    with patch.dict(sys.modules, {"google.genai": None, "google": None}):
        # Block actual import attempts
        original_import = builtins.__import__
        
        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("google"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)
        
        with patch("builtins.__import__", side_effect=mock_import):
            # This should NOT raise ImportError
            # because GeminiAPIProvider import should be lazy
            from ai import epub_translate_roundtrip
            
            # Verify the module loaded successfully
            assert epub_translate_roundtrip is not None
            assert hasattr(epub_translate_roundtrip, "run_translate_roundtrip")


def test_api_provider_import_fails_gracefully_when_needed() -> None:
    """
    When API provider is actually requested but google-genai is not available,
    it should fail with a clear error message (not at import time, but at usage time).
    """
    # This test will be added after we implement lazy import
    # For now, we just need the first test to drive the refactor
    pass
