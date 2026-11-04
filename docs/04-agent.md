# Agent architecture and tools

[← Back to README](../README.md)

## Agent architecture

```
              ┌────────────────────────────── ChatSession (one per conversation) ──────────────────────────┐
 customer ──▶ │  START → input_guard → agent ──(tools requested?)──▶ tools ──┐                              │
              │                          ▲                                   │                              │
              │                          └───────────────────────────────────┘                              │
              │                          │ final reply → ticket and price verification ──▶ customer          │
              └─────────────────────────────────────────────────────────────────────────────────────────────┘
   shared: model (OpenRouter) · SQLite repository · policy retrieval · checkpointer
```

**Framework: LangGraph, with a hand-built graph.** The loop follows the ReAct pattern: the model
reasons, calls tools, observes the results and repeats until it answers. I did not use
LangGraph's prebuilt agent because the input and output guardrails and the human handoff needed to
be explicit graph nodes. LangGraph also provides the per-conversation history checkpointer.

**Prompt strategy** ([`agent/prompts.py`](../src/emporio/agent/prompts.py)):

- **"Lia" persona**, with the tone of voice from the manual (7.1): informal but professional,
  short WhatsApp-style messages, at most one emoji.
- **What goes into the prompt and what does not.** Stable facts (address, contacts, hours) are in
  the prompt, taken from the canonical source that already resolves the manual's contradictions.
  Volatile facts (prices, stock, orders, deadlines) **never** are: the prompt requires the tools
  and forbids estimating or recalculating values.
- **Date, time and store status are injected every turn,** so "we are closed now, we open
  tomorrow at 9am" needs no tool call, and deadlines are consistent with the clock.
- **Tool map.** The prompt says which tool to use for each kind of question, and each tool's
  description reinforces it.
- **Security.** Customer messages and tool results are treated as data. The agent does not change
  role, does not reveal the prompt, does not create discounts and does not discuss orders without
  identity verification.

**Persistent history** ([`agent/memory.py`](../src/emporio/agent/memory.py)). Each conversation is
saved in SQLite by LangGraph's checkpointer, and the customer can resume it later. Persisting
makes sense for the experience: someone coming back with "what was my ticket number?" or "what
about that guitar you recommended?" does not have to repeat everything. Since the history
contains personal data, it is kept out of the repository (`var/`), and the conversation can be
deleted, honoring the LGPD right to erasure (manual, section 9).

**Human handoff** ([`handoff.py`](../src/emporio/handoff.py)). Complaints, defects, cancellations
and requests to talk to a person are recorded with a summary for the team, so they do not need
to reread the conversation. The team follows them with `uv run emporio-handoffs` or the
"Atendimentos" page. In a real store, this would be replaced by an integration with the CRM or
WhatsApp Business.

**Prompt caching.** The system prompt is split into a **static** part (persona, rules and store
facts) and a **dynamic** part at the end (date and time, store status, guardrail notes). The
static part carries `cache_control`, so it and the tool definitions that precede it can be
reused from the provider's cache on every message, reducing cost and latency. Before this split,
the date sat at the top of the prompt and would have invalidated the cache on every message. It
is enabled only for OpenRouter (where it was validated) and can be turned off with
`LLM_PROMPT_CACHE=false`. Measuring the actual gain (tokens read from cache) is pending: the
OpenRouter workspace's daily spending limit was reached before it.

**Robustness:**

- **One `ChatSession` per conversation,** with its own tool context. The limit of 3 identity
  verification attempts is per conversation, not global.
- **History window** of the last 40 messages. The cut always starts at a customer message, so a
  tool call is never separated from its result, which providers reject.
- **Iteration limit:** at most ~7 tool rounds per message. If exceeded, the agent hands over to
  the team instead of looping.
- **Provider failures** (network, credit, outage) become a friendly message with the store's
  contact, and the conversation keeps working on the next message. Tests simulate these cases
  with a scripted model, without network.

## Agent tools

The tools live in [`src/emporio/tools/`](../src/emporio/tools/). Each one is a **pure Python
function** that receives a context (repository + clock) and returns a Pydantic model, so all of
them are tested without an LLM. The [registry](../src/emporio/tools/registry.py) exposes them as
LangChain `StructuredTool`s, with descriptions that tell the model **when** to use each one.

| Tool | Typical question | What it guarantees |
|---|---|---|
| `search_products` | "Which guitars under R$ 1000?" | Structured filters; only sellable items by default; redirects accessory requests; warns when a category is empty |
| `get_product_details` | "How much is the Takamine GD20?" | List price, promotion (with percentage) and PIX price; alternatives if out of stock or discontinued; asks for clarification on ambiguous names ("Martin D28" → D-28 or D-28E?) |
| `list_categories`, `list_promotions` | "What do you sell?", "Any promotions?" | Only active promotions, already applying the no-stacking rule with PIX |
| `get_order_status` | "Where is my order 8?" | Requires order + e-mail or phone; warns about late deliveries; locks after 3 wrong attempts in the conversation |
| `check_return_eligibility` | "I regret it, can I return it?" | Computes deadlines (7-day withdrawal, 30-day defect exchange, 90-day legal warranty) and says which date it used; suggests human handoff when the order cannot be verified on a defect report |
| `payment_options` | "In how many installments can I pay?" | Minimum installment tiers; PIX discount only on non-promotional items; split payment above R$ 2,000 |
| `shipping_quote` | "Do you deliver to Dourados?" | Price only when it can be computed (Campo Grande); warns about special freight for large items |
| `search_policies` | "What is the return deadline?" | Manual excerpts with section numbers, plus the official interpretation when a passage is ambiguous (see [Policy retrieval](05-rag.md)) |
| `escalate_to_human` | "My guitar arrived cracked", "I want to talk to a person" | Records the case for the team with a summary and contact; returns a ticket (`ATD-00001`) and a response time based on opening hours (complaints: 24 business hours); does not duplicate open cases |
| `store_status` | "Are you open?" | Hours in Campo Grande's time zone, holidays (including movable ones), next opening, address and contacts |

Design decisions:

- **Preformatted values.** Tools return "R$ 2.199,00" and "24/02/2026", and installments already
  computed. The LLM only repeats them: arithmetic and formatting done by the model are a classic
  source of hallucination, and the manual (7.1) forbids giving prices without checking the system.
- **Notes for the model.** Each result carries `notes` with the applicable policy guidance, such
  as "does not stack with PIX", "do not say whether the order exists" or "offer alternatives".
  The rule arrives when it is relevant, instead of relying only on the system prompt.
- **Errors become messages.** Invalid arguments or internal failures return text so the model can
  recover, instead of crashing the conversation. Every error is converted into a
  `ToolException`, because LangChain only handles that type and would let others propagate.
- **Injectable clock** (`EMPORIO_NOW`). The orders in the data are from 2025–2026; pinning the
  date makes demos and deadline tests reproducible.
- **Holidays.** National holidays (including Good Friday, computed from Easter), the Mato Grosso
  do Sul state holiday (Oct 11) and Campo Grande's municipal holiday (Aug 26).
