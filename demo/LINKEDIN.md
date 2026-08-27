# LinkedIn post

Attach `demo/warba-client-documentation.mp4` (59s, 1280×720). LinkedIn autoplays muted,
so the video is captioned throughout and needs no sound.

---

## Post copy

I spent the last stretch building a submission for the **Warba Bank Corporate Banking AI
Challenge (Track 1 — AI-Powered Client Documentation)**, and the interesting part turned
out not to be the drafting.

A Relationship Manager can write a call report in an hour. What a bank cannot accept is a
fluent, confident, **wrong** number sitting inside it — or a conventional interest product
described as if it were Islamic. So the question I actually had to answer was not "can AI
write this faster." It was: **how do you make "it didn't hallucinate" something you can
check, rather than something you have to hope for?**

Four things, all of them enforced by code rather than by prompt:

**1 · Two-pass generation through an evidence ledger.**
The first pass extracts claims and verifies each one against the source. The second pass
writes the document from that ledger and *never sees the raw sources at all* — so it
cannot cite what isn't there. It's a structural guarantee, not an instruction.

**2 · If the model can't quote it, the system deletes it.**
The model supplies a verbatim quote; our own code then searches the real source text for
it. No fuzzy matching — a single altered digit fails. Unsupported claims never reach the
page. And every number in the finished document is traced back to a cited claim, or the
whole generation fails closed.

**3 · What the notes didn't say is marked MISSING, not invented.**
This is the part I'd point at first. Gaps appear in amber, in the document, and they
**block approval outright** — the button is disabled and every missing item is listed by
name. No override. No timer that quietly approves anything.

**4 · Shariah screening is a deterministic gate, not a prompt.**
A reviewable word list that compliance can audit without reading code. Non-compliant
terminology stops the draft *before it exists*, and every finding cites its rule ID.

Underneath: audit immutability enforced by database privilege (the application role holds
INSERT and SELECT only — UPDATE and DELETE are never granted), synthetic-only client data
enforced by a CHECK constraint, and provider portability enforced by lint. 247 tests.

Everything in the video is the real application against a real database and a real model
call. Nothing is mocked or staged.

FastAPI · PostgreSQL · React · Claude and Gemini behind a single port interface.

Built spec-first: constitution → spec → plan → tasks → implementation, with every
architectural decision written down before it was coded.

#AI #Banking #IslamicFinance #FinTech #Kuwait #SoftwareEngineering #LLM

---

## Shorter variant (if the above runs long in the composer)

Built a submission for the **Warba Bank Corporate Banking AI Challenge** — an AI system
that drafts corporate banking documents from a Relationship Manager's raw meeting notes.

The hard part wasn't the drafting. It was making **"it didn't hallucinate"** something you
can *check*:

→ Two-pass generation. The pass that writes the document never sees the raw sources — it
can only use a pre-verified evidence ledger.
→ If the model can't quote it from a real source, our code deletes the claim. No fuzzy
matching; one altered digit fails.
→ What the notes didn't say is marked **MISSING** in amber — and unresolved gaps block
approval outright. No override.
→ Shariah screening is a deterministic, compliance-reviewable word list, not a prompt. It
stops a non-compliant draft before it exists.

Audit trail immutability is enforced by database privilege, not by convention. Synthetic-
only data by a CHECK constraint. 247 tests.

Every frame in this video is the real app against a real database and a real model call.

FastAPI · PostgreSQL · React · Claude and Gemini behind one port.

#AI #Banking #IslamicFinance #FinTech #Kuwait
