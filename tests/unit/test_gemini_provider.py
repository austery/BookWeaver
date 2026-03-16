import importlib


def test_gemini_provider_module_exists():
    try:
        module = importlib.import_module("ai.gemini_provider")
    except ModuleNotFoundError as exc:
        raise AssertionError("Expected module ai.gemini_provider to exist") from exc

    assert hasattr(module, "GeminiProvider"), "GeminiProvider class should be defined"


def test_gemini_provider_accepts_valid_model():
    module = importlib.import_module("ai.gemini_provider")
    provider = module.GeminiProvider(model="gemini-2.5-flash")
    assert provider.model == "gemini-2.5-flash"


def test_gemini_provider_rejects_invalid_model():
    module = importlib.import_module("ai.gemini_provider")
    try:
        module.GeminiProvider(model="bad-model")
    except ValueError:
        return
    raise AssertionError("Expected ValueError for invalid model")

