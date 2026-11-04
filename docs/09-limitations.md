# Known limitations

[← Back to README](../README.md)

- **Pattern-based guardrails.** Manipulation detection uses regular expressions in Portuguese and
  English. More elaborate attacks (hidden instructions, other languages, paraphrases) may get
  through; in that case the prompt's rules and the output checks are what hold. Price
  verification only covers amounts written with "R$".
- **Verification attempt limit per process.** The counter of wrong identification attempts is
  per conversation, but kept in memory: if the conversation is resumed in another process, it
  resets. In a production API it would live in the persisted conversation state.
- **Brand validation by dictionary.** Detecting conflicting descriptions relies on a list of
  known brands and models. A new brand in the catalog must be added to `BRANDS` in `products.py`.
- **Rule-based product search.** Synonyms ("acústico" vs. "folk", "elétrico" vs.
  "eletroacústico") are not handled. With a larger catalog, a hybrid search (BM25 + embeddings)
  would be worthwhile.
- **Actual delivery date.** The data only has the estimated delivery date; return deadlines use
  the date given by the customer or that estimate.
- **Municipal holidays of other cities and optional holidays** (Carnival, Corpus Christi) are not
  considered in the store's hours.
- **Small evaluation sets** (28 + 22 questions, written by me). They are useful to compare
  strategies and catch regressions, but differences of a few percentage points are not
  statistically robust.
- **Promotions without dates.** With no validity dates, `is_active` is the only source of truth.
- **Discrepancies not resolved at the source.** The phone number, product 130's status and the
  totals of orders 3 and 20 would need to be confirmed with the store.

## What I would do with more time

- **More robust evaluation:** run each scenario several times and report pass rates, create a
  separate validation set of agent scenarios, and use real customer questions (for example, from
  the store's WhatsApp).
- **Finish the model comparison:** check Gemini 2.5 Flash with a judge from another family and
  include larger models (Claude Sonnet). If Flash's advantage holds, switch the preset's model,
  with no code changes.
- **Measure prompt caching** (tokens read from cache and savings per conversation).
- **Integrate real channels:** connect the API to WhatsApp Business and the human handoff to the
  store's CRM or helpdesk.
- **Human review of the data:** turn the data quality report into a queue of items for the team to
  confirm (conflicting phone number, product statuses, order totals).
- **Fully persisted state:** keep the identity verification attempt limit in the conversation
  history.
- **Semantic product search,** if the catalog grows well beyond the current 65 items.
