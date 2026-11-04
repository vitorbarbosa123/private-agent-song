# Use of AI coding assistants

[← Back to README](../README.md)

I used **Claude Code** (Anthropic), inside VS Code, as a pair programmer throughout the project.
The split of roles was: **I decided what to build and approved each step; the assistant
proposed, implemented, tested and explained**. The commit history, one commit per objective and
one branch per phase, reflects this workflow.

## Workflow

1. **File analysis and security.** Before any code, I asked for an analysis of the case and the
   data, including a scan for malicious content or hidden prompts (JavaScript and automatic
   actions in the PDFs, invisible text, hidden Unicode characters, prompt injection attempts in
   the CSVs). Nothing was found.
2. **Phased plan.** The assistant proposed an architecture and an implementation plan (data →
   tools → RAG → agent → memory → guardrails → evaluation → interfaces), and I adjusted the
   choices before each phase.
3. **Decisions I made that changed the course of the project:**
   - use **OpenRouter** with a *preset*, to configure models and fallbacks on the platform and
     let reviewers switch models easily;
   - run everything in **containers** and have a **chat interface** with history and a tool-call
     inspector;
   - use **Langfuse** for observability;
   - keep the zero-data-retention (ZDR) policy on OpenRouter, which led to switching the preset's
     model to one with ZDR-compliant, tool-capable endpoints.
4. **Implementation with tests.** Each phase was implemented by the assistant with automated tests
   (300+, with no model calls) and reviewed by me before committing.
5. **Live tests and evaluation as a source of fixes.** Many improvements came from running the
   agent for real and reading its replies: a ticket number invented by the model, an internal
   correction leaking to the customer, an ignored card warning, a card number appearing in
   Langfuse traces, an LLM judge failing correct replies. Each case became a root-cause fix and a
   regression test, documented in the corresponding section.
6. **My own manual tests.** Simulations I ran also led to fixes, such as a defect complaint with a
   non-existent order number, which did not offer human handoff before.

## What worked well and what needed attention

- **Worked well:** speed in implementing and testing alternatives (for example, comparing
  retrieval strategies and models with numbers), and the discipline of documenting every
  decision.
- **Needed attention:** the assistant also makes mistakes (wrong expected values in tests,
  configuration errors, over-strict evaluation checks). Reviewing real outputs and keeping
  separate validation sets is what caught them. It also took care not to tune the agent until it
  "passed" the same scenarios used to measure it.
