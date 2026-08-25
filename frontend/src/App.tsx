/**
 * Application shell.
 *
 * The five-interaction journey (SC-009, NFR-UX-01) is the state machine below:
 *
 *   portfolio → generate → review → approved
 *
 * Four screens, five interactions: sign in, select client, generate, review, approve.
 * Any new step added here costs an interaction, so it needs to earn its place.
 */

import { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/api/client";
import { Generate } from "@/pages/Generate";
import { Login } from "@/pages/Login";
import { Portfolio } from "@/pages/Portfolio";
import { Review } from "@/pages/Review";
import type { ApprovalRecord, ClientSummary, DocumentDetail, User } from "@/types/api";

type Screen =
  | { name: "portfolio" }
  | { name: "generate"; client: ClientSummary }
  | { name: "review"; document: DocumentDetail }
  | { name: "approved"; record: ApprovalRecord; document: DocumentDetail };

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [screen, setScreen] = useState<Screen>({ name: "portfolio" });

  useEffect(() => {
    if (!getToken()) {
      setChecking(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false));
  }, []);

  if (checking) return <main className="loading">Loading&hellip;</main>;
  if (!user) return <Login onSignedIn={setUser} />;

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__brand">Warba Bank &middot; Client Documentation</div>
        <div className="app__user">
          {user.full_name}
          <span className="app__role">{user.role.replace(/_/g, " ")}</span>
          <button
            type="button"
            className="link"
            onClick={() => {
              setToken(null);
              setUser(null);
              setScreen({ name: "portfolio" });
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Constitution Principle VII, stated where users can see it. */}
      <div className="app__synthetic-notice">
        Demonstration environment &mdash; all client data is synthetic.
      </div>

      {screen.name === "portfolio" && (
        <Portfolio onSelect={(client) => setScreen({ name: "generate", client })} />
      )}

      {screen.name === "generate" && (
        <Generate
          client={screen.client}
          onBack={() => setScreen({ name: "portfolio" })}
          onGenerated={(document) => setScreen({ name: "review", document })}
        />
      )}

      {screen.name === "review" && (
        <Review
          document={screen.document}
          onChange={(document) => setScreen({ name: "review", document })}
          onApproved={(record) =>
            setScreen({ name: "approved", record, document: screen.document })
          }
          onBack={() => setScreen({ name: "portfolio" })}
        />
      )}

      {screen.name === "approved" && (
        <main className="approved">
          <h2>Document approved</h2>
          <p>
            Approved by <strong>{screen.record.approver_name}</strong> as{" "}
            {screen.record.approver_role} on{" "}
            {new Date(screen.record.approved_at).toLocaleString()}.
          </p>
          <p className="muted">
            Shariah status:{" "}
            {screen.record.shariah_status_at_approval.replace(/_/g, " ").toLowerCase()}. The
            approval, the exact content, and every step that produced it are recorded in the
            audit trail.
          </p>
          <button type="button" onClick={() => setScreen({ name: "portfolio" })}>
            Back to portfolio
          </button>
        </main>
      )}
    </div>
  );
}
