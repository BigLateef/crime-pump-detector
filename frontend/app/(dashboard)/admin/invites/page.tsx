"use client";

import { useState } from "react";
import { Card, CardHeader, Button, Input, EmptyState } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";
import { apiFetch } from "@/lib/api";
import { InviteOut, InviteCreateResponse } from "@/lib/types";

export default function AdminInvitesPage() {
  const { data: invites, loading, reload } = useApiData<InviteOut[]>("/admin/invites");
  const [label, setLabel] = useState("");
  const [maxUses, setMaxUses] = useState(1);
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<InviteCreateResponse | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const result = await apiFetch<InviteCreateResponse>("/admin/invites", {
        method: "POST",
        body: { recipient_label: label || undefined, max_uses: maxUses },
      });
      setJustCreated(result);
      setLabel("");
      reload();
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id: string) {
    await apiFetch(`/admin/invites/${id}/revoke`, { method: "POST" });
    reload();
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">Invite management</h1>
        <p className="text-sm text-ink-muted">Generate and manage invites. Codes are shown once, at creation.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Generate an invite" />
          <form onSubmit={handleCreate} className="space-y-3">
            <Input placeholder="Recipient label (optional)" value={label} onChange={(e) => setLabel(e.target.value)} />
            <div className="flex items-center gap-2">
              <label className="text-sm text-ink-muted">Max uses</label>
              <Input
                type="number"
                min={1}
                max={50}
                value={maxUses}
                onChange={(e) => setMaxUses(Number(e.target.value))}
                className="w-20"
              />
            </div>
            <Button type="submit" disabled={creating} className="w-full">
              {creating ? "Generating…" : "Generate invite"}
            </Button>
          </form>

          {justCreated && (
            <div className="mt-4 rounded border border-signal-conviction/30 bg-signal-conviction/10 p-3">
              <div className="mb-1 text-xs text-ink-muted">
                Copy this now — it won&apos;t be shown again.
              </div>
              <div className="font-mono text-lg tracking-widest text-ink">{justCreated.code}</div>
              <div className="mt-2 break-all font-mono text-xs text-ink-faint">{justCreated.registration_url}</div>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="All invites" />
          {loading && <p className="text-sm text-ink-muted">Loading…</p>}
          {!loading && invites && invites.length === 0 && (
            <EmptyState title="No invites yet" body="Generate the first one to bring a friend onto the platform." />
          )}
          {!loading && invites && invites.length > 0 && (
            <div className="space-y-2">
              {invites.map((inv) => {
                const status = inv.revoked_at
                  ? "Revoked"
                  : inv.is_used
                  ? "Used up"
                  : inv.expires_at && new Date(inv.expires_at) < new Date()
                  ? "Expired"
                  : "Active";
                return (
                  <div key={inv.id} className="flex items-center justify-between rounded border border-base-border p-3">
                    <div>
                      <div className="text-sm text-ink">{inv.recipient_label || "Unlabeled"}</div>
                      <div className="text-xs text-ink-faint">
                        {inv.use_count}/{inv.max_uses} used · {status}
                      </div>
                    </div>
                    {status === "Active" && (
                      <Button variant="danger" onClick={() => handleRevoke(inv.id)}>
                        Revoke
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
