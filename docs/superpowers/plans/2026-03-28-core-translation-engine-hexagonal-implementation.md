# Core Translation Engine Refactor (Hexagonal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-architect the BookWeaver translation logic into a Hexagonal (Ports & Adapters) structure to unify batching logic, eliminate duplication, and enforce strict architectural boundaries using **Tach**.

**Architecture:** We will implement an `ai/core` domain that holds the `TranslationEngine`, `TextBatcher`, and `GlossaryManager`. We will define strict interfaces in `ai/ports` (`ITranslationProvider`, `IBookSource`). Implementations like Gemini CLI and EPUB parsing will move to `ai/adapters`. We will use **Tach** (Rust-based) to enforce that AI-generated code respects these boundaries and only accesses public interfaces.

**Tech Stack:** Python 3.13, Pytest, Tach (Rust-based architectural linter).

---

### Task 1: Setup Architectural Governance (Tach)

**Files:**
- Create: `tach.toml`
- Modify: `pyproject.toml`
- Test: `tests/integration/test_architecture.py`

- [ ] **Step 1: Install Tach**

Run: `uv add --dev tach`

- [ ] **Step 2: Initialize Tach and Create Directory Structure**

```bash
# Create target structure first
mkdir -p ai/core ai/ports ai/adapters/providers ai/adapters/sources
touch ai/core/__init__.py ai/ports/__init__.py ai/adapters/__init__.py ai/adapters/providers/__init__.py ai/adapters/sources/__init__.py

# Initialize Tach
uv run tach init
```

- [ ] **Step 3: Synchronize Tach to create baseline**

Run: `uv run tach sync`
Expected: `tach.toml` is created/updated with current project dependencies.

- [ ] **Step 4: Configure strict interfaces in tach.toml**

Modify `tach.toml` to define layers and strict boundaries. Ensure `ai.core` is marked as `strict = true` to prevent deep imports.

```toml
# Example target config in tach.toml
[[modules]]
path = "ai.core"
strict = true

[[modules]]
path = "ai.ports"

[[modules]]
path = "ai.adapters"
depends_on = ["ai.ports"]
```

- [ ] **Step 5: Write an architecture test wrapper**

```python
# tests/integration/test_architecture.py
import subprocess

def test_architecture_boundaries():
    """Ensure tach check passes, verifying Hexagonal Architecture boundaries and strict interfaces."""
    result = subprocess.run(["tach", "check"], capture_output=True, text=True)
    assert result.returncode == 0, f"Architecture violation detected by Tach:\n{result.stdout}"
```

- [ ] **Step 6: Run Tach check**

Run: `uv run tach check`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock tach.toml tests/integration/test_architecture.py ai/core ai/ports ai/adapters
git commit -m "chore: setup Tach for hexagonal architecture and strict interface enforcement"
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
from ai.ports.source import IBookSource

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

@dataclass(frozen=True)
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
    assert len(batches[0]) == 2
    assert len(batches[1]) == 1

def test_batcher_formats_text():
    batcher = TextBatcher(max_chars=100, delimiter="%%")
    segments = [Segment("1", "A", True), Segment("2", "B", True)]
    text = batcher.format_batch(segments)
    assert text == "A\n\n%%\n\nB"
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
            if not segment.is_translatable: continue
            segment_len = len(segment.text)
            sep_len = len(self.separator) if current_batch else 0
            if current_batch and (current_length + sep_len + segment_len > self.max_chars):
                yield current_batch
                current_batch, current_length = [], 0
            current_batch.append(segment)
            current_length += sep_len + segment_len
        if current_batch: yield current_batch

    def format_batch(self, segments: list[Segment]) -> str:
        return self.separator.join(s.text for s in segments)

    def parse_response(self, response_text: str) -> list[str]:
        return [part.strip() for part in self.split_pattern.split(response_text)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_core_batcher.py -v`
Expected: PASS

- [ ] **Step 5: Run Tach to ensure no leaks**

Run: `uv run tach check`
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

- [ ] **Step 1: Write test for TranslationEngine using Mocks**

```python
# tests/unit/test_core_engine.py
from ai.core.engine import TranslationEngine
from ai.core.batcher import TextBatcher
from ai.ports.provider import ITranslationProvider
from ai.ports.source import IBookSource, Segment

class MockProvider(ITranslationProvider):
    def translate(self, text: str, target_lang: str, prompt_template: str = "") -> str:
        return "%%".join([p.strip().upper() for p in text.split("%%")])

class MockSource(IBookSource):
    def __init__(self): self.saved = []
    def get_segments(self): return [Segment("1", "hello", True), Segment("2", "world", True)]
    def save_segments(self, segments): self.saved.extend(segments)

def test_engine_orchestrates_translation():
    engine = TranslationEngine(MockProvider(), TextBatcher(max_chars=100))
    source = MockSource()
    engine.run(source, "zh")
    assert [s.text for s in source.saved] == ["HELLO", "WORLD"]
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
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.provider.translate(text_to_translate, target_lang)
                    parsed = self.batcher.parse_response(response)
                    if len(parsed) != len(batch):
                        raise ValueError(f"Mismatch: sent {len(batch)}, got {len(parsed)}")
                    for orig, trans in zip(batch, parsed):
                        translated_segments.append(Segment(id=orig.id, text=trans, is_translatable=True))
                    break
                except Exception as e:
                    if attempt == max_retries - 1: raise
                    time.sleep(1)
        source.save_segments(translated_segments)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_core_engine.py -v`
Expected: PASS

- [ ] **Step 5: Run Tach check**

Run: `uv run tach check`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ai/core/engine.py tests/unit/test_core_engine.py
git commit -m "feat: implement core TranslationEngine"
```

---

### Task 5: Implement GeminiCLIAdapter

**Files:**
- Create: `ai/adapters/providers/gemini_cli_adapter.py`
- Modify: `tests/unit/test_gemini_cli_adapter.py`

- [ ] **Step 1: Write test for GeminiCLIAdapter**

```python
# tests/unit/test_gemini_cli_adapter.py
from ai.adapters.providers.gemini_cli_adapter import GeminiCLIAdapter
from unittest.mock import patch, MagicMock

@patch("subprocess.run")
def test_cli_adapter_calls_gemini(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="Mock Translation")
    adapter = GeminiCLIAdapter(model="flash")
    assert adapter.translate("Hello", "zh") == "Mock Translation"
    mock_run.assert_called_once()
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
        cmd = ["gemini", "generate", "--model", self.model, "--text", text]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"Gemini CLI failed: {result.stderr}")
        return result.stdout.strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_gemini_cli_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Run Tach check**

Run: `uv run tach check`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ai/adapters/providers/gemini_cli_adapter.py tests/unit/test_gemini_cli_adapter.py
git commit -m "feat: implement GeminiCLIAdapter"
```
