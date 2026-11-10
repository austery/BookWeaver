# Term Panel live acceptance (2026-11-10)

**Result:** `bookweaver terms` (SPEC-028 Phase 2a) ran on two whole books with the `three-vendor` panel, and Gemini Flash translated both with the panel glossaries. Every fixed term was used throughout both books; the only reported misses are inflected uses. The owner read *A Philosophy of Software Design* and judged the terms more stable than before, with Gemini Flash's translation good enough. The owner kept the term limit at 100.

## Setup

- Code: `main` at `205c69f` (PR 97).
- Panel `three-vendor`: nominators `agy-flash-low`, `codex-gpt-6.1-sol-low`, `claude-opus-5-5-low`; judges `codex-gpt-6.1-sol-low`, `claude-opus-5-5-low`. Low effort, subscription only, no paid call.
- Term limit 100, from the owner's `terminology_extraction.max_terms`; each nominator was asked for up to 100 terms.
- *A Philosophy of Software Design* ran through `run_term_panel` with the panel added to the configuration in memory, because the owner's configuration did not hold it yet. The owner then asked for the panel to be added to `config/config.json`, and *Political Thinking* ran through the `bookweaver terms` command with that file.
- Translation: `agy-flash-low` with `--glossary`, each into a new folder; no old checkpoint was resumed.

## Term Panel runs

| | *A Philosophy of Software Design* | *Political Thinking* |
|---|---|---|
| Time, calls | 6.5 minutes, 5 calls | 8.5 minutes, 5 calls |
| Candidates | 107 | 143 |
| Nominated by 3 / 2 / 1 vendors | 38 / 35 / 27 | not tallied |
| Merged by `duplicate_of` | 7 | 11 |
| Dropped by vote | 9 | 4 |
| Cut by the limit | 0 | 28 |
| Fixed / preferred | 17 / 74 | 33 / 67 |
| Tie-break judge | anthropic (openai self-preference 0.012) | openai (anthropic unmeasured: 7 own-only candidates) |

- Fixed terms were the books' coined concepts, names and titles, as the narrow `enforce` definition intends: for example 深模块, 变更放大, 透传方法, 时序分解, 战术式编程; 公意, 救赎政治, 人道的不确定性, 定言命令, 色拉叙马霍斯, and book titles.
- Judges disagreed on 14 translations for *Software Design*, mostly spacing (`URL 编码` against `URL编码`) or whether to keep English (`getter方法` against `取值方法`).
- `duplicate_of` worked in its first live use, for example the two Robert Martin and David Parnas entries.
- One nomination had a slash (`selection/cursor`); the extraction warning named it.
- The 28 terms cut in *Political Thinking* were all preferred and nominated by fewer vendors, such as Totalitarianism, Transcendence, Private property, State of nature and Liberalism. The owner kept the limit at 100: Flash translates such general concepts correctly without help.

## Translations

| | *A Philosophy of Software Design* | *Political Thinking* |
|---|---|---|
| Segments, time | 1,775 segments, 374,124 source characters, 14 minutes | 1,744 segments, 24 minutes |
| Fixed terms used | 17 of 17 seen; 1 reported miss | 33 of 33 seen; 1 reported miss |
| Preferred terms that varied | 11 | 7 |

- **Reported misses are not drift.** *Software Design*: "a clean code base" is not the book *Clean Code*, and a bibliography footnote kept the English title. *Political Thinking*: 符合强者利益 is 强者的利益 inflected.
- **Preferred variation is mostly context.** *interface* is 接口 in 144 of 158 segments; *Being* is 存在 in 63 of 131, because *being* is usually an ordinary verb.

## Against earlier translations

These comparisons change both the glossary and, for *Software Design*, the translator, so they show stability, not a cause.

- ***Software Design* against the Terra translation** (`codex-gpt-6.1-terra-low`, its own 50-term glossary): the 17 panel fixed terms were consistent in both versions under each version's glossary. Judges changed three renderings: 类膨胀症 → 类泛滥症, 按时间顺序分解 → 时序分解, 战略性编程 → 战略式编程. The panel glossary has 91 terms instead of 50.
- ***Political Thinking* against the 2026-11-09 full-book retest** (Gemini Flash, its own 50-term glossary): 18 of the 33 panel fixed terms were in the old glossary, two with another rendering (绝对命令 → 定言命令, 苏格拉底式的谦和审慎 → 苏格拉底式的谦和). Names the old glossary lacked drifted in the old translation and are now fixed: Martin Buber 2 of 4 segments → all, Simone Weil 1 of 2 → all, Gelasius I 0 of 2 → all, *The Discourses* 0 of 1 → all.
- **Against the offline replay** (SPEC-028 §2): this run had three nominators asking for 100 terms, not five lists of 50, so candidates differ. Shared outcomes: Humane Uncertainty 人道的不确定性, Democratic totalitarianism 民主极权主义, Transcendentalism 超验主义. Cosmic morale became 宇宙信心 (preferred, alternative 宇宙士气). Uniformity was not nominated this time.

## Not proven

- One run per book and panel; run-to-run variation of a panel is unmeasured.
- The owner read *Software Design*; *Political Thinking* has not been read yet.
- Deep Scan with a panel, paid members, `--term-panel` and `runtimes.disabled` are later phases.

## Files (owner machine)

- `~/Documents/BookWeaver/A Philosophy of Software Design (John K. Ousterhout) (z-library.sk, 1lib.sk, z-lib.sk)/panel-three-vendor/`: `terms.log`, `translate.log`, the translation, and `.bookweaver_glossaries/panel/<identity>/` with `glossary.json`, `term-panel-report.json` and `replies/`.
- `~/Documents/BookWeaver/Political Thinking - panel three-vendor/`: the same layout.
