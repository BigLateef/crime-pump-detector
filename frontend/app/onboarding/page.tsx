"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/nav/AuthShell";
import { Button } from "@/components/ui/primitives";
import { apiFetch } from "@/lib/api";
import clsx from "clsx";

const CHAINS = ["solana", "base", "ethereum", "bnb"] as const;

export default function OnboardingPage() {
  const router = useRouter();
  const [selectedChains, setSelectedChains] = useState<string[]>(["solana", "base"]);
  const [threshold, setThreshold] = useState(60);
  const [saving, setSaving] = useState(false);

  function toggleChain(chain: string) {
    setSelectedChains((prev) => (prev.includes(chain) ? prev.filter((c) => c !== chain) : [...prev, chain]));
  }

  async function handleFinish() {
    setSaving(true);
    try {
      await apiFetch("/preferences", {
        method: "PATCH",
        body: { selected_chains: selectedChains, alert_threshold: threshold },
      });
    } finally {
      router.push("/scanner");
    }
  }

  return (
    <AuthShell title="Set up your alerts" subtitle="You can change these anytime in Settings.">
      <div className="space-y-5">
        <div>
          <div className="mb-2 text-sm font-medium text-ink">Chains to monitor</div>
          <div className="flex flex-wrap gap-2">
            {CHAINS.map((chain) => (
              <button
                key={chain}
                type="button"
                onClick={() => toggleChain(chain)}
                className={clsx(
                  "rounded border px-3 py-1.5 text-sm capitalize transition-colors",
                  selectedChains.includes(chain)
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
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="w-full accent-signal-early"
          />
          <p className="mt-1 text-xs text-ink-faint">
            Only alerts scoring at or above this threshold will notify you. WATCH starts at 35, EARLY at 55,
            HIGH-CONVICTION at 75.
          </p>
        </div>

        <Button className="w-full" onClick={handleFinish} disabled={saving}>
          {saving ? "Saving…" : "Go to the scanner"}
        </Button>
      </div>
    </AuthShell>
  );
}
