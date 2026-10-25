# Assign Provider Execution Policy Ownership

Type: grilling
Status: open
Triage: ready-for-human
Blocked by: 01

## Question

Which module should own model-profile resolution, Antigravity availability checks, typed provider outcomes, retry budgets, and paid API authorization so that the core translation engine stays provider-agnostic while cost and failure guarantees remain enforceable?

The decision must account for SDK-level, raw-provider, adapter, and engine retry layers, and must ensure `agy models` runs only when Antigravity will actually receive pending work.

## Comments
