# SPEC-011 设计文档：ModelResolver & ProviderFactory

**日期**: 2026-03-26  
**状态**: ✅ 设计确认，待实施  
**关联 SPEC**: SPEC-011 (`docs/architecture/specs/SPEC-011-model-selection-and-config-abstraction.md`)

---

## 1. 问题背景

当前有两条翻译 pipeline：

| Pipeline | 入口 | Provider | Alias 来源 | Probe/Fallback |
|----------|------|----------|------------|----------------|
| Markdown | `03_translate_md.py` | `GeminiProvider` (CLI) | ✅ `config.model_aliases` | ✅ 有 |
| EPUB | `ai/epub_translate_roundtrip.py` | `GeminiProvider` + `GeminiAPIProvider` | ❌ 硬编码 `{"pro": "gemini-3-pro-preview"}` | ❌ 无 |

**核心问题**：
1. EPUB pipeline 的 `_MODEL_ALIASES` 硬编码覆盖了 `config.json` 配置，导致 `--model pro` 解析为废弃的 `gemini-3-pro-preview` 而非 `gemini-2.5-pro`
2. 两条 pipeline 的模型解析逻辑重复，行为不一致
3. `03_translate_md.py` 里的 `resolve_model_name` / `build_model_candidates` / `_select_final_model` 散落在业务代码中，不可复用

---

## 2. 设计目标

- **统一**：两条 pipeline 使用同一套模型解析逻辑
- **配置优先**：`config.json` 的 `model_aliases` 完全控制别名映射
- **可测试**：`ModelResolver` 和 `ProviderFactory` 均可独立单测
- **对齐 probe/fallback**：EPUB pipeline 接入与 Markdown pipeline 相同的 probe/fallback 能力

---

## 3. 架构方案

### 3.1 新增两个模块

```
ai/model_resolver.py      ← ModelRole enum + ModelResolver class
ai/provider_factory.py    ← ProviderPair dataclass + ProviderFactory class
```

### 3.2 数据流

```
CLI --model pro
      │
      ▼
ModelResolver(config)         ← 读取 config.model_aliases, fallback_chain,
  .resolve("pro")               model_probe.enabled, enable_fallback
      │
      │ 1. alias 解析: "pro" → "gemini-2.5-pro"  (config 优先，内置兜底)
      │ 2. 构建 candidates: ["gemini-2.5-pro", "gemini-2.5-flash", ...]
      │ 3. probe (若 config 开启): 选第一个可用模型
      ▼
"gemini-2.5-pro"
      │
      ├─→ resolver.get_role("gemini-2.5-pro") → ModelRole.PRO
      │   (用于 is_pro_model 判断：timeout 300s, pre-batch 开关)
      │
      ▼
ProviderFactory(config)
  .create(model, provider_name, api_key, cli_api_fallback_enabled)
      ▼
ProviderPair(
    primary  = GeminiProvider("gemini-2.5-pro"),          # CLI
    fallback = GeminiAPIProvider(api_key, "gemini-2.5-pro") | None
)
```

---

## 4. ModelResolver API

```python
# ai/model_resolver.py

from enum import Enum

class ModelRole(Enum):
    PRO     = "pro"
    FLASH   = "flash"
    LITE    = "lite"
    UNKNOWN = "unknown"


class ModelResolver:
    """
    单一职责：将用户请求的模型标识符解析为最终的 provider 模型名。

    解析优先级：
      1. config.model_aliases（用户配置）
      2. 内置 fallback aliases（_BUILTIN_ALIASES）
      3. probe（若 config.model_probe.enabled = true）
      4. fallback_chain（若 config.enable_fallback = true）

    用法：
        resolver = ModelResolver(config)
        model = resolver.resolve("pro")       # → "gemini-2.5-pro"
        role  = resolver.get_role(model)      # → ModelRole.PRO
    """

    _BUILTIN_ALIASES: dict[str, str] = {
        "pro":   "gemini-2.5-pro",
        "flash": "gemini-2.5-flash",
        "lite":  "gemini-2.5-flash-lite",
    }

    def __init__(self, config: dict) -> None:
        # 读取 config.model_aliases（覆盖内置）
        # 读取 config.fallback_chain
        # 读取 config.enable_fallback（默认 False）
        # 读取 config.model_probe.enabled（默认 False）
        # 若 probe 开启，创建 ModelProbe 实例
        ...

    def resolve(self, requested: str) -> str:
        """
        完整解析：alias → (probe if enabled) → (fallback if enabled) → 模型名

        Args:
            requested: 用户请求的模型名或别名（如 "pro", "flash", "gemini-2.5-pro"）

        Returns:
            具体的 provider 模型名字符串

        Raises:
            ValueError: 检测到 alias 循环
        """
        ...

    def get_role(self, model: str) -> ModelRole:
        """
        反查：具体模型名 → ModelRole

        Args:
            model: 已 resolved 的模型名（如 "gemini-2.5-pro"）

        Returns:
            ModelRole.PRO / FLASH / LITE / UNKNOWN
        """
        ...
```

**关键行为**：
- `ModelResolver(config).resolve("pro")` → `"gemini-2.5-pro"`（从 config）
- `config` 没有 `model_aliases.pro` 时，使用 `_BUILTIN_ALIASES["pro"]`
- probe 失败时降级到下一个 candidate；全部失败时返回第一个 candidate（不崩溃）
- `get_role("gemini-2.5-pro")` → `ModelRole.PRO`（反转 aliases 映射）

---

## 5. ProviderFactory API

```python
# ai/provider_factory.py

from dataclasses import dataclass

@dataclass
class ProviderPair:
    primary: GeminiProvider | GeminiAPIProvider
    fallback: GeminiAPIProvider | None   # None = 不需要 fallback


class ProviderFactory:
    """
    单一职责：根据 provider_name 和配置创建 primary + fallback provider 对。

    用法：
        factory = ProviderFactory(config)
        pair = factory.create("gemini-2.5-pro", provider_name="cli",
                               api_key=..., cli_api_fallback_enabled=True)
        # pair.primary  → GeminiProvider
        # pair.fallback → GeminiAPIProvider | None
    """

    def __init__(self, config: dict) -> None: ...

    def create(
        self,
        model: str,
        provider_name: str = "cli",           # "cli" | "api"
        api_key: str | None = None,
        cli_api_fallback_enabled: bool = False,
    ) -> ProviderPair:
        """
        Args:
            model: 已 resolved 的模型名
            provider_name: "cli" 使用 GeminiProvider，"api" 使用 GeminiAPIProvider
            api_key: API key（仅 API provider 需要）
            cli_api_fallback_enabled: CLI 模式下是否额外创建 API fallback

        Returns:
            ProviderPair(primary, fallback)

        Raises:
            ValueError: provider_name 不是 "cli" 或 "api"
            ValueError: API provider 但 api_key 缺失
        """
        ...
```

---

## 6. 调用方变更

### `03_translate_md.py`

**删除**：`resolve_model_name`, `build_model_candidates`, `_select_final_model`, `_create_model_probe`（本地定义）

**替换为**：
```python
from ai.model_resolver import ModelResolver

resolver = ModelResolver(config)
model = resolver.resolve(requested_model)
```

### `ai/epub_translate_roundtrip.py`

**删除**：`_MODEL_ALIASES`, `_resolve_model_name`

**替换为**：
```python
from ai.model_resolver import ModelResolver, ModelRole
from ai.provider_factory import ProviderFactory

resolver = ModelResolver(config)
model = resolver.resolve(requested_model)
is_pro = resolver.get_role(model) == ModelRole.PRO

factory = ProviderFactory(config)
pair = factory.create(model, provider_name, api_key, cli_api_fallback_enabled)
# pair.primary → 主 provider
# pair.fallback → CLI→API fallback（可为 None）
```

---

## 7. 错误处理

| 场景 | 行为 |
|------|------|
| alias 循环（`pro → flash → pro`） | `ValueError: Model alias cycle detected at 'pro'` |
| 所有 probe candidates 失败 | 降级到第一个 candidate，记录 warning（不崩溃） |
| config 缺少 `model_aliases` | 使用 `_BUILTIN_ALIASES` 兜底 |
| `provider_name` 非法值 | `ValueError: Unknown provider 'xyz'. Expected 'cli' or 'api'` |
| API key 缺失（API provider） | 保持 `GeminiAPIProvider` 原有 `ValueError` |

---

## 8. 测试策略

### `tests/unit/test_model_resolver.py`（新建）

- alias 从 `config.model_aliases` 解析 ✅
- alias 未定义时使用内置 fallback ✅
- alias 循环检测 → `ValueError` ✅
- `get_role()` 正反向映射 ✅
- `config.model_probe.enabled = false` 时直接返回 alias 结果 ✅
- probe 开启时取第一个可用 candidate ✅（mock `ModelProbe`）
- probe 全部失败时 fallback 到第一个 candidate ✅

### `tests/unit/test_provider_factory.py`（新建）

- `provider_name="cli"` → `ProviderPair(primary=GeminiProvider, fallback=None)` ✅
- `provider_name="api"` → `ProviderPair(primary=GeminiAPIProvider, fallback=None)` ✅
- CLI + `cli_api_fallback_enabled=True` → `ProviderPair(primary=GeminiProvider, fallback=GeminiAPIProvider)` ✅
- `provider_name="invalid"` → `ValueError` ✅

### 现有测试

`03_translate_md.py` 和 `epub_translate_roundtrip.py` 的现有测试：接口语义不变，调整 import 路径即可。

---

## 附：两种 "Fallback" 的区分

本设计中存在两种不同语义的 fallback，需明确区分：

| | 类型 | 控制位置 | 说明 |
|---|---|---|---|
| **模型级 fallback** | `config.enable_fallback` + `config.fallback_chain` | `ModelResolver` 读取 config | 尝试下一个模型（如 `gemini-2.5-pro` → `gemini-2.5-flash`） |
| **Provider 级 fallback** | `cli_api_fallback_enabled` 参数 | `ProviderFactory.create()` 调用方传入 | CLI 调用失败时切换到 API provider（同一模型） |

两者互相独立，在不同层处理。

---

## 9. 不在本次范围内

- `GeminiAPIProvider.__init__` 内部的 model 解析逻辑（不做 alias 处理，直接传 resolved model name）
- Provider 选择逻辑（"cli" vs "api"）的配置化（`cli_api_fallback_enabled` 仍由调用方传入）
- SPEC-010 术语提取系统
