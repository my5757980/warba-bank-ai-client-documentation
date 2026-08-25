/**
 * Section card (task T103).
 *
 * Shows the drafted content, its citations, its confidence, and any gaps. Three signals
 * are always visible rather than tucked behind a control:
 *
 *   - citation chips, so the RM can check any claim in one click (FR-024)
 *   - a LOW-confidence flag, so attention goes where the evidence is thin (FR-012)
 *   - external-data marking, so unverified content is never mistaken for a bank record
 */

import { useState } from "react";
import type { Gap, Section } from "@/types/api";
import { GapMarker } from "./GapMarker";

interface Props {
  section: Section;
  readOnly: boolean;
  onInspectEvidence: (claimId: string) => void;
  onEdit: (sectionKey: string, content: string) => void;
  onRegenerate: (sectionKey: string) => void;
  onResolveGap: (sectionKey: string, field: string, note: string) => void;
}

export function SectionCard({
  section,
  readOnly,
  onInspectEvidence,
  onEdit,
  onRegenerate,
  onResolveGap,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(section.content ?? "");

  const openGaps = section.gaps.filter((g: Gap) => !g.resolved);

  return (
    <article className={`section section--${section.confidence.toLowerCase()}`}>
      <header className="section__header">
        <h3>{section.title}</h3>
        <div className="section__flags">
          {section.confidence === "LOW" && (
            <span className="flag flag--low" title="Built on thin or ambiguous evidence — review closely">
              ⚠ Low confidence
            </span>
          )}
          {section.contains_external_data && (
            <span className="flag flag--external" title="Contains external, unverified data">
              External source
            </span>
          )}
          {section.is_rm_edited && <span className="flag flag--edited">Edited by you</span>}
        </div>
      </header>

      {editing ? (
        <div className="section__editor">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={10} />
          <div className="section__actions">
            <button type="button" onClick={() => { onEdit(section.section_key, draft); setEditing(false); }}>
              Save
            </button>
            <button type="button" onClick={() => { setDraft(section.content ?? ""); setEditing(false); }}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="section__body">
          {section.content ? (
            <p>{section.content}</p>
          ) : (
            <p className="section__empty">
              No content could be sourced for this section.
            </p>
          )}
        </div>
      )}

      {openGaps.length > 0 && (
        <div className="section__gaps">
          {openGaps.map((gap) => (
            <GapMarker
              key={gap.field}
              gap={gap}
              readOnly={readOnly}
              onResolve={(field, note) => onResolveGap(section.section_key, field, note)}
            />
          ))}
        </div>
      )}

      {section.evidence_refs.length > 0 && (
        <footer className="section__evidence">
          <span className="section__evidence-label">Sources:</span>
          {section.evidence_refs.map((claimId) => (
            <button
              key={claimId}
              type="button"
              className="citation"
              onClick={() => onInspectEvidence(claimId)}
              title="View the exact text this came from"
            >
              {claimId}
            </button>
          ))}
        </footer>
      )}

      {!readOnly && !editing && (
        <div className="section__actions">
          <button type="button" onClick={() => setEditing(true)}>Edit</button>
          <button type="button" onClick={() => onRegenerate(section.section_key)}>Regenerate</button>
        </div>
      )}
    </article>
  );
}
