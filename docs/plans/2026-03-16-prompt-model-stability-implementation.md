# Prompt & Model Stability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Externalize translation prompts and replace hardcoded model assumptions with config-driven alias + startup probing + fallback selection.

**Architecture:** Keep `03_translate_md.py` as orchestration entrypoint, move prompt content to profile files under `config/prompts/`, and add a lightweight model probe utility with cache. Runtime selection flow becomes `requested model -> alias resolution -> availability probe -> fallback chain`, with explicit failure logs when no candidate is available.

**Tech Stack:** Python 3, Gemini CLI, JSON config (`config/config.json.example`), pytest (`uv run pytest`), bash pipeline (`translatebook.sh`)

---

### Task 1: Add failing tests for prompt externalization and model flexibility

**Files:**
- Modify: `tests/unit/test_translate_step3_refactor.py`
- Modify: `tests/unit/test_gemini_provider.py`
- Test: `tests/unit/test_translate_step3_refactor.py`
- Test: `tests/unit/test_gemini_provider.py`

**Step 1: Write the failing test**

```python
def test_step3_parse_arguments_accepts_non_hardcoded_model(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["03_translate_md.py", "--temp-dir", "/tmp/demo", "--model", "gemini-3-pro-preview"])
    args = module.parse_arguments()
    assert args.model == "gemini-3-pro-preview"
```

```python
def test_gemini_provider_accepts_unknown_model_name():
    provider = GeminiProvider(model="gemini-3-pro-preview")
    assert provider.model == "gemini-3-pro-preview"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py tests/unit/test_gemini_provider.py`  
Expected: FAIL on hardcoded model choices / strict model allow-list.

**Step 3: Write minimal implementation**

Update parser and provider validation to allow non-empty model strings instead of fixed choices.

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py tests/unit/test_gemini_provider.py`  
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_translate_step3_refactor.py tests/unit/test_gemini_provider.py 03_translate_md.py ai/gemini_provider.py
git commit -m "test+refactor: allow non-hardcoded model names"
```

### Task 2: Externalize prompt templates and wire prompt profile loading

**Files:**
- Create: `config/prompts/default_prompt.txt`
- Create: `config/prompts/ebook_prompt.txt`
- Modify: `03_translate_md.py`
- Modify: `config/config.json.example`
- Test: `tests/unit/test_translate_step3_refactor.py`

**Step 1: Write the failing test**

```python
def test_step3_create_translation_prompt_from_external_template():
    config = {"prompt_profile": "default", "prompt_templates": {"default": "/tmp/p.txt"}}
    prompt = module.create_translation_prompt("zh", "extra-rule", runtime_config=config)
    assert "ADDITIONAL INSTRUCTIONS" in prompt
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py::test_step3_create_translation_prompt_from_external_template -v`  
Expected: FAIL because loader/function does not yet support external template path.

**Step 3: Write minimal implementation**

```python
def load_prompt_template(runtime_config): ...
def create_translation_prompt(output_lang, custom_prompt=None, runtime_config=None): ...
```

Template placeholders:
- `{TARGET_LANGUAGE}`
- `{CUSTOM_INSTRUCTIONS_BLOCK}`

Config fields:
- `prompt_profile`
- `prompt_templates`

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add config/prompts/default_prompt.txt config/prompts/ebook_prompt.txt config/config.json.example 03_translate_md.py tests/unit/test_translate_step3_refactor.py
git commit -m "feat: externalize prompt templates with profile loading"
```

### Task 3: Add startup model probe module with cache

**Files:**
- Create: `ai/model_probe.py`
- Create: `tests/unit/test_model_probe.py`
- Modify: `config/config.json.example`

**Step 1: Write the failing test**

```python
def test_probe_uses_cache_when_fresh(tmp_path):
    cache = tmp_path / "model_probe_cache.json"
    # seed cache with recent timestamp and available models
    # assert probe manager returns cached result without shell call
```

```python
def test_probe_marks_unavailable_model(monkeypatch):
    # simulate subprocess non-zero return for a candidate
    # assert candidate marked unavailable with stderr snippet
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_model_probe.py -v`  
Expected: FAIL because module does not exist.

**Step 3: Write minimal implementation**

```python
class ModelProbe:
    def probe(self, candidates: list[str]) -> dict[str, bool]: ...
    def load_cache(self) -> dict: ...
    def save_cache(self, payload: dict) -> None: ...
```

Probe command example:

```bash
gemini --model <candidate> -p "ping"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_model_probe.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add ai/model_probe.py tests/unit/test_model_probe.py config/config.json.example
git commit -m "feat: add startup model probing with cache"
```

### Task 4: Integrate alias resolution + probe + fallback into step 3 runtime

**Files:**
- Modify: `03_translate_md.py`
- Modify: `translatebook.sh` (help text and pass-through behavior)
- Test: `tests/unit/test_translate_step3_refactor.py`

**Step 1: Write the failing test**

```python
def test_step3_resolve_model_name_supports_alias():
    config = {"model_aliases": {"pro": "gemini-2.5-pro"}}
    assert module.resolve_model_name("pro", config) == "gemini-2.5-pro"
```

```python
def test_step3_fallback_chain_selects_first_available():
    # configure probe result: first unavailable, second available
    # expect selected model == second candidate
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py -v`  
Expected: FAIL for missing fallback-chain integration.

**Step 3: Write minimal implementation**

Runtime selection algorithm:
1. Resolve `--model` alias (if provided)
2. Build candidate list (`requested -> fallback_chain`)
3. Filter by probe availability
4. Select first available
5. Error with attempted list if none available

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/unit/test_translate_step3_refactor.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add 03_translate_md.py translatebook.sh tests/unit/test_translate_step3_refactor.py
git commit -m "feat: add alias+probe+fallback model selection flow"
```

### Task 5: Update docs and run full verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/architecture/specs/SPEC-001-multi-tier-gemini-translation.md` (if references need alignment)
- Test: full suite

**Step 1: Write/update doc expectations as checks**

Checklist:
- Prompt source path documented
- Model alias behavior documented
- Probe/fallback behavior documented
- Step3 vs Step4 bilingual behavior clarified

**Step 2: Run tests and validations**

Run:

```bash
uv run pytest -q
bash -n translatebook.sh
python3 -m py_compile 03_translate_md.py ai/gemini_provider.py ai/model_probe.py 05_md_to_html.py 07_generate_formats.py
./translatebook.sh --dry-run --output-format epub --bilingual-style alternating /path/to/book.epub
```

Expected:
- All tests pass
- Syntax checks pass
- Dry-run prints selected model/profile/fallback path clearly

**Step 3: Commit**

```bash
git add README.md CLAUDE.md docs/architecture/specs/SPEC-001-multi-tier-gemini-translation.md
git commit -m "docs: align prompt-profile and model probe behavior"
```

### Task 6: Final cleanup and release note

**Files:**
- Modify: `README.md` (optional changelog snippet)
- Modify: `docs/plans/2026-03-16-prompt-model-stability-design.md` (status to implemented)

**Step 1: Verify working tree and output artifacts**

Run:

```bash
git --no-pager status
```

Expected: only intended files changed.

**Step 2: Summarize implementation outcomes**

Include:
- Prompt profiles delivered
- Probe cache path and TTL
- Model selection precedence
- Known limitations

**Step 3: Commit**

```bash
git add README.md docs/plans/2026-03-16-prompt-model-stability-design.md
git commit -m "chore: finalize prompt-model stability rollout notes"
```

