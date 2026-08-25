/**
 * Approval dialog (task T107).
 *
 * The most constitutionally significant component in the frontend.
 *
 * Constitution Principle III requires approval to be a deliberate, recorded act. This
 * dialog is built so it cannot be completed by accident:
 *
 *   - the confirm button is disabled until the RM ticks an explicit acknowledgement;
 *   - unresolved gaps block the action entirely and are listed by name;
 *   - the exact `content_hash` being approved is displayed and submitted, so the RM
 *     approves the version they actually read;
 *   - the RM is told, in plain words, that they are accepting authorship.
 *
 * There is no "approve all", no keyboard shortcut, and no default-checked box. If
 * approving ever feels like one click too many, that is the design working.
 */

import { useState } from "react";
import type { DocumentDetail, Gap } from "@/types/api";

interface Props {
  document: DocumentDetail;
  onConfirm: (acknowledgeGaps: Array<{ section_key: string; field: string; note: string }>) => void;
  onCancel: () => void;
  submitting: boolean;
}

interface OpenGap extends Gap {
  section_key: string;
  section_title: string;
}

export function ApprovalDialog({ document, onConfirm, onCancel, submitting }: Props) {
  const [confirmed, setConfirmed] = useState(false);

  const openGaps: OpenGap[] = document.sections.flatMap((section) =>
    section.gaps
      .filter((gap) => !gap.resolved)
      .map((gap) => ({ ...gap, section_key: section.section_key, section_title: section.title })),
  );

  const blocked = openGaps.length > 0;

  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-label="Approve document">
      <div className="dialog">
        <h2>Approve this document</h2>

        <dl className="dialog__meta">
          <dt>Client</dt>
          <dd>{document.client_reference}</dd>
          <dt>Document</dt>
          <dd>{document.document_type.replace(/_/g, " ").toLowerCase()}</dd>
          <dt>Version</dt>
          <dd>{document.version_number}</dd>
          <dt>Shariah status</dt>
          <dd>{document.shariah_status.replace(/_/g, " ").toLowerCase()}</dd>
          <dt>Content reference</dt>
          {/* Displayed so the RM can see they are approving a specific version. */}
          <dd><code>{document.content_hash.slice(0, 16)}…</code></dd>
        </dl>

        {blocked ? (
          <div className="dialog__blocked">
            <h3>Approval is blocked</h3>
            <p>
              {openGaps.length} item{openGaps.length === 1 ? " is" : "s are"} still marked as
              missing. Fill each one in, or acknowledge it, before approving.
            </p>
            <ul>
              {openGaps.map((gap) => (
                <li key={`${gap.section_key}.${gap.field}`}>
                  <strong>{gap.section_title}</strong> — {gap.label}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <>
            <div className="dialog__attestation">
              <p>
                This document was drafted with AI assistance. By approving it you confirm
                that you have reviewed its content and that you accept authorship of it as
                the Relationship Manager for this client.
              </p>
              <p className="dialog__note">
                Your name, the time, and the exact content you approved will be recorded in
                the audit trail.
              </p>
            </div>

            <label className="dialog__confirm">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              I have reviewed this document and accept authorship.
            </label>
          </>
        )}

        <div className="dialog__actions">
          <button type="button" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button
            type="button"
            className="button--primary"
            // Disabled unless the RM has actively confirmed. Never enabled by default.
            disabled={blocked || !confirmed || submitting}
            onClick={() => onConfirm([])}
          >
            {submitting ? "Approving…" : "Approve document"}
          </button>
        </div>
      </div>
    </div>
  );
}
