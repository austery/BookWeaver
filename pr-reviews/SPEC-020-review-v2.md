# 设计复审 v2 — SPEC-020：Antigravity CLI 迁移与付费 API 授权

**审查对象：** `docs/architecture/specs/SPEC-020-antigravity-cli-migration-and-paid-api-authorization.md`（commit `664c0b4`，552 行）
**当前状态：** 📝 草案 (Draft) — 在晋级为 `🟡 待实施 (Ready for Implementation)` 之前等待外部 AI 评审
**审查者角色：** 首席工程师（Python / 六边形翻译内核）
**审查类型：** 规格 / 设计门评审（该文档本身不提交代码变更）

## 复审说明（相对 v1 的变化）

- 本轮为应要求的复审，评审语言改用中文；SPEC 文件自 v1 以来**未发生修改**，因此 v1 的 6 项发现全部仍然成立，在下方完整重列（非「已解决」）。
- 本轮**新增 1 项正式发现**（IMPROVEMENT 7：§5.3 移除标志的双层迁移失败消息落差），并补充了若干范围/清理层面的**次要观察**。
- 结论与 v1 一致：存在 2 项 BLOCKER，评审门建议维持 **Request changes**。

---

## 摘要

SPEC-020 是一份结构清晰、以安全为导向的迁移设计。其核心约束——*技术可用 ≠ 花钱授权；CLI 失败绝不能自动触发付费 API*——是正确的，架构直觉（保留 `cli|api` 公共契约、只替换内部后端、把 Antigravity 的进程语义隔离在端口之后）也与既有六边形结构吻合。

但在晋级为「待实施」之前，有两处必须先解决：§7.2 承诺的**付费 API 成本保证在所描述的架构下无法被强制执行**（engine 的分裂重试会放大付费请求数量），以及 §9.2/§9.4 的 **checkpoint 兼容性模型自相矛盾、并悄悄改变了当前的续跑契约**——而这正是 schema v2 迁移的地基。

### 发现清单

| # | 严重度 | 章节 | 发现 |
|---|--------|------|------|
| 1 | **BLOCKER** | §7.1 / §7.2 | 付费 API 路径仍通过 `TranslationEngine` 的分裂重试放大请求数，违反「每批一次请求」「防止重试倍增付费开销」。 |
| 2 | **BLOCKER** | §3.4 / §9.2 / §9.4 | checkpoint 兼容键模型内部矛盾（扁平清单 vs. force-resume 分层），并悄然改变现有软键续跑契约。 |
| 3 | IMPROVEMENT | §5.2 / §9 | `flash`/`pro` profile 跨越两个模型代际（Antigravity 3.5/3.1 vs. API 2.5）；同一本书内混用代际是未声明的翻译质量权衡。 |
| 4 | IMPROVEMENT | §6.2 / §10 / §16 | 既有模型解析子系统（`ModelResolver`、`ModelProbe`）及其配置键（`model_aliases`、`fallback_chain`、`enable_fallback`、`model_probe`）的处置未定义。 |
| 5 | IMPROVEMENT | §3.4 | 问题陈述夸大了现状限制——今天通过 `--force-resume` 已经可以跨 provider 续跑。 |
| 6 | IMPROVEMENT | §9.3 | schema v2 的 JSON 示例与真实的双文件 checkpoint 布局不符，且运行级与段级 provenance 的一致性未说明。 |
| 7 | IMPROVEMENT | §5.3 / §10 | 移除的 fallback 标志要「给出迁移提示而非被忽略/重解释」，但需在 shell 与 Python 两层实现；当前设计下用户会看到 argparse 的 `unrecognized arguments` 而非友好提示。 |

### 评审门建议：**Request changes（要求修改）**

在 BLOCKER 1 与 BLOCKER 2 于文档中解决之前，不要将 SPEC-020 晋级为 `🟡 待实施`。发现 3–7 应在同一次修订中处理，但属于澄清而非正确性缺陷。

---

## 详细发现

### BLOCKER 1 — §7.2 的付费 API 成本保证在所述架构下无法被强制执行

§7.1 将 *协议错误（缺分隔符、段数不符）* 归入「在符合条件处使用既有的有界分裂策略」，§7.2 又声明「Gemini API 默认每批一次请求尝试」，且该重试策略「保护订阅额度与付费 API 开销免于重试倍增」。

对 `api` 后端而言这两句自相矛盾，因为分裂策略位于 **engine 而非 adapter**，且 engine 会包裹传入的任意 adapter：

- `TranslationEngine` 用所选后端的 provider adapter 构造——`--provider api` 时该 adapter 是 `GeminiAPIAdapter`（`ai/cli.py:1014`、`ai/cli.py:1107`；`create_provider` 在 `ai/cli.py:716-721` 返回 `GeminiAPIAdapter`）。
- 遇到协议 / 段数错误时，API adapter 抛出 `TranslationError`（`ai/adapters/providers/gemini_api_adapter.py:72`；触发它的段数/ID 校验在 `ai/adapters/providers/_delimiter.py:132-146`）。
- `TranslationEngine._translate_with_resilience` 捕获 `TranslationError`，将批次对半分裂，并对每一半**递归重试**，直到 `max_split_depth`——默认 **10**（`ai/core/engine.py:243-251`，默认值 `ai/core/engine.py:37`）。
- 每个被重试的半批都是一次新的 `GeminiAPIProvider` 调用，即一次新的计费请求。

因此一个已授权的 API 批次若遭遇协议错误，可扇出为大量付费请求——恰恰是 §7.2 声称要防止的「重试倍增」。只要付费 adapter 仍位于同一条分裂重试的 engine 路径上，「每批一次请求」就无法实现。

**建议：** 在 §7 明确规定 `api` 后端**禁用分裂重试（或硬性上限为深度 0–1）**，并针对 API provider 显式调和 §7.1（协议→分裂）与 §7.2（每批一次、不倍增）：例如协议分裂重试仅为 CLI 的能力，付费路径遇错即让该批失败并停机、保留 checkpoint。否则该 SPEC 最核心的成本安全承诺无法由当前 engine 设计兑现。

---

### BLOCKER 2 — §9.2/§9.4 的 checkpoint 兼容键模型内部矛盾，并悄然重定义当前续跑契约

本 SPEC 的 schema v2 迁移以兼容键模型为核心，但该模型的表述前后不一致，也没有描述相对现状的差异。

**(a) §9.2 与 §9.4 对「层数」不一致。** §9.2 给出一个扁平的 7 项「兼容键」清单（输入签名、输入格式、分段器签名、目标语言、逻辑 profile、系统提示/术语表哈希、批协议版本），它们共同「决定翻译是否可安全复用」。但 §9.4 说 `--force-resume`「可覆盖 profile、prompt 或批设置差异，但不能覆盖输入签名、输入格式、分段器签名差异」。这意味着实际有**三层**——绝对硬（输入/格式/分段器）、可被 force-resume 覆盖（profile/prompt/批设置）、纯审计（§9.2 的第二个清单）——然而 §9.2 把前两层合并成一个不加区分的集合。实现者仅凭 §9.2 无法推导出正确的失效逻辑。

**(b) SPEC 悄悄改变了今天的行为。** 当前实现已采用两层：

- 硬键 → 从头开始：输入签名、输入格式、分段器签名（`ai/cli.py:371-382`）。
- 软键 → 警告并要求 `--force-resume`：`output_lang`、`model`、`provider`、`max_batch_chars`、`separator_overhead`、`system_prompt_hash`（`ai/cli.py:384-404`）。

SPEC-020 把 `目标语言` 和 `系统提示哈希` 上移进「兼容键」，把 `model`/`provider` 下移为纯审计，却从未说明由此产生的契约变化：(1) 目标语言或 prompt 不一致将从「软（可覆盖）」变为「硬」；(2) model/provider 不一致将**不再要求 `--force-resume`**。这些恰恰是 Phase 4 必须实现的续跑行为，含糊其辞会导致迁移实现错误。

**建议：** 用一个显式的三层表（绝对硬 / 可 force-resume 覆盖 / 纯审计）替换 §9.2 的扁平清单，使 §9.4 与之一致，并补一小节「相对 schema v1 的行为变化」，说明目标语言/prompt 变为非审计键、model/provider 不再门控续跑。交叉引用 `ai/cli.py:371-404`，让实现者清楚哪些现有校验换了层。

---

### IMPROVEMENT 3 — `flash`/`pro` profile 跨越两个模型代际；同书混用是未声明的质量权衡

§5.2 将 `flash` 映射为 Antigravity `Gemini 3.5 Flash (Low)` **与** Gemini API `gemini-2.5-flash`，`pro` 映射为 `Gemini 3.1 Pro (Low)` **与** `gemini-2.5-pro`。每个 profile 内部两个后端是**不同模型代际**（3.5/3.1 vs. 2.5）。§9 的跨 provider 续跑刻意复用先前翻译好的段落，理由是「逻辑翻译 profile……未变」，而 §9.3 展示的 checkpoint 同一本书里同时含 `antigravity` 段与 `gemini_api` 段。

对长篇散文而言，两个不同代际的模型通常产出不同的译文声腔、语域与术语。因此续跑后的书稿可能交错出现 3.5-Flash 与 2.5-flash 的译文——对图书翻译是读者可感知的真实质量风险，而 §14 的风险表并未提及。

**建议：** 要么在 §9 用一句话明确「接受同书内跨代际输出，作为成本/连续性的有意权衡」，要么补一条缓解措施（例如续跑后端代际与磁盘上已有段落不同时给出提示）。设计取舍本身可能没问题，缺的是明示。

---

### IMPROVEMENT 4 — 既有模型解析子系统及其配置键的处置未定义

§6.2 引入新的「类型化模型 profile 注册表」，§5.2 称非法模型「在参数或模型解析阶段被拒绝」。但 SPEC 从未说明现有解析栈的去留：

- `ModelResolver` 及其配置驱动的 `model_aliases`、`fallback_chain`、`enable_fallback`（`ai/model_resolver.py:49-53`、`:58`、`:81-87`）。
- `ModelProbe`，被 `ModelResolver.resolve()` 用于可用性探测（`ai/model_resolver.py:171-175`；探针接线在 `ai/model_resolver.py:93-106`）。

§10 只说「移除 `ai/model_probe.py` 中 Gemini 特有的 CLI 探测」——但 `ModelResolver` 依赖 `ModelProbe`，且 §16 仍列出 `ai/model_resolver.py` 而未给出处置。需要 SPEC 明确回答：

1. `ModelResolver` 是被 profile 注册表**取代**，还是保留并改造？若移除 `ModelProbe` 的 CLI 探测，`resolve()` 的探针分支会失效。
2. 对含 `model_aliases`/`fallback_chain`/`enable_fallback`/`model_probe` 的既有 `config.json`，这些键现在是**报错、警告，还是被静默忽略**？由于 `model_aliases` 条目可能重新引入 `lite` 或任意模型，其处理属于 §5.2 安全契约的一部分，而非无关紧要的细节。

**建议：** 在 §6 或 §10 增补一节，定义 `ai/model_resolver.py`、`ai/model_probe.py` 及每个受影响配置键的处置，并增加一条验收标准：含已移除键的旧配置应报错或警告，而不是静默弱化白名单。

---

### IMPROVEMENT 5 — §3.4 夸大了当前的 checkpoint 限制

§3.4 称当前 schema「将具体的 provider 与 model 值当作兼容键」，并说这「阻止了从 Antigravity `flash` 到 Gemini API `flash` 的安全、经用户授权的续跑」。

事实上今天 `model` 与 `provider` 是**软键**：不一致会打印警告，并可用 `--force-resume` 覆盖，覆盖后先前的翻译**确实会**被复用（`ai/cli.py:387-388`、`:397-404`、`:416`）。因此跨 provider 续跑今天已经可行，只是被 `--force-resume` 门控。准确且更有力的问题陈述应是：(a) `model` 以**具体字符串**存储，因此跨后端没有逻辑 profile 层面的相等判定；(b) `--force-resume` **过于粗粒度**——它会同时覆盖 prompt、分段、批设置差异，用户无法只授权「仅一次 provider 变更」。

**建议：** 重写 §3.4，说明该能力已存在但粗粒度且基于具体字符串，从而让 schema v2 的立论建立在真实缺口而非被夸大的限制之上。

---

### IMPROVEMENT 6 — §9.3 的 schema v2 示例与真实双文件布局不符，运行级/段级 provenance 一致性未说明

当前 checkpoint 是**两个文件**：`state.json`（运行级元数据，含 `model` 与 `provider`）与 `translations.json`（`{schema_version, segments}`）——见 `ai/cli.py:86-87` 与 `ai/cli.py:319-337`。§9.3 的示例展示的是一个把 `schema_version` 与段级 provenance 混在一起的单一对象；它映射到 `translations.json`，却忽略了 `state.json`——而 §9.2 的兼容键恰恰存放并被续跑校验读取于此（`ai/cli.py:319-331`、`:362-395`）。

新增段级 `provider`/`backend`/`model` 还引入了 SPEC 未解决的一致性问题：这些段级 provenance 值与 `state.json` 里驱动兼容性校验的运行级 `model`/`provider` 是什么关系？在跨 provider 续跑下它们会合理地不同。

**建议：** 同时给出**两个文件**的 v2 布局，并说明兼容键与 provenance 记录分别落在哪个文件，以免 Phase 4 把两文件合并，或与运行级字段重复/冲突。

---

### IMPROVEMENT 7 —（新增）§5.3 移除标志的迁移失败提示需在 shell 与 Python 两层落地

§5.3 要求被移除的 `--cli-api-fallback` 与 `--fallback-provider api`「不得被忽略或重新解释」，并要「以迁移提示失败」。但当前调用链是双层的：

- `translatebook.sh` 自己解析 `--fallback-provider`（`translatebook.sh:434`）、做**自有校验**（`translatebook.sh:512-521`，如「`--fallback-provider` 仅在 `--provider cli` 时支持」），随后将其翻译为 `--cli-api-fallback` 转发给 Python（`translatebook.sh:762-763`、`:961-962`）。
- Python 的 `ai.cli` 用 argparse 解析 `--cli-api-fallback`（`ai/cli.py:469`）。

若仅移除 Python 侧的参数定义：shell 仍会在 762/961 转发 `--cli-api-fallback`，argparse 将报 `unrecognized arguments: --cli-api-fallback`——这是丑陋的报错，而非 §5.3 要求的友好迁移提示。更进一步，shell 的 512-521 校验会**先于**任何迁移提示运行，恰恰构成 §5.3 禁止的「重新解释」。

**建议：** 明确要求两层协同：Python 侧**保留**这两个参数名（用自定义 argparse action）以输出统一的迁移提示，而非删除导致 `unrecognized arguments`；shell 侧在其现有 `--fallback-provider` 校验/转发**之前**拦截并打印同样的迁移提示。§10 目前只笼统说「更新 translatebook.sh 的帮助与转发」，应把「双层一致的迁移失败消息」列为显式验收点。

---

## 次要观察（不阻塞，建议一并澄清）

- **移除/清理范围界定不全。** §10 声称清理过时的 Gemini CLI 代码，但未提及以下同样受影响或已过时的组件：`ai/epub_translate_roundtrip.py` 仍带 `cli_api_fallback_enabled` 接线（`ai/epub_translate_roundtrip.py:671,708`，CLAUDE.md 标注其为遗留/仅供参考）；`ai/quota_tracker.py`（注释自述「尚未接入主流程」，主树无引用）；`ai/model_selector.py` + 配置 `model_thresholds`（当前 EPUB 主流程不引用，仅服务于 `.worktrees` 里的遗留 markdown 工作流 `03_translate_md.py`）。建议 §10 对这些模块给出「清理 / 明确排除范围」的一句话表态，避免范围含糊。
- **`agy models` 探测时机。** §6.3 规定「每次 BookWeaver 调用运行一次 `agy models`」。应澄清两种情形是否仍强制探测：`--provider api` 运行（根本不用 Antigravity），以及从 checkpoint **全量恢复、无待翻译批次**的 no-op 运行——后者若因 Antigravity 登录过期而 `agy models` 失败，会阻塞一次本不需要任何 Antigravity 调用的成品输出。建议把该探测限定在「将实际调用 Antigravity 的 cli 运行且存在待翻译工作」时。
- **跨文件持久化非原子。** `_persist_checkpoint` 分两次 `_write_json`（各自 atomic replace）写 `state.json` 与 `translations.json`（`ai/cli.py:336-337`）。两次写之间被杀会造成两文件短暂不一致；schema v2 增加段级 provenance 后该窗口依旧存在。影响有限（续跑主要读 `translations.json`），但值得在 §9 明示可接受或给出缓解。
- **§9.4 的 `lite` 复用与 §4 的立论有张力。** §4 拒绝「把 `lite` 映射到 Antigravity Flash Low」，理由是会「制造虚假模型身份与误导性 checkpoint」；而 §9.4 允许用 `--force-resume` 把 `gemini-2.5-flash-lite` 的旧数据当作 `flash` profile 复用——本质是把 lite 译文并入 flash。因需显式 `--force-resume`，属知情覆盖、可接受，但建议 §9.4 用一句话点明这是与 §4 一致的「仅在用户显式强制时允许的例外」。

---

## 已核实为准确的声明（Notes）

以下 SPEC 声明已对照代码核实，属实：

- 默认模型是具体的 `gemini-2.5-flash`（`ai/cli.py:436`）；SPEC 改为逻辑 `flash` 是真实且有意的默认变更。
- `--cli-api-fallback` 与 `--fallback-provider api` 确实存在并接线了自动付费 fallback（`ai/cli.py:469`、`_CLIAPIFallbackAdapter` 于 `ai/cli.py:625-676`；`translatebook.sh:434,763,962`）。§10 的移除范围有据。
- `GeminiProvider` 经 stdin 调用 `gemini --model <model> -p`（`ai/gemini_provider.py:62-63`）。
- 段 ID 采用 SPEC 假设的 `"<doc_path>::<index>"` 形式，如 `EPUB/chapter01.xhtml::0`（`ai/adapters/sources/epub_adapter.py:153`）。
- checkpoint 写入为原子的临时文件替换（`ai/cli.py:305-310`）；`--resume`/`--force-resume` 已存在（`ai/cli.py:489`、`:501`）。
- `00_extract_glossary.py` 直接构造 provider、绕过 `ProviderFactory`（`00_extract_glossary.py:109-118`）——§6.5「统一走组合根」有其必要。
- 分隔符/分段封装 helper 已被共享（`ai/adapters/providers/_delimiter.py`，被 `gemini_api_adapter.py:18-23` 引用）——§6.4「既有 helper 保持共享」正确。
- 当前 schema 版本为 `1`（`ai/cli.py:84`），与 v1→v2 迁移的叙述一致。

---

## 与上一版评审的关系（Prior Review Status）

SPEC 文件自 `v1` 起未修改，故 v1 的 6 项发现全部仍为**未解决**并已在上文完整重列；本版 v2 追加了 IMPROVEMENT 7 及若干次要观察。无「已解决」项。
