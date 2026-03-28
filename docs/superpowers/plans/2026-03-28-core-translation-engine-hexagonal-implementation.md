# Core Translation Engine Refactor (Hexagonal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-architect the BookWeaver translation logic into a Hexagonal (Ports & Adapters) structure to unify batching logic, eliminate duplication, and enforce architectural boundaries.

**Architecture:** We will implement an `ai/core` domain that holds the `TranslationEngine`, `TextBatcher`, and `GlossaryManager`. We will define strict interfaces in `ai/ports` (`ITranslationProvider`, `IBookSource`). Implementations like Gemini CLI and EPUB parsing will move to `ai/adapters`. Finally, we will configure `import-linter` to ensure the core remains independent.

**Tech Stack:** Python 3.13, Pytest, Import-Linter.

---

### Task 1: Setup Architectural Governance (Import-Linter)

**Files:**
- Create: `.importlinter`
- Modify: `pyproject.toml`
- Test: `tests/integration/test_architecture.py`

- [ ] **Step 1: Install import-linter**

Run: `uv add --dev import-linter`

- [ ] **Step 2: Create .importlinter configuration**

```ini
[importlinter]
root_package = ai

[importlinter:contract:layers]
name = Hexagonal Architecture Layers
type = layers
layers =
    ai.adapters
    ai.ports
    ai.core
```

- [ ] **Step 3: Write an architecture test wrapper**

```python
# tests/integration/test_architecture.py
import subprocess

def test_architecture_boundaries():
    """Ensure import-linter passes, verifying Hexagonal Architecture boundaries."""
    result = subprocess.run(["lint-imports"], capture_output=True, text=True)
    assert result.returncode == 0, f"Architecture violation detected:\n{result.stdout}"
```

- [ ] **Step 4: Run test to verify (Should pass initially or we fix existing)**

Run: `uv run pytest tests/integration/test_architecture.py -v`
Expected: PASS (Since `ai/core` etc. don't exist yet, it should pass, or complain about missing modules. We might need to create the `__init__.py` files first).

- [ ] **Step 5: Create empty directory structure to satisfy linter**

```bash
mkdir -p ai/core ai/ports ai/adapters/providers ai/adapters/sources
touch ai/core/__init__.py ai/ports/__init__.py ai/adapters/__init__.py ai/adapters/providers/__init__.py ai/adapters/sources/__init__.py
```

- [ ] **Step 6: Re-run architecture test**

Run: `uv run lint-imports`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .importlinter tests/integration/test_architecture.py ai/core ai/ports ai/adapters
git commit -m "chore: setup import-linter for hexagonal architecture boundaries"
```

---

### Task 2: Define Ports (Interfaces)

**Files:**
- Create: `ai/ports/provider.py`
- Create: `ai/ports/source.py`
- Test: `tests/unit/test_ports.py`

- [ ] **Step 1: Write the failing test for interfaces**

```python
# tests/unit/test_ports.py
import pytest
from ai.ports.provider import ITranslationProvider
from ai.ports.source import IBookSource, Segment

def test_provider_is_abstract():
    with pytest.raises(TypeError):
        ITranslationProvider()

def test_source_is_abstract():
    with pytest.raises(TypeError):
        IBookSource()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_ports.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'ai.ports.provider'"

- [ ] **Step 3: Implement Provider Port**

```python
# ai/ports/provider.py
from abc import ABC, abstractmethod

class ITranslationProvider(ABC):
    @abstractmethod
    def translate(self, text: str, target_lang: str, prompt_template: str = "") -> str:
        """Translate text string using the underlying AI model."""
        pass
```

- [ ] **Step 4: Implement Source Port**

```python
# ai/ports/source.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable

@dataclass
class Segment:
    id: str
    text: str
    is_translatable: bool

class IBookSource(ABC):
    @abstractmethod
    def get_segments(self) -> Iterable[Segment]:
        """Yield translatable units from the source book."""
        pass
    
    @abstractmethod
    def save_segments(self, segments: Iterable[Segment]) -> None:
        """Persist translated segments back to the source."""
        pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_ports.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ai/ports/ tests/unit/test_ports.py
git commit -m "feat: define ITranslationProvider and IBookSource ports"
```

---

### Task 3: Extract TextBatcher (Core Domain)

**Files:**
- Create: `ai/core/batcher.py`
- Test: `tests/unit/test_core_batcher.py`

- [ ] **Step 1: Write tests for TextBatcher**

```python
# tests/unit/test_core_batcher.py
from ai.core.batcher import TextBatcher
from ai.ports.source import Segment

def test_batcher_groups_segments_by_char_limit():
    batcher = TextBatcher(max_chars=20, delimiter="%%")
    segments = [
        Segment("1", "Hello world", True), # 11 chars
        Segment("2", "Test", True),        # 4 chars
        Segment("3", "Another long string", True) # 19 chars
    ]
    
    batches = list(batcher.create_batches(segments))
    assert len(batches) == 2
    assert len(batches[0]) == 2 # 11 + 4 + delimiter < 20
    assert len(batches[1]) == 1 # 19 < 20

def test_batcher_formats_text():
    batcher = TextBatcher(max_chars=100, delimiter="%%")
    segments = [Segment("1", "A", True), Segment("2", "B", True)]
    text = batcher.format_batch(segments)
    assert text == "A\n\n%%\n\nB"

def test_batcher_parses_response():
    batcher = TextBatcher(max_chars=100, delimiter="%%")
    response = "Translated A\n\n%%\n\nTranslated B"
    results = batcher.parse_response(response)
    assert results == ["Translated A", "Translated B"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_core_batcher.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TextBatcher**

```python
# ai/core/batcher.py
from typing import Iterable
from ai.ports.source import Segment
import re

class TextBatcher:
    def __init__(self, max_chars: int = 60000, delimiter: str = "%%"):
        self.max_chars = max_chars
        self.delimiter = delimiter
        self.separator = f"\n\n{self.delimiter}\n\n"
        self.split_pattern = re.compile(rf"\n\s*{re.escape(self.delimiter)}\s*\n")

    def create_batches(self, segments: Iterable[Segment]) -> Iterable[list[Segment]]:
        current_batch: list[Segment] = []
        current_length = 0

        for segment in segments:
            if not segment.is_translatable:
                continue
                
            segment_len = len(segment.text)
            sep_len = len(self.separator) if current_batch else 0
            
            if current_batch and (current_length + sep_len + segment_len > self.max_chars):
                yield current_batch
                current_batch = []
                current_length = 0
                
            current_batch.append(segment)
            current_length += sep_len + segment_len
            
        if current_batch:
            yield current_batch

    def format_batch(self, segments: list[Segment]) -> str:
        return self.separator.join(s.text for s in segments)

    def parse_response(self, response_text: str) -> list[str]:
        return [part.strip() for part in self.split_pattern.split(response_text)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_core_batcher.py -v`
Expected: PASS

- [ ] **Step 5: Run architecture linter to ensure purity**

Run: `uv run lint-imports`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ai/core/batcher.py tests/unit/test_core_batcher.py
git commit -m "feat: implement TextBatcher in core domain"
```

---

### Task 4: Implement TranslationEngine (Core Domain)

**Files:**
- Create: `ai/core/engine.py`
- Test: `tests/unit/test_core_engine.py`

- [ ] **Step 1: Write test for TranslationEngine**

```python
# tests/unit/test_core_engine.py
from ai.core.engine import TranslationEngine
from ai.core.batcher import TextBatcher
from ai.ports.provider import ITranslationProvider
from ai.ports.source import IBookSource, Segment

class MockProvider(ITranslationProvider):
    def translate(self, text: str, target_lang: str, prompt_template: str = "") -> str:
        # Simple mock: just return uppercase
        parts = text.split("%%")
        return "%%".join([p.strip().upper() for p in parts])

class MockSource(IBookSource):
    def __init__(self):
        self.saved_segments = []
    def get_segments(self):
        return [Segment("1", "hello", True), Segment("2", "world", True)]
    def save_segments(self, segments):
        self.saved_segments.extend(segments)

def test_engine_orchestrates_translation():
    provider = MockProvider()
    source = MockSource()
    batcher = TextBatcher(max_chars=100)
    engine = TranslationEngine(provider, batcher)
    
    engine.run(source, "zh")
    
    assert len(source.saved_segments) == 2
    assert source.saved_segments[0].text == "HELLO"
    assert source.saved_segments[1].text == "WORLD"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_core_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TranslationEngine**

```python
# ai/core/engine.py
from ai.ports.provider import ITranslationProvider
from ai.ports.source import IBookSource, Segment
from ai.core.batcher import TextBatcher
import time

class TranslationEngine:
    def __init__(self, provider: ITranslationProvider, batcher: TextBatcher):
        self.provider = provider
        self.batcher = batcher

    def run(self, source: IBookSource, target_lang: str) -> None:
        segments = list(source.get_segments())
        batches = self.batcher.create_batches(segments)
        
        translated_segments = []
        
        for batch in batches:
            text_to_translate = self.batcher.format_batch(batch)
            # Basic retry logic placeholder
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.provider.translate(text_to_translate, target_lang)
                    parsed_responses = self.batcher.parse_response(response)
                    
                    if len(parsed_responses) != len(batch):
                        raise ValueError(f"Mismatch: sent {len(batch)}, got {len(parsed_responses)}")
                        
                    for original_segment, translated_text in zip(batch, parsed_responses):
                        translated_segments.append(
                            Segment(id=original_segment.id, text=translated_text, is_translatable=True)
                        )
                    break # Success
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise RuntimeError(f"Translation failed after {max_retries} attempts: {e}")
                    time.sleep(1) # Simple backoff
                    
        source.save_segments(translated_segments)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_core_engine.py -v`
Expected: PASS

- [ ] **Step 5: Run architecture test**

Run: `uv run lint-imports`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ai/core/engine.py tests/unit/test_core_engine.py
git commit -m "feat: implement basic TranslationEngine orchestration"
```

---

### Task 5: Implement GeminiCLIAdapter

**Files:**
- Create: `ai/adapters/providers/gemini_cli_adapter.py`
- Modify: `tests/unit/test_gemini_cli_adapter.py`

- [ ] **Step 1: Write test for Adapter**

```python
# tests/unit/test_gemini_cli_adapter.py
from ai.adapters.providers.gemini_cli_adapter import GeminiCLIAdapter
from unittest.mock import patch, MagicMock

@patch("subprocess.run")
def test_cli_adapter_calls_gemini(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="Mock Translation")
    
    adapter = GeminiCLIAdapter(model="flash")
    result = adapter.translate("Hello", "zh")
    
    assert result == "Mock Translation"
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "gemini" in args
    assert "Hello" in args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_gemini_cli_adapter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement GeminiCLIAdapter**

```python
# ai/adapters/providers/gemini_cli_adapter.py
import subprocess
from ai.ports.provider import ITranslationProvider

class GeminiCLIAdapter(ITranslationProvider):
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model

    def translate(self, text: str, target_lang: str, prompt_template: str = "") -> str:
        # In real implementation, merge prompt_template with text
        # For now, keep it simple mapping to existing logic
        cmd = ["gemini", "generate", "--model", self.model, "--text", text]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Gemini CLI failed: {result.stderr}")
            
        return result.stdout.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_gemini_cli_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Run architecture test**

Run: `uv run lint-imports`
Expected: PASS (Adapters can import Ports, but not Core. Wait, Adapter can import Ports. Does `lint-imports` pass? Yes).

- [ ] **Step 6: Commit**

```bash
git add ai/adapters/providers/gemini_cli_adapter.py tests/unit/test_gemini_cli_adapter.py
git commit -m "feat: implement GeminiCLIAdapter implementing ITranslationProvider"
```

---

*(Note: Future tasks would involve implementing `EpubSourceAdapter`, migrating `GlossaryManager`, and finally replacing the ad-hoc logic in `09_epub_translate_roundtrip.py` with this engine. This plan establishes the critical path and boundaries).*
