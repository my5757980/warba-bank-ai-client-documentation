/** Portfolio page (task T100) — steps 1–2 of the five-interaction journey. */

import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { ClientSummary } from "@/types/api";

export function Portfolio({ onSelect }: { onSelect: (client: ClientSummary) => void }) {
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .listClients(search || undefined)
      .then(setClients)
      .finally(() => setLoading(false));
  }, [search]);

  return (
    <main className="portfolio">
      <h2>Your clients</h2>
      <p className="muted">
        Select a client to prepare a document. You see only the relationships you own.
      </p>

      <input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by name or reference"
        aria-label="Search clients"
      />

      {loading ? (
        /* Skeleton rows rather than a spinner: the page keeps its shape, so the
           content appears to resolve rather than to arrive. */
        <ul className="portfolio__list" aria-busy="true" aria-label="Loading clients">
          {[0, 1, 2, 3].map((i) => (
            <li key={i} className="skeleton-row" />
          ))}
        </ul>
      ) : clients.length === 0 ? (
        <div className="empty-state">
          <p>
            {search
              ? `No clients match “${search}”.`
              : "No clients in your portfolio yet."}
          </p>
          {search && (
            <button type="button" className="link" onClick={() => setSearch("")}>
              Clear search
            </button>
          )}
        </div>
      ) : (
        <ul className="portfolio__list">
          {clients.map((client) => (
            <li key={client.id}>
              <button type="button" onClick={() => onSelect(client)}>
                <span className="portfolio__name">{client.legal_name}</span>
                <span className="portfolio__ref">{client.client_reference}</span>
                <span className="portfolio__sector">{client.sector}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
