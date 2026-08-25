/**
 * Evidence inspector (task T105).
 *
 * Shows the verbatim excerpt exactly as captured from the source, with its page or
 * character locator. Never a paraphrase — the RM opens this to check the system's
 * reading against the document, and a paraphrase cannot be checked.
 */

import type { Evidence } from "@/types/api";

interface Props {
  evidence: Evidence | null;
  loading: boolean;
  onClose: () => void;
}

export function EvidenceInspector({ evidence, loading, onClose }: Props) {
  if (!loading && !evidence) return null;

  const locator = evidence?.locator ?? {};
  const location =
    locator.page_start != null
      ? `page ${locator.page_start}${locator.page_end && locator.page_end !== locator.page_start ? `–${locator.page_end}` : ""}`
      : locator.char_start != null
        ? `characters ${locator.char_start}–${locator.char_end}`
        : null;

  return (
    <aside className="evidence-panel" role="dialog" aria-label="Source evidence">
      <header className="evidence-panel__header">
        <h4>Source evidence</h4>
        <button type="button" onClick={onClose} aria-label="Close">×</button>
      </header>

      {loading && <p>Loading…</p>}

      {evidence && (
        <div className="evidence-panel__body">
          <dl>
            <dt>Reference</dt>
            <dd>{evidence.claim_id}</dd>
            <dt>Source</dt>
            <dd>
              {evidence.source_label}
              {location && <span className="evidence-panel__locator"> · {location}</span>}
              {evidence.is_external && <span className="flag flag--external">External</span>}
            </dd>
          </dl>

          <h5>Exact text from the source</h5>
          <blockquote className="evidence-panel__excerpt">{evidence.verbatim_excerpt}</blockquote>

          <h5>Extracted claim</h5>
          <p className="evidence-panel__claim">{evidence.claim_text}</p>
        </div>
      )}
    </aside>
  );
}
