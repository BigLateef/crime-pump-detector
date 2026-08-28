"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { Card, CardHeader, Button } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";
import { apiFetch } from "@/lib/api";
import { PreferencesOut } from "@/lib/types";

const CHAINS = ["solana", "base", "ethereum", "bnb"] as const;

export default function PreferencesPage() {
  const { data: prefs, loading } = useApiData<PreferencesOut>("/preferences");
  const [threshold, setThreshold] = useState(60);
  const [chains, setChains] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (prefs) {
      setThreshold(prefs.alert_threshold);
      setChains(prefs.selected_chains);
    }
  }, [prefs]);

  function toggleChain(chain: string) {
    setChains((prev) => (prev.includes(chain) ? prev.filter((c) => c !== chain) : [...prev, chain]));
    setSaved(false);
  }

  async function handleSave() {
    await apiFetch("/preferences", {
      method: "PATCH",
      body: { alert_threshold: threshold, selected_chains: chains },
    });
    setSaved(true);
  }

  if (loading) return <p className="text-sm text-ink-muted">Loading…</p>;

  return (
    <div className="max-w-lg">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">Preferences</h1>
        <p className="text-sm text-ink-muted">Controls which alerts reach you and at what threshold.</p>
      </div>

      <Card>
        <CardHeader title="Alert settings" />
        <div className="space-y-5">
          <div>
            <div className="mb-2 text-sm font-medium text-ink">Chains to monitor</div>
            <div className="flex flex-wrap gap-2">
              {CHAINS.map((chain) => (
                <button
                  key={chain}
                  onClick={() => toggleChain(chain)}
                  className={clsx(
                    "rounded border px-3 py-1.5 text-sm capitalize transition-colors",
                    chains.includes(chain)
                      ? "border-signal-early bg-signal-early/15 text-signal-early"
                      : "border-base-border text-ink-muted hover:border-ink-faint"
                  )}
                >
                  {chain}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between text-sm font-medium text-ink">
              <span>Minimum alert score</span>
              <span className="font-mono text-ink-muted">{threshold}</span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => {
                setThreshold(Number(e.target.value));
                setSaved(false);
              }}
              className="w-full accent-signal-early"
            />
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={handleSave}>Save changes</Button>
            {saved && <span className="text-sm text-signal-conviction">Saved.</span>}
          </div>
        </div>
      </Card>
    </div>
  );
}
