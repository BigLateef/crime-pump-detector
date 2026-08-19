"use client";

import { Card, CardHeader, Button, EmptyState } from "@/components/ui/primitives";
import { useApiData } from "@/lib/useApiData";
import { apiFetch } from "@/lib/api";
import { UserOut } from "@/lib/types";

export default function AdminUsersPage() {
  const { data: users, loading, reload } = useApiData<UserOut[]>("/admin/users");

  async function handleDisable(id: string) {
    await apiFetch(`/admin/users/${id}/disable`, { method: "POST" });
    reload();
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this user? This cannot be undone.")) return;
    await apiFetch(`/admin/users/${id}`, { method: "DELETE" });
    reload();
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-ink">User management</h1>
        <p className="text-sm text-ink-muted">Everyone who has redeemed an invite.</p>
      </div>

      <Card>
        <CardHeader title="All users" />
        {loading && <p className="text-sm text-ink-muted">Loading…</p>}
        {!loading && users && users.length === 0 && (
          <EmptyState title="No users yet" body="Users appear here once they redeem an invite and sign up." />
        )}
        {!loading && users && users.length > 0 && (
          <div className="-mx-4 overflow-x-auto px-4">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-ink-faint">
                <th className="py-2 font-normal">Name</th>
                <th className="py-2 font-normal">Email</th>
                <th className="py-2 font-normal">Role</th>
                <th className="py-2 font-normal">Status</th>
                <th className="py-2 font-normal">Joined</th>
                <th className="py-2 font-normal"></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-base-border">
                  <td className="py-2 text-ink">{u.display_name}</td>
                  <td className="py-2 text-ink-muted">{u.email}</td>
                  <td className="py-2 capitalize text-ink-muted">{u.role}</td>
                  <td className="py-2">
                    <span
                      className={
                        u.status === "active" ? "text-signal-conviction" : "text-ink-faint"
                      }
                    >
                      {u.status}
                    </span>
                  </td>
                  <td className="py-2 text-ink-muted">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="py-2 text-right">
                    {u.status === "active" && (
                      <div className="flex justify-end gap-2">
                        <Button variant="secondary" onClick={() => handleDisable(u.id)}>
                          Disable
                        </Button>
                        <Button variant="danger" onClick={() => handleDelete(u.id)}>
                          Delete
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Card>
    </div>
  );
}
