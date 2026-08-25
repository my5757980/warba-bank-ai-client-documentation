/** Sign-in page (task T079). */

import { useState } from "react";
import { api, setToken } from "@/api/client";
import type { User } from "@/types/api";

export function Login({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [email, setEmail] = useState("sara.rm@warba.demo");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.login(email, password);
      setToken(result.access_token);
      onSignedIn(result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <h1>Warba Bank — Client Documentation</h1>
      <p className="login__subtitle">Corporate Banking · Relationship Manager workspace</p>

      <form onSubmit={submit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="login__notice">
        All client data in this system is synthetic. No real customer information is held.
      </p>
    </main>
  );
}
