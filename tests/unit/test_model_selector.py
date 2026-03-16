import importlib


def test_model_selector_module_exists():
    try:
        module = importlib.import_module("ai.model_selector")
    except ModuleNotFoundError as exc:
        raise AssertionError("Expected module ai.model_selector to exist") from exc

    assert hasattr(module, "ModelSelector"), "ModelSelector class should be defined"


def test_select_flash_for_small_chunks():
    module = importlib.import_module("ai.model_selector")
    selector = module.ModelSelector(
        config={
            "model_thresholds": {
                "small": {"max_chars": 5000, "model": "gemini-2.5-flash"},
                "medium": {"max_chars": 10000, "model": "gemini-2.5-flash"},
                "large": {"max_chars": None, "model": "gemini-2.5-pro"},
            }
        }
    )
    assert selector.select(chunk_size=3000) == "gemini-2.5-flash"


def test_select_pro_for_large_chunks():
    module = importlib.import_module("ai.model_selector")
    selector = module.ModelSelector(
        config={
            "model_thresholds": {
                "small": {"max_chars": 5000, "model": "gemini-2.5-flash"},
                "medium": {"max_chars": 10000, "model": "gemini-2.5-flash"},
                "large": {"max_chars": None, "model": "gemini-2.5-pro"},
            }
        }
    )
    assert selector.select(chunk_size=15000) == "gemini-2.5-pro"
