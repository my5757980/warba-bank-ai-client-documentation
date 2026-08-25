/**
 * Review page (task T106).
 *
 * Step 4–5 of the journey. The RM reads the draft, checks citations, fixes what needs
 * fixing, and approves.
 *
 * The AI-generated banner is permanent and unconditional (FR-020). It does not
 * disappear once the RM edits a section, because a part-edited document is still
 * part-AI-generated, and the reviewer downstream needs to know that.
 */

import { useState } from "react";
import { api, RequestError } from "@/api/client";
import { ApprovalDialog } from "@/components/ApprovalDialog";
import { EvidenceInspector } from "@/components/EvidenceInspector";
import { SectionCard } from "@/components/SectionCard";
import type { ApprovalRecord, DocumentDetail, Evidence } from "@/types/api";

interface Props {
  document: DocumentDetail;
  onChange: (document: DocumentDetail) => void;
  onApproved: (record: ApprovalRecord) => void;
  onBack: () => void;
}

export function Review({ document, onChange, onApproved, onBack }: Props) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [loadingEvidence, setLoadingEvidence] = useState(false);
  const [showApproval, setShowApproval] = useState(false);
  const [approving, setApproving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const readOnly = document.status === "APPROVED";

  async function download() {
    try {
      const { blob, filename } = await api.exportDocument(document.id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "The document could not be exported.");
    }
  }

  async function guard<T>(fn: () => Promise<T>, onOk: (value: T) => void) {
    try {
      onOk(await fn());
      setNotice(null);
    } catch (err) {
      if (err instanceof RequestError && err.isStale) {
        // FR-040 — never silently overwrite another session's work.
        setNotice("This document changed in another session. Reload to see the current version.");
      } else if (err instanceof RequestError && err.isScreeningBlocked) {
        setNotice(`Blocked by Shariah screening: ${err.message}`);
      } else {
        setNotice(err instanceof Error ? err.message : "That action could not be completed.");
      }
    }
  }

  return (
    <main className="review">
      <button type="button" className="link" onClick={onBack}>
        &larr; Back
      </button>

      {/* Permanent and unconditional. Never hidden once editing begins. */}
      <div className="banner banner--ai" role="note">
        AI-assisted draft &mdash; you are the author. Review every section before approving.
      </div>

      <header className="review__header">
        <h2>Call Report</h2>
        <dl className="review__meta">
          <dt>Client</dt>
          <dd>{document.client_reference}</dd>
          <dt>Status</dt>
          <dd>{document.status.toLowerCase()}</dd>
          <dt>Shariah</dt>
          <dd>{document.shariah_status.replace(/_/g, " ").toLowerCase()}</dd>
          <dt>Version</dt>
          <dd>{document.version_number}</dd>
        </dl>
      </header>

      {document.unresolved_gap_count > 0 && (
        <div className="alert alert--gaps" role="status">
          <strong>{document.unresolved_gap_count}</strong> item
          {document.unresolved_gap_count === 1 ? "" : "s"} could not be sourced and{" "}
          {document.unresolved_gap_count === 1 ? "is" : "are"} marked below. Approval is blocked
          until each is filled in or acknowledged.
        </div>
      )}

      {document.screening && document.screening.findings.length > 0 && (
        <div className="alert alert--screening">
          <strong>Terminology flags</strong> (vocabulary {document.screening.vocabulary_version}):
          <ul>
            {document.screening.findings.map((f, i) => (
              <li key={i}>
                &ldquo;{f.term}&rdquo; in {f.section_key} &mdash; <code>{f.rule_id}</code>
              </li>
            ))}
          </ul>
        </div>
      )}

      {notice && (
        <div className="alert alert--error" role="alert">
          {notice}
        </div>
      )}

      <div className="review__body">
        <div className="review__sections">
          {document.sections.map((section) => (
            <SectionCard
              key={section.section_key}
              section={section}
              readOnly={readOnly}
              onInspectEvidence={async (claimId) => {
                setLoadingEvidence(true);
                try {
                  setEvidence(await api.getEvidence(document.id, claimId));
                } finally {
                  setLoadingEvidence(false);
                }
              }}
              onEdit={(key, content) =>
                guard(
                  () => api.editSection(document.id, key, document.content_hash, { content }),
                  onChange,
                )
              }
              onRegenerate={(key) => guard(() => api.regenerateSection(document.id, key), onChange)}
              onResolveGap={(key, field, note) =>
                guard(
                  () =>
                    api.editSection(document.id, key, document.content_hash, {
                      content: document.sections.find((s) => s.section_key === key)?.content ?? null,
                      resolved_gaps: [{ field, resolution_note: note }],
                    }),
                  onChange,
                )
              }
            />
          ))}
        </div>

        <EvidenceInspector
          evidence={evidence}
          loading={loadingEvidence}
          onClose={() => setEvidence(null)}
        />
      </div>

      {!readOnly ? (
        <footer className="review__actions">
          <button type="button" onClick={() => guard(() => api.reject(document.id), onChange)}>
            Reject draft
          </button>
          <button type="button" className="button--primary" onClick={() => setShowApproval(true)}>
            Approve&hellip;
          </button>
        </footer>
      ) : (
        <footer className="review__actions">
          <span className="approved-badge">&#10003; Approved &mdash; this document is final</span>
          {/* Only offered once APPROVED. A draft has no approved content to distribute. */}
          <button type="button" className="button--primary" onClick={download}>
            Download Word document
          </button>
        </footer>
      )}

      {showApproval && (
        <ApprovalDialog
          document={document}
          submitting={approving}
          onCancel={() => setShowApproval(false)}
          onConfirm={async (acknowledged) => {
            setApproving(true);
            try {
              const record = await api.approve(document.id, document.content_hash, acknowledged);
              setShowApproval(false);
              onApproved(record);
            } catch (err) {
              setNotice(err instanceof Error ? err.message : "Approval failed.");
            } finally {
              setApproving(false);
            }
          }}
        />
      )}
    </main>
  );
}
