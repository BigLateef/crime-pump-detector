"use client";

import { useState } from "react";
import { Card, CardHeader, Button, Input, EmptyState } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";
import { apiFetch } from "@/lib/api";
import { DiscordIntegrationOut, DiscordAlertConfigOut } from "@/lib/types";

const ALERT_TYPE_LABELS: Record<string, string> = {
  SIGNAL_DETECTED: "Signal detected",
  SECURITY_RISK: "Security risk",
  LIQUIDITY_WARNING: "Liquidity warning",
  DEPLOYER_SELLING: "Deployer selling",
  MOMENTUM_FAILURE: "Momentum failure",
  MOMENTUM_RECOVERY: "Momentum recovery",
  SCANNER_FAILURE: "Scanner failure",
};

export default function DiscordSettingsPage() {
  const { data: integrations, loading, reload } = useApiData<DiscordIntegrationOut[]>(
    "/admin/discord-integrations"
  );
  const { data: config, loading: configLoading } = useApiData<DiscordAlertConfigOut>(
    "/admin/discord-integrations/config"
  );
  const [name, setName] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [minScore, setMinScore] = useState(55);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch("/admin/discord-integrations", {
        method: "POST",
        body: { name, webhook_url: webhookUrl, minimum_score: minScore, allowed_chains: [], alert_types: [] },
      });
      setName("");
      setWebhookUrl("");
      reload();
    } catch {
      setError("Couldn't save this integration. Confirm the webhook URL is valid.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">Discord alerts</h1>
        <p className="text-sm text-ink-muted">
          Webhook URLs are encrypted at rest and never shown again after saving.
        </p>
      </div>

      {!configLoading && config && (
        <Card className="mb-4">
          <CardHeader title="Delivery mode" />
          <p className="text-sm text-ink">
            {config.all_signals_enabled ? (
              <>
                <span className="font-medium text-signal-conviction">All-signals mode is ON.</span>{" "}
                Every valid signal is sent regardless of score — per-destination minimum score below is
                ignored while this is on. Set via <code className="text-xs">DISCORD_ALERT_ALL_SIGNALS</code> on
                the backend.
              </>
            ) : (
              <>
                Score filtering is active. Each destination's minimum score (default{" "}
                <span className="font-mono">{config.min_score}</span>) still applies.
              </>
            )}
          </p>
          <p className="mt-2 text-xs text-ink-muted">
            Delivery cooldown: <span className="font-mono">{config.cooldown_minutes} min</span> per
            token/alert-type, independent of the scanner's own signal cooldown.
          </p>
          <div className="mt-3">
            <div className="mb-1 text-xs uppercase tracking-wide text-ink-faint">Alert types</div>
            <div className="flex flex-wrap gap-1.5">
              {config.all_alert_types.map((t) => {
                const implemented = config.implemented_alert_types.includes(t);
                return (
                  <span
                    key={t}
                    className={`rounded border px-2 py-0.5 text-xs ${
                      implemented
                        ? "border-signal-conviction/30 bg-signal-conviction/10 text-signal-conviction"
                        : "border-base-border text-ink-faint"
                    }`}
                    title={implemented ? "Actively detected and sent" : "Defined, no detection logic wired up yet"}
                  >
                    {ALERT_TYPE_LABELS[t] || t}
                    {!implemented && " (not yet wired)"}
                  </span>
                );
              })}
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Connected destinations" />
          {loading && <p className="text-sm text-ink-muted">Loading…</p>}
          {!loading && integrations && integrations.length === 0 && (
            <EmptyState title="No Discord destinations yet" body="Add one to start receiving alerts in Discord." />
          )}
          {!loading && integrations && integrations.length > 0 && (
            <div className="space-y-2">
              {integrations.map((i) => (
                <div key={i.id} className="flex items-center justify-between rounded border border-base-border p-3">
                  <div>
                    <div className="text-sm font-medium text-ink">{i.name}</div>
                    <div className="text-xs text-ink-faint">
                      min score {i.minimum_score}
                      {config?.all_signals_enabled && " (ignored — all-signals mode is on)"}
                    </div>
                  </div>
                  <span
                    className={`text-xs ${i.enabled ? "text-signal-conviction" : "text-ink-faint"}`}
                  >
                    {i.enabled ? "Active" : "Disabled"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Add a destination" />
          <form onSubmit={handleCreate} className="space-y-3">
            <Input placeholder="Name (e.g. #early-signals)" value={name} onChange={(e) => setName(e.target.value)} required />
            <Input
              placeholder="Discord webhook URL"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              type="url"
              required
            />
            <div>
              <div className="mb-1 flex justify-between text-xs text-ink-muted">
                <span>Minimum score to notify</span>
                <span className="font-mono">{minScore}</span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-signal-early"
              />
            </div>
            {error && <p className="text-sm text-signal-danger">{error}</p>}
            <Button type="submit" disabled={submitting} className="w-full">
              {submitting ? "Saving…" : "Save destination"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
