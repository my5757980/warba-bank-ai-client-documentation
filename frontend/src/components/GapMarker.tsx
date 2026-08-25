/**
 * Gap marker (task T104).
 *
 * A gap is a successful outcome, not an error — the system telling the RM plainly that
 * it could not source something. It is styled to be unmissable and it blocks approval
 * until resolved or explicitly acknowledged (FR-025).
 *
 * The visual weight here is deliberate. A subtle gap marker would be scrolled past,
 * and a gap scrolled past is functionally identical to a fabricated value.
 */

import type { Gap } from "@/types/api";

interface Props {
  gap: Gap;
  onResolve?: (field: string, note: string) => void;
  readOnly?: boolean;
}

export function GapMarker({ gap, onResolve, readOnly }: Props) {
  if (gap.resolved) {
    return (
      <span className="gap gap--resolved" title={gap.resolution_note ?? "Acknowledged"}>
        ✓ {gap.label} — resolved
      </span>
    );
  }

  return (
    <div className="gap gap--open">
      <strong className="gap__label">{gap.label}</strong>
      <p className="gap__help">
        The system could not find this in the supplied sources, so it has not been filled in.
        Add it yourself, or acknowledge it, before approving.
      </p>
      {!readOnly && onResolve && (
        <div className="gap__actions">
          <button
            type="button"
            onClick={() => {
              const note = window.prompt(`Provide the missing "${gap.field}", or a note explaining why it is not available:`);
              if (note && note.trim()) onResolve(gap.field, note.trim());
            }}
          >
            Resolve
          </button>
        </div>
      )}
    </div>
  );
}
