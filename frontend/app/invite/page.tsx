"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AuthShell } from "@/components/nav/AuthShell";
import { Button, Input } from "@/components/ui/primitives";
import { apiFetch } from "@/lib/api";

export default function InvitePage() {
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<"idle" | "checking" | "invalid">("idle");
  const [recipientLabel, setRecipientLabel] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("checking");
    try {
      const result = await apiFetch<{ valid: boolean; recipient_label: string | null }>(
        "/auth/invite/validate",
        { method: "POST", body: { code }, auth: false }
      );
      if (result.valid) {
        setRecipientLabel(result.recipient_label);
        router.push(`/signup?invite=${encodeURIComponent(code)}`);
      } else {
        setStatus("invalid");
      }
    } catch {
      setStatus("invalid");
    }
  }

  return (
    <AuthShell title="Enter your invite code" subtitle="This platform is private and invite-only.">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          placeholder="K7M4-XP9Q"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          className="text-center font-mono tracking-widest"
          autoFocus
          required
        />
        {status === "invalid" && (
          <p className="text-sm text-signal-danger">Invite code is invalid or expired.</p>
        )}
        <Button type="submit" className="w-full" disabled={status === "checking"}>
          {status === "checking" ? "Checking…" : "Continue"}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-ink-muted">
        Already have an account?{" "}
        <a href="/login" className="text-signal-early hover:underline">
          Log in
        </a>
      </p>
    </AuthShell>
  );
}
