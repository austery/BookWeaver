# Claude Code request capture (2026-11-09)

**Result:** on Claude Code 2.1.311 with a fake API key, `--restricted` keeps the owner's `~/.claude/CLAUDE.md`, auto-memory, skills and plugins out of a `claude -p` request. The SPEC-025 §5 flag set is still not enough: it needs `--system-prompt`, an empty working directory, and a guard for a prompt that starts with `/`.

No request reached Anthropic. The real CLI ran against a local fake endpoint (`ANTHROPIC_BASE_URL=http://127.0.0.1:<port>`) with a fake `ANTHROPIC_API_KEY`, in a child environment built with `env -i`. The redirect was first proven with a temporary `CLAUDE_CONFIG_DIR`; later rows used the real `~/.claude`. No book text was sent.

## What each flag removes

"Fixed context" is every character of the request body except the prompt. Each run made one request, `POST /v1/messages?beta=true` with `stream: true`.

| Arguments | Fixed context, characters | Owner `CLAUDE.md` | Memory, skills, plugins | Tools |
|---|---|---|---|---|
| `-p` only, inside this repository | about 97,600 | Sent | Sent, with `AGENTS.md` and git status | 13 |
| `-p` only, in a temporary directory | about 87,700 | Sent | Skills and plugins sent | 13 |
| `-p --tools ""` | about 20,800 | **Sent** | Not found | 1 |
| `-p --restricted` | about 39,000 | Not sent | Not sent | 12 |
| `-p --safe-mode` | about 50,000 | Not sent | Not sent | 13 |
| SPEC-025 §5 flag set | about 5,700 | Not sent | Not sent | 0 |
| SPEC-025 §5 flag set + `--system-prompt` | about 1,900 | Not sent | Not sent | 0 |

- `--restricted` is the flag that removes the owner's rules. Its help text promises only that it ignores settings files, so this holds for 2.1.311 and needs a new capture after an upgrade.
- A canary `CLAUDE.md` in a private `CLAUDE_CONFIG_DIR` was sent under `-p` alone and was not sent under the §5 flag set. A canary `CLAUDE.md` in the working directory was also not sent under the §5 flag set, unless the prompt named it (see below).
- Without `--system-prompt`, about 4,200 characters of the coding-agent prompt travel with every request. Inside a git repository the request also carries the branch name and the five latest commits. `--system-prompt` removes both.
- What remains with `--system-prompt`: the line `You are a Claude agent, built on Anthropic's Claude Agent SDK.`, a billing header line, and one environment message of about 1,100 characters (working directory path, platform, OS version, date, model name).
- The body always carries `thinking: {"type": "adaptive"}` and `max_tokens: 128000`. `--effort low` arrives as `output_config.effort`.
- A 56,000-character prompt with CJK text, segment tags, `$VAR`, backslashes and emoji arrived on stdin byte for byte.
- With the final arguments nothing was written under `~/.claude/projects`.

## Risks found

1. **A prompt that starts with `/` is a local command.** The CLI sends no request and exits 0 with `is_error: false`, `num_turns: 0` and an empty or canned `result`. `--disable-slash-commands` does not prevent it, and neither does `--input-format stream-json`. A `/` line later in the prompt is harmless.
2. **`@path` in the prompt inlines a file from the working directory.** The file content enters the request as a system note, even with `--tools ""`. Paths outside the working directory were not inlined under `--restricted` (an absolute path and a `../` path were tested). Book text can contain `@name`, so the working directory must hold no files; the prompt travels on stdin.
3. **An API key in the environment beats the claude.ai login.** With the real `~/.claude`, every request carried `x-api-key` and no `authorization` header. The child environment must drop the key, or a subscription run becomes a metered one.
4. **`--tools` with a lost empty value swallows the next flag and still exits 0.** A shell that drops the empty string turned `--tools "" --no-session-persistence` into `--tools --no-session-persistence`: tools stayed empty, and the session file was written. `--tools=` gave the same request as `--tools ""` and cannot lose its value.
5. **The parent environment can change the child.** A shell started by Claude Code exports `ANTHROPIC_BASE_URL`, `CLAUDECODE`, `CLAUDE_CODE_SIMPLE` (the variable `--bare` sets) and other `CLAUDE_CODE_*` variables. The capture avoided them with `env -i`; the effect of inheriting them was not measured.

## Arguments for the provider

```
claude -p --restricted --strict-mcp-config --tools= --no-session-persistence \
  --output-format json --model <family> --effort <effort> --system-prompt <text>
```

The prompt goes on stdin, and the working directory is empty. `--output-format json` returns one object; the reply is `result`, with `is_error`, `num_turns`, `stop_reason` and `api_error_status` beside it.

## Not proven

- The request shape under the claude.ai login. That capture was not run, because it sends the real token through a redirect proven only for key authentication.
- That the subscription pool pays for `-p`. An owner-run probe is still required (SPEC-025 §5).
- Quota (429) and expired-login (401) behavior.
- Requests to other hosts, such as telemetry.
- Any translation output; the fake endpoint returned a fixed reply.
- Behavior on any version other than 2.1.311.

## Harness note

The first runs of the §5 flag set passed the flags through an unquoted zsh array, which dropped the empty `--tools` value (risk 4). Those rows are valid for the request content and were repeated with literal arguments; the repeated request had an identical system prompt. The six session files they left under `~/.claude/projects` held only the test sentence and were deleted. Raw captures are not in the repository, because the baseline rows contain the owner's private rules.
