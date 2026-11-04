# Agent evaluation

[← Back to README](../README.md)

```bash
uv run emporio-eval-agent                     # deterministic checks only (~US$ 0.30)
uv run emporio-eval-agent --judge --judge-model google/gemini-2.5-pro   # + LLM judge
uv run emporio-eval-agent --calibrate-judge   # measures the judge itself
uv run emporio-eval-agent --model <other>     # compares another model for the agent
```

There are [28 test conversations](../evals/agent_scenarios.yaml) in 13 categories: the 4 scenarios
from the case, catalog, prices and promotions, payment, shipping, orders, returns, policies,
opening hours, human handoff, multi-turn, out of scope and security. Evaluation has two layers:

1. **Deterministic checks per turn.** Tools that must or must not be called, and required or
   forbidden text in the reply (e.g. "R$ 2.199,00" yes; the conflicting WhatsApp number, no;
   nothing about the order when the e-mail does not match). They catch objective errors with no
   subjectivity.
2. **LLM judge (LLM-as-judge).** Scores from 1 to 5 for tone, policy adherence and helpfulness,
   using the scenario's goal and the tool data as reference. I used a model from **another
   family** (Gemini) to judge the agent (Claude), reducing the bias of a model favoring its own
   answers.

**Final result** ([full report](../evals/results/agent_eval.md)), with the agent on
`anthropic/claude-haiku-4.5` (through the preset) and `google/gemini-2.5-pro` as judge:

| Metric | Result |
|---|---|
| Deterministic checks | 28/28 scenarios (100%) |
| Tool selection (per turn) | 100% |
| Judge: tone / policy / helpfulness (mean, 1-5) | 5.0 / 4.93 / 4.96 |
| Scenarios passed (checks + all scores ≥ 4) | 27/28 (96%) |
| Mean latency per turn | 3.4 s |
| Cost of a full run (31 turns) | ~US$ 0.32 |

**How we got here: what the evaluation revealed.**

- **First run (26/28 on the checks).** One failure was real: for "do you deliver to Dourados?",
  the agent asked which product instead of answering, because the shipping tool's description did
  not make clear that only the city is required. The other was my scenario's fault: the
  "customer" asked to register a complaint without saying what happened, and asking for details
  was the right behavior. I adjusted the scenario and record it here.
- **The judge must be evaluated too.** In its first version, it failed 12 correct scenarios: it
  read "never give a price that does not come from the system" as "never give a price". I built a
  [calibration set](../evals/judge_calibration.yaml) of 12 replies with known verdicts (invented
  price, PIX discount stacked on a promotion, order data leak, promised discount, invented
  deadline, robotic tone, and good replies) and rewrote its prompt until it got them all right.
  Both judges tested score 12/12 (`gemini-2.5-flash` and `gemini-2.5-pro`).
- **My mistakes in the judge's context.** The store's address was missing from the store facts,
  tool data was truncated (suggested alternatives were cut off), and the judge did not know the
  conversation date (it thought "tomorrow, Saturday 04/04" was invented).
- **Real agent issues found by the evaluation and fixed:**
  - give the status of a late order first, instead of escalating straight away without asking;
  - do not offer "pre-orders", which the store does not do (the idea came from a note in my own
    tool);
  - do not suggest a nylon classical guitar as an alternative to a steel-string one (alternatives
    now prioritize the same string type and electronics);
  - warn about special freight for large items outside Campo Grande;
  - the card warning was "satisfied" by any mention of the word "cartão" (e.g. "pay with PIX,
    card or boleto"); it now requires an explicit instruction.

## Model comparison

Since the model is swappable by configuration, the same evaluation was run with other OpenRouter
models that support tools under the workspace's zero-data-retention policy. The judge is the same
for all (`google/gemini-2.5-pro`, calibrated). Reports in
[`evals/results/models/`](../evals/results/models/).

| Agent model | Passed | Deterministic checks | Tone / policy / helpfulness | Mean latency | Cost (28 scenarios) |
|---|---:|---:|---|---:|---:|
| `anthropic/claude-haiku-4.5` (current preset) | 27/28 | 28/28 | 5.0 / 4.93 / 4.96 | 3.6 s | US$ 0.326 |
| `google/gemini-2.5-flash` | **28/28** | 28/28 | 5.0 / 5.0 / 4.89 | **2.3 s** | **US$ 0.029** |
| `openai/gpt-oss-120b` (open weights) | 26/28 | 26/28 | 4.96 / 4.79 / 4.79 | 9.2 s | US$ 0.005 |

**Reading.**

- **Gemini 2.5 Flash** matched or beat Haiku at **11 times lower cost** and lower latency. Its
  replies are shorter (helpfulness 4.89), which suits the WhatsApp tone but gives less detail.
- **gpt-oss-120b** is cheap and open-weights (it could run on the store's own infrastructure),
  but it is slow and had two real failures: it wrote an amount in US format ("R$ 1,000"), which
  price verification blocked, and it omitted the carriers for Dourados.
- **Caveat:** the judge is from the same family as Gemini Flash and may favor it. The cross-check
  (re-judging Flash's recorded replies with a Claude judge, via `--rescore --judge`) and the
  `claude-sonnet-4.5` run are pending: the OpenRouter workspace's daily spending limit was reached
  during the comparison. That is why the preset stays on Haiku; if the cross-check confirms the
  result, switching to Flash only means changing the preset, with no code changes.

**Over-strict checks.** The comparison revealed false negatives in my expectations: "até 4 vezes"
did not match "4x", "abrimos amanhã" (on a Sunday) did not match "segunda", "só vendemos
instrumentos" did not match "acessório", and "3341‑4444" written with a Unicode hyphen (U+2011)
did not match a regular hyphen. I fixed the scenarios and the normalization, and re-scored the
recorded replies with `--rescore`, which reapplies the checks without calling the agent again.

**Run-to-run variation.** When running the same scenarios several times, the set of failures
changes (e.g. the remaining failure, omitting that the return deadline was counted from the
*estimated* delivery date, does not always happen). A single result should not be read as
definitive. With more time, I would run each scenario N times and report pass rates.

**Overfitting risk.** I fixed the agent by looking at failures on these same scenarios. Unlike
policy retrieval, there is no separate validation set here, which is why I stopped iterating on
the last failure instead of tuning until 100%. A next step would be writing new scenarios (or
using real conversations) to measure generalization.
