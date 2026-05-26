/**
 * Claims Manager.
 *
 * Production edge-enrollment path. Operators generate a one-time claim
 * token here, then walk it over to the physical Tactile Edge appliance,
 * which redeems the token with its real serial + firmware version.
 *
 * This replaces the "type any string and the edge appears" misfeature.
 */

import { useEffect, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { api } from "../lib/api";
import type { ApiError, Claim, ClaimCreated } from "../lib/types";

export interface ClaimsManagerProps {
  onRefresh: () => Promise<void>;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().replace("T", " ").slice(0, 16);
  } catch {
    return iso;
  }
}

export function ClaimsManager({ onRefresh }: ClaimsManagerProps): JSX.Element {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastCreated, setLastCreated] = useState<ClaimCreated | null>(null);

  // form
  const [label, setLabel] = useState("");
  const [site, setSite] = useState("");
  const [expectedSerial, setExpectedSerial] = useState("");
  const [ttlHours, setTtlHours] = useState(24);

  // redeem-test form
  const [redeemToken, setRedeemToken] = useState("");
  const [redeemEdgeId, setRedeemEdgeId] = useState("");
  const [redeemSerial, setRedeemSerial] = useState("");
  const [redeemFw, setRedeemFw] = useState("TS-G4 v0.3");
  const [redeemMsg, setRedeemMsg] = useState<string | null>(null);

  const refresh = async (): Promise<void> => {
    setErr(null);
    try {
      const rows = await api.listClaims();
      setClaims(rows);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const create = async (): Promise<void> => {
    setBusy(true);
    setErr(null);
    try {
      const c = await api.createClaim({
        label: label.trim(),
        site: site.trim(),
        expected_serial: expectedSerial.trim(),
        ttl_hours: ttlHours,
      });
      setLastCreated(c);
      setLabel("");
      setSite("");
      setExpectedSerial("");
      await refresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (id: string): Promise<void> => {
    setBusy(true);
    setErr(null);
    try {
      await api.revokeClaim(id);
      await refresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const redeem = async (): Promise<void> => {
    setBusy(true);
    setErr(null);
    setRedeemMsg(null);
    try {
      const edge = await api.redeemClaim({
        token: redeemToken.trim(),
        edge_id: redeemEdgeId.trim(),
        serial: redeemSerial.trim(),
        firmware_version: redeemFw.trim(),
      });
      setRedeemMsg(`Enrolled edge ${edge.id} (serial ${edge.serial}).`);
      setRedeemToken("");
      setRedeemEdgeId("");
      setRedeemSerial("");
      await refresh();
      await onRefresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="EDGE CLAIMS"
        title="Two-step enrollment with validation"
        lede="Generate a one-time claim token, then redeem it on the physical Edge. Validates serial + firmware version. Replaces the v0.1 'type any ID' enrollment."
        actions={
          <button type="button" className="btn" onClick={() => void refresh()}>
            Refresh
          </button>
        }
      />

      {err ? (
        <div className="banner">
          <b>ERR</b>&nbsp;{err}
        </div>
      ) : null}

      <section className="card">
        <header className="card__head">
          <h3 className="h3">01 · Create claim token</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            POST /v1/claims
          </span>
        </header>
        <div
          className="card__body"
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 100px auto", gap: 8, alignItems: "end" }}
        >
          <label className="field">
            <span>LABEL</span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="edge-floor3-line7"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>SITE</span>
            <input
              type="text"
              value={site}
              onChange={(e) => setSite(e.target.value)}
              placeholder="Plant 2 / Bakery"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>EXPECTED SERIAL (optional)</span>
            <input
              type="text"
              value={expectedSerial}
              onChange={(e) => setExpectedSerial(e.target.value)}
              placeholder="PINNED to one device"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>TTL HOURS</span>
            <input
              type="number"
              min={1}
              max={720}
              value={ttlHours}
              onChange={(e) => setTtlHours(parseInt(e.target.value, 10) || 24)}
              disabled={busy}
            />
          </label>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void create()}
            disabled={busy}
          >
            Generate
          </button>
        </div>
      </section>

      {lastCreated ? (
        <section className="card card--ink">
          <header className="card__head">
            <h3 className="h3">Token generated</h3>
            <span className="mono" style={{ fontSize: 11 }}>
              shown once · expires {fmtDate(lastCreated.expires_at)}
            </span>
          </header>
          <div className="card__body">
            <p style={{ marginBottom: 8, fontSize: 12, opacity: 0.85 }}>
              Copy this token now and paste it into the Edge appliance&apos;s
              first-boot wizard. We will NOT show it again.
            </p>
            <code
              className="mono"
              style={{
                display: "block",
                padding: 10,
                background: "rgba(0,0,0,0.5)",
                fontSize: 12,
                wordBreak: "break-all",
              }}
            >
              {lastCreated.token}
            </code>
          </div>
        </section>
      ) : null}

      <section className="card">
        <header className="card__head">
          <h3 className="h3">02 · Redeem (bench-test)</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            POST /v1/claims/redeem
          </span>
        </header>
        <div
          className="card__body"
          style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 8, alignItems: "end" }}
        >
          <label className="field">
            <span>TOKEN</span>
            <input
              type="text"
              value={redeemToken}
              onChange={(e) => setRedeemToken(e.target.value)}
              placeholder="ec_..."
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>EDGE ID</span>
            <input
              type="text"
              value={redeemEdgeId}
              onChange={(e) => setRedeemEdgeId(e.target.value)}
              placeholder="edge-floor3-line7"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>SERIAL</span>
            <input
              type="text"
              value={redeemSerial}
              onChange={(e) => setRedeemSerial(e.target.value)}
              placeholder="1234567890ABCD"
              disabled={busy}
            />
          </label>
          <label className="field">
            <span>FIRMWARE</span>
            <input
              type="text"
              value={redeemFw}
              onChange={(e) => setRedeemFw(e.target.value)}
              placeholder="TS-G4 v0.3"
              disabled={busy}
            />
          </label>
          <button
            type="button"
            className="btn"
            disabled={busy || !redeemToken || !redeemEdgeId || !redeemSerial || !redeemFw}
            onClick={() => void redeem()}
          >
            Redeem
          </button>
        </div>
        {redeemMsg ? (
          <div className="banner" style={{ margin: 8, background: "#1a3", color: "#fff" }}>
            <b>OK</b>&nbsp;{redeemMsg}
          </div>
        ) : null}
      </section>

      <section className="card">
        <header className="card__head">
          <h3 className="h3">Claims</h3>
          <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
            {claims.length} total
          </span>
        </header>
        <div className="card__body" style={{ padding: 0 }}>
          {claims.length === 0 ? (
            <div className="empty">No claims yet.</div>
          ) : (
            <table className="datagrid">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Label</th>
                  <th>Site</th>
                  <th>Pinned serial</th>
                  <th>State</th>
                  <th>Created</th>
                  <th>Expires</th>
                  <th>Redeemed by</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {claims.map((c) => {
                  const state = c.revoked
                    ? "REVOKED"
                    : c.redeemed_at
                      ? "REDEEMED"
                      : new Date(c.expires_at) < new Date()
                        ? "EXPIRED"
                        : "PENDING";
                  return (
                    <tr key={c.id}>
                      <td className="id">{c.id}</td>
                      <td>{c.label || "—"}</td>
                      <td>{c.site || "—"}</td>
                      <td className="mono">{c.expected_serial || "any"}</td>
                      <td>
                        <span
                          className="led"
                          data-state={
                            state === "PENDING"
                              ? "warn"
                              : state === "REDEEMED"
                                ? "online"
                                : "off"
                          }
                        >
                          <span className="led__dot" aria-hidden="true" />
                          {state}
                        </span>
                      </td>
                      <td>{fmtDate(c.created_at)}</td>
                      <td>{fmtDate(c.expires_at)}</td>
                      <td className="mono">{c.redeemed_edge_id ?? "—"}</td>
                      <td>
                        {!c.revoked && !c.redeemed_at ? (
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={() => void revoke(c.id)}
                            disabled={busy}
                          >
                            Revoke
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
