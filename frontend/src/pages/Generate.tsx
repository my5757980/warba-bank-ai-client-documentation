/**
 * Generation page (task T102).
 *
 * Steps 2–4 of the five-interaction journey: select client → provide notes → review
 * context → generate.
 *
 * The waiting state matters (NFR-PERF-03): generation takes tens of seconds, and the
 * screen must never look frozen. It shows what is happening at each stage — grounding,
 * then composing, then screening — because an honest explanation of a 30-second wait is
 * far better tolerated than an unexplained spinner.
 */

import { useEffect, useState } from "react";
import { api, RequestError } from "@/api/client";
import { ContextPreview } from "@/components/ContextPreview";
import type { AssembledContext, ClientSummary, DocumentDetail, DocumentType } from "@/types/api";

const DOC_TYPE: DocumentType = "CALL_REPORT";

const STAGES = [
  "Reading your sources and extracting the facts they state…",
  "Drafting the report from those facts only…",
  "Checking terminology and verifying every figure…",
];

interface Props {
  client: ClientSummary;
  onGenerated: (document: DocumentDetail) => void;
  onBack: () => void;
}

export function Generate({ client, onGenerated, onBack }: Props) {
  const [context, setContext] = useState<AssembledContext | null>(null);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [notes, setNotes] = useState("");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<{ title: string; message: string; findings?: unknown } | null>(null);

  useEffect(() => {
    api.getContext(client.id, DOC_TYPE).then(setContext).catch(() => setContext(null));
  }, [client.id]);

  // Honest progress. The stages are real pipeline phases, advanced on a timer because
  // the backend does not stream stage events yet — the wording stays accurate either way.
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 9000);
    return () => clearInterval(timer);
  }, [busy]);

  async function generate() {
    setBusy(true);
    setStage(0);
    setError(null);
    try {
      const included = (context?.sources ?? [])
        .filter((s) => !excluded.has(s.source_id))
        .reduce<{ records: string[]; documents: string[] }>(
          (acc, s) => {
            if (s.source_type === "CLIENT_RECORD") acc.records.push(s.source_id);
            else acc.documents.push(s.source_id);
            return acc;
          },
          { records: [], documents: [] },
        );

      const document = await api.generate({
        client_id: client.id,
        document_type: DOC_TYPE,
        meeting_notes: notes,
        client_record_ids: included.records,
        source_document_ids: included.documents,
        rm_instruction: instruction || undefined,
      });
      onGenerated(document);
    } catch (err) {
      if (err instanceof RequestError && err.isScreeningBlocked) {
        setError({
          title: "Draft blocked — Shariah compliance",
          message: err.message,
          findings: err.detail?.findings,
        });
      } else if (err instanceof RequestError && err.isValidationFailure) {
        setError({ title: "Draft could not be verified", message: err.message });
      } else {
        setError({
          title: "Could not generate the report",
          message: err instanceof Error ? err.message : "Please try again.",
        });
      }
    } finally {
      setBusy(false);
    }
  }

  if (busy) {
    return (
      <main className="generating">
        <h2>Preparing your call report</h2>
        <div className="progress" aria-live="polite">
          {STAGES.map((text, i) => (
            <p key={i} className={i <= stage ? "progress__step progress__step--active" : "progress__step"}>
              {i < stage ? "✓" : i === stage ? "…" : "·"} {text}
            </p>
          ))}
        </div>
        <p className="generating__note">
          This usually takes under 30 seconds. Nothing is saved until the checks pass.
        </p>
      </main>
    );
  }

  return (
    <main className="generate">
      <button type="button" className="link" onClick={onBack}>← Back to portfolio</button>

      <h2>New call report</h2>
      <p className="generate__client">
        {client.legal_name} <span className="muted">({client.client_reference})</span>
      </p>

      {error && (
        <div className="alert alert--error" role="alert">
          <h3>{error.title}</h3>
          <p>{error.message}</p>
          {Array.isArray(error.findings) && (
            <ul>
              {(error.findings as Array<{ term: string; rule_id: string; rationale: string }>).map(
                (f) => (
                  <li key={f.rule_id}>
                    <strong>“{f.term}”</strong> — {f.rationale} <code>{f.rule_id}</code>
                  </li>
                ),
              )}
            </ul>
          )}
          <p className="alert__note">No document was created.</p>
        </div>
      )}

      <label className="field">
        <span>Your meeting notes</span>
        <span className="field__help">
          Paste them exactly as you wrote them — bullet points are fine. Anything the notes
          do not say will be marked as missing rather than filled in.
        </span>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={14}
          placeholder="- Met the Finance Director at their office&#10;- Discussed working capital needs for Q4&#10;- Action: send facility review checklist"
        />
      </label>

      {context && (
        <ContextPreview
          context={context}
          excluded={excluded}
          onToggle={(id) =>
            setExcluded((prev) => {
              const next = new Set(prev);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            })
          }
        />
      )}

      <label className="field">
        <span>Anything to emphasise? (optional)</span>
        <span className="field__help">
          Affects tone and emphasis only. It cannot add facts or change what is checked.
        </span>
        <input
          type="text"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          maxLength={1000}
          placeholder="e.g. keep the risk section prominent"
        />
      </label>

      <button
        type="button"
        className="button--primary"
        onClick={generate}
        disabled={!notes.trim()}
      >
        Generate call report
      </button>
      {!notes.trim() && (
        <p className="muted">Meeting notes are required — a call report needs a record of the meeting.</p>
      )}
    </main>
  );
}
