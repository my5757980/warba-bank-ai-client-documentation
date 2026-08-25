# Call Report — Grounding Pass (v1.0.0)

Versioned artifact. Every generated document records the prompt version that produced
it (FR-030), so this file must not be edited in place — publish a new version directory.

## Extraction scope

Extract every factual claim from the supplied meeting notes and client records that
bears on a client call report.

Extract:

- Who attended, on both sides, and in what capacity
- When and where the meeting took place, and through what channel
- What was discussed, in the order raised
- Any figure the client or the records state — amounts, limits, utilisation,
  percentages, tenors, ageing
- Products or structures the client referenced
- Any risk, concern, delay, dispute, or adverse signal
- Actions agreed, with their owner and any stated date

Do not extract:

- Conclusions about the client's creditworthiness
- Anything the notes imply but do not state
- Your own summary or interpretation of what the meeting "means"

## The rule that matters

If the notes do not state something, say nothing about it. A missing follow-up date is
not a claim that the follow-up is "to be confirmed" — it is an absence, and the
composition pass will mark it as a gap. Inventing a plausible bridge here is the single
most damaging thing you can do, because a claim in the ledger is treated downstream as
grounded fact.
