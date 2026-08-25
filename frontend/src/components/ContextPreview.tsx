/**
 * Context preview (task T101).
 *
 * Shows the RM everything the system found, BEFORE it writes anything (FR-003), and
 * lets them deselect any source (FR-004).
 *
 * This screen is only meaningful because retrieval is deterministic (research.md R4).
 * With semantic retrieval the candidate set would not be knowable in advance, so there
 * would be nothing honest to display here.
 */

import type { AssembledContext } from "@/types/api";

interface Props {
  context: AssembledContext;
  excluded: Set<string>;
  onToggle: (sourceId: string) => void;
}

export function ContextPreview({ context, excluded, onToggle }: Props) {
  return (
    <section className="context">
      <header>
        <h3>What the system found</h3>
        <p className="context__help">
          These are the only sources that will be used. Untick anything you do not want
          included — nothing outside this list can appear in the draft.
        </p>
      </header>

      {context.sources.length === 0 ? (
        <p className="context__empty">
          No stored records were found for this client. Any document generated now will be
          based solely on the notes you provide, and everything else will be marked as missing.
        </p>
      ) : (
        <ul className="context__sources">
          {context.sources.map((source) => (
            <li key={source.source_id}>
              <label>
                <input
                  type="checkbox"
                  checked={!excluded.has(source.source_id)}
                  onChange={() => onToggle(source.source_id)}
                />
                <span className="context__label">{source.label}</span>
                {source.source_system && (
                  <span className="context__system">{source.source_system}</span>
                )}
                {source.effective_date && (
                  <span className="context__date">{source.effective_date}</span>
                )}
                {source.is_external && (
                  <span className="flag flag--external" title="External, unverified source">
                    External
                  </span>
                )}
              </label>
            </li>
          ))}
        </ul>
      )}

      {context.conflicts.length > 0 && (
        <div className="context__conflicts">
          <h4>⚠ Sources disagree</h4>
          <p>
            These values differ between systems. The system will not choose between them —
            please check which is correct.
          </p>
          <ul>
            {context.conflicts.map((conflict) => (
              <li key={conflict.field}>
                <strong>{conflict.field.replace(/_/g, " ")}</strong>:{" "}
                {conflict.values
                  .map((v) => `${String(v.value)} (${v.source_system})`)
                  .join(" vs ")}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
