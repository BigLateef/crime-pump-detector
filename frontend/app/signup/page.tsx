"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthShell } from "@/components/nav/AuthShell";
import { Button, Input } from "@/components/ui/primitives";
import { apiFetch, ApiError } from "@/lib/api";
import { setTokens } from "@/lib/auth";

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  );
}

function SignupForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [inviteCode, setInviteCode] = useState(params.get("invite") || "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const data = await apiFetch<{ access_token: string; refresh_token: string }>("/auth/signup", {
        method: "POST",
        auth: false,
        body: { invite_code: inviteCode, email, password, display_name: displayName },
      });
      setTokens(data.access_token, data.refresh_token);
      router.push("/onboarding");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Your invite code is required to finish signing up.">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Input
          placeholder="Invite code"
          value={inviteCode}
          onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
          className="font-mono tracking-widest"
          required
        />
        <Input
          placeholder="Display name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          required
        />
        <Input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          type="password"
          placeholder="Password (min 10 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={10}
          required
        />
        {error && <p className="text-sm text-signal-danger">{error}</p>}
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
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
