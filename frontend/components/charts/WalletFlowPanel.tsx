"use client";

import { StatBox } from "@/components/ui/primitives";

interface WalletFlowSummary {
  earlyWallets: number;
  smartMoneyWallets: number;
  deployerLinkedWallets: number;
  coordinatedWallets: number;
}

/**
 * Per Section 6, wallet addresses are never exposed — only category
 * counts ("early wallets", "smart-money activity", "deployer-linked
 * wallets", "coordinated wallets"). Backend doesn't populate this yet (see
 * the holder/wallet-data gap noted in adapters/base.py), so this renders
 * an honest empty state until a real wallet-tracking source is wired in.
 */
export function WalletFlowPanel({ summary }: { summary: WalletFlowSummary | null }) {
  if (!summary) {
    return (
      <div className="flex h-40 flex-col items-center justify-center text-center">
        <p className="text-sm text-ink-muted">Wallet-flow data isn&apos;t available yet.</p>
        <p className="mt-1 max-w-sm text-xs text-ink-faint">
          Smart-money and wallet-cluster tracking needs a paid on-chain indexer — not wired in yet. When it
          is, this panel will only ever show category counts, never raw wallet addresses.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      <StatBox label="Early wallets" value={summary.earlyWallets} />
      <StatBox label="Smart-money activity" value={summary.smartMoneyWallets} />
      <StatBox label="Deployer-linked" value={summary.deployerLinkedWallets} />
      <StatBox label="Coordinated wallets" value={summary.coordinatedWallets} />
    </div>
  );
}
