import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  FileText,
  KeyRound,
  LogIn,
  PauseCircle,
  Pencil,
  PlayCircle,
  Search,
  Trash2,
  UserPlus,
} from "lucide-react";
import { apiRequest, apiRequestPaginated } from "@/lib/api";
import { cpanelPortalUrl } from "@/lib/portal";
import { canCreateResellerAccount } from "@/lib/resellerAcl";
import { useAuthStore } from "@/stores/auth";
import { AccountLogsModal } from "@/components/AccountLogsModal";
import { IconAction } from "@/components/ui/IconAction";
import { Modal } from "@/components/ui/Modal";
import type { HostingPackage, User } from "@/types";

type ResetPasswordResult = {
  user_id: number;
  username: string;
  temporary_password: string;
  must_change_password: boolean;
  sessions_revoked: number;
  shown_once: boolean;
  message: string;
};

type EditForm = {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
  role: string;
  package_id: string;
  is_active: boolean;
};

type AccountRow = User & {
  date_joined?: string;
  package_name?: string;
  disk_used_mb?: number | null;
  disk_limit_mb?: number | null;
};

function formatDate(iso?: string) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("fr-FR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function formatDisk(u: AccountRow) {
  const used = u.disk_used_mb;
  const limit = u.disk_limit_mb;
  const unlimited = u.quota?.unlimited_disk || limit == null;
  const usedLabel = used == null ? "…" : used < 1024 ? `${Math.round(used)} MB` : `${(used / 1024).toFixed(1)} GB`;
  if (unlimited) return `${usedLabel} / ∞`;
  const limLabel = limit < 1024 ? `${limit} MB` : `${(limit / 1024).toFixed(1)} GB`;
  return `${usedLabel} / ${limLabel}`;
}

function diskPct(u: AccountRow): number | null {
  if (u.disk_used_mb == null || u.disk_limit_mb == null || u.disk_limit_mb <= 0) return null;
  if (u.quota?.unlimited_disk) return null;
  return Math.min(100, Math.round((u.disk_used_mb / u.disk_limit_mb) * 100));
}

function SkeletonRows({ rows = 8 }: { rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i} className="border-t border-cp-border/60 dark:border-ink-800">
          {Array.from({ length: 9 }).map((__, j) => (
            <td key={j} className="px-3 py-3">
              <div
                className="h-3.5 animate-pulse rounded bg-cp-canvas dark:bg-ink-800"
                style={{ width: `${55 + ((i + j) % 5) * 8}%` }}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function WhmAccountsPage() {
  const qc = useQueryClient();
  const me = useAuthStore((s) => s.user);
  const allowResellerType = canCreateResellerAccount(me?.role, me?.reseller_privileges);
  const isAdmin = me?.role === "administrator";

  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "suspended">("all");
  const [roleFilter, setRoleFilter] = useState<"all" | "client" | "reseller">("all");
  /** "" = tous · "root" = comptes root · id = comptes d'un reseller */
  const [resellerFilter, setResellerFilter] = useState("");
  const [editing, setEditing] = useState<AccountRow | null>(null);
  const [editForm, setEditForm] = useState<EditForm | null>(null);
  const [logsFor, setLogsFor] = useState<AccountRow | null>(null);
  const [resetFor, setResetFor] = useState<AccountRow | null>(null);
  const [resetConfirm, setResetConfirm] = useState("");
  const [resetResult, setResetResult] = useState<ResetPasswordResult | null>(null);
  const [copiedPwd, setCopiedPwd] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setQDebounced(q.trim()), 280);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    setPage(1);
  }, [qDebounced, statusFilter, pageSize, roleFilter, resellerFilter]);

  // Liste légère des revendeurs pour le filtre (admin only)
  const { data: resellersPage } = useQuery({
    queryKey: ["users", "resellers-options"],
    queryFn: () =>
      apiRequestPaginated<AccountRow>("/auth/users/?role=reseller&page_size=200&page=1"),
    enabled: isAdmin,
    staleTime: 60_000,
  });
  const resellers = resellersPage?.results ?? [];

  const listPath = useMemo(() => {
    const params = new URLSearchParams();
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    if (qDebounced) params.set("q", qDebounced);
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (roleFilter !== "all") params.set("role", roleFilter);
    // Filtre reseller : si on choisit un reseller précis, on liste ses clients
    // (sauf si role=reseller — alors on ignore parent pour éviter une liste vide)
    if (isAdmin && resellerFilter && roleFilter !== "reseller") {
      params.set("parent", resellerFilter);
      if (resellerFilter !== "root") params.set("include_reseller", "1");
    }
    return `/auth/users/?${params.toString()}`;
  }, [page, pageSize, qDebounced, statusFilter, roleFilter, resellerFilter, isAdmin]);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["users", listPath],
    queryFn: () => apiRequestPaginated<AccountRow>(listPath),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });

  const users = data?.results ?? [];
  const total = data?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const { data: packages = [] } = useQuery({
    queryKey: ["packages", "client"],
    queryFn: () => apiRequest<HostingPackage[]>("/packages/?type=client"),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!editing) {
      setEditForm(null);
      return;
    }
    setEditForm({
      email: editing.email,
      first_name: editing.first_name || "",
      last_name: editing.last_name || "",
      password: "",
      role: editing.role,
      package_id: "",
      is_active: editing.is_active && !editing.is_suspended,
    });
  }, [editing]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["users"] });
    void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
  };

  const updateUser = useMutation({
    mutationFn: async () => {
      if (!editing || !editForm) return;
      const payload: Record<string, unknown> = {
        email: editForm.email,
        first_name: editForm.first_name,
        last_name: editForm.last_name,
        role: editForm.role,
        is_active: editForm.is_active,
        is_suspended: !editForm.is_active,
      };
      if (editForm.password.trim()) payload.password = editForm.password.trim();
      await apiRequest(`/auth/users/${editing.id}/`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (editForm.package_id) {
        await apiRequest("/packages/assign/", {
          method: "POST",
          body: JSON.stringify({
            user_id: editing.id,
            package_id: Number(editForm.package_id),
          }),
        });
      }
    },
    onSuccess: () => {
      setError(null);
      setEditing(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Modification impossible."),
  });

  const suspendUser = useMutation({
    mutationFn: ({ id, suspended }: { id: number; suspended: boolean }) =>
      apiRequest(`/auth/users/${id}/suspend/`, {
        method: "POST",
        body: JSON.stringify({ suspended }),
      }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Action impossible."),
  });

  const deleteUser = useMutation({
    mutationFn: (id: number) => apiRequest(`/auth/users/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      if (editing) setEditing(null);
      invalidate();
    },
    onError: (err: Error) => setError(err.message || "Suppression impossible."),
  });

  const loginAs = useMutation({
    mutationFn: (id: number) =>
      apiRequest<{ handoff: string; username: string }>("/auth/users/" + id + "/login-as/", {
        method: "POST",
        body: "{}",
      }),
    onSuccess: (data) => {
      setError(null);
      const url = cpanelPortalUrl(`/panel/sso?handoff=${encodeURIComponent(data.handoff)}`);
      const win = window.open(url, "_blank", "noopener,noreferrer");
      if (!win) {
        setError("Autorisez les pop-ups pour ouvrir le panneau client (Login as).");
      }
    },
    onError: (err: Error) => setError(err.message || "Login as impossible."),
  });

  const resetPassword = useMutation({
    mutationFn: ({ id, confirm_username }: { id: number; confirm_username: string }) =>
      apiRequest<ResetPasswordResult>(`/auth/users/${id}/reset-password/`, {
        method: "POST",
        body: JSON.stringify({ confirm_username }),
      }),
    onSuccess: (data) => {
      setError(null);
      setResetResult(data);
      setResetConfirm("");
      setCopiedPwd(false);
    },
    onError: (err: Error) => setError(err.message || "Réinitialisation impossible."),
  });

  function openReset(u: AccountRow) {
    setError(null);
    setResetResult(null);
    setResetConfirm("");
    setCopiedPwd(false);
    setResetFor(u);
  }

  function closeReset() {
    setResetFor(null);
    setResetResult(null);
    setResetConfirm("");
    setCopiedPwd(false);
  }

  async function copyTemporaryPassword() {
    if (!resetResult?.temporary_password) return;
    try {
      await navigator.clipboard.writeText(resetResult.temporary_password);
      setCopiedPwd(true);
      window.setTimeout(() => setCopiedPwd(false), 2000);
    } catch {
      setError("Copie presse-papiers impossible — sélectionnez le mot de passe manuellement.");
    }
  }

  function onSaveEdit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    updateUser.mutate();
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="whm-page-head">
        <div className="whm-page-head-bar flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-sm font-semibold uppercase tracking-wide">List Accounts</h1>
            <p className="text-[11px] text-white/70">
              {isFetching && !isLoading ? "Actualisation…" : `${total.toLocaleString("fr-FR")} compte(s)`}
            </p>
          </div>
          <Link to="/whm/accounts/create" className="whm-btn-create !py-1.5 text-xs">
            <UserPlus className="h-3.5 w-3.5" />
            Create a New Account
          </Link>
        </div>
        <div className="flex flex-wrap items-center gap-2 px-4 py-3">
          <div className="relative min-w-[200px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cp-muted" />
            <input
              className="vz-input pl-9"
              placeholder="Search user, domain, email…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select
            className="vz-input !w-auto !py-1.5 text-xs"
            value={roleFilter}
            onChange={(e) => {
              const next = e.target.value as typeof roleFilter;
              setRoleFilter(next);
              // Afficher uniquement les resellers → reset filtre propriétaire
              if (next === "reseller") setResellerFilter("");
            }}
          >
            <option value="all">All types</option>
            <option value="client">Clients only</option>
            <option value="reseller">Resellers only</option>
          </select>
          {isAdmin && roleFilter !== "reseller" && (
            <select
              className="vz-input !w-auto max-w-[14rem] !py-1.5 text-xs"
              value={resellerFilter}
              onChange={(e) => setResellerFilter(e.target.value)}
              title="Filtrer par propriétaire / revendeur"
            >
              <option value="">All owners</option>
              <option value="root">Root (no reseller)</option>
              {resellers.map((r) => (
                <option key={r.id} value={String(r.id)}>
                  Reseller: {r.username}
                  {r.is_suspended ? " (suspended)" : ""}
                </option>
              ))}
            </select>
          )}
          <select
            className="vz-input !w-auto !py-1.5 text-xs"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          >
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </select>
          <select
            className="vz-input !w-auto !py-1.5 text-xs"
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
          >
            <option value={25}>25 / page</option>
            <option value={50}>50 / page</option>
            <option value={100}>100 / page</option>
            <option value={200}>200 / page</option>
          </select>
        </div>
      </div>

      {editing && editForm && (
        <form
          className="overflow-hidden rounded-lg border border-cp-link/30 bg-white shadow-panel dark:border-ink-700 dark:bg-ink-950"
          onSubmit={onSaveEdit}
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cp-border bg-cp-header px-4 py-2 text-white dark:border-ink-800">
            <h2 className="text-sm font-semibold">
              Modify Account · <span className="font-mono">{editing.username}</span>
            </h2>
            <button type="button" className="text-sm text-white/80 hover:text-white" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
          <div className="grid gap-3 p-4 md:grid-cols-3">
            <input
              className="vz-input md:col-span-2"
              type="email"
              required
              value={editForm.email}
              onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
            />
            <select
              className="vz-input"
              value={allowResellerType ? editForm.role : "client"}
              disabled={!allowResellerType}
              onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
            >
              <option value="client">Client</option>
              {allowResellerType && <option value="reseller">Reseller</option>}
            </select>
            <input
              className="vz-input"
              placeholder="First name"
              value={editForm.first_name}
              onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
            />
            <input
              className="vz-input"
              placeholder="Last name"
              value={editForm.last_name}
              onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
            />
            <div className="space-y-1">
              <input
                className="vz-input"
                type="password"
                minLength={10}
                placeholder="New password (optional)"
                value={editForm.password}
                onChange={(e) => setEditForm({ ...editForm, password: e.target.value })}
              />
              <p className="text-[10px] text-cp-muted">
                Prefer the secure Reset password action (key icon). Setting a password here also forces change at next login.
              </p>
            </div>
            <select
              className="vz-input"
              value={editForm.package_id}
              onChange={(e) => setEditForm({ ...editForm, package_id: e.target.value })}
            >
              <option value="">Package (unchanged)…</option>
              {packages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={editForm.is_active}
                onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
              />
              Active
            </label>
            <button className="whm-btn-create" type="submit" disabled={updateUser.isPending}>
              Save
            </button>
          </div>
        </form>
      )}

      {error && (
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">
          {error}
        </p>
      )}

      <div className="vz-table-wrap overflow-hidden rounded-lg border border-cp-border bg-white shadow-panel dark:border-ink-800 dark:bg-ink-950">
        <table className="min-w-[56rem] w-full text-left text-sm">
          <thead className="sticky top-0 z-[1] bg-cp-canvas text-[11px] uppercase tracking-wide text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2.5">Domain</th>
              <th className="px-3 py-2.5">User</th>
              <th className="px-3 py-2.5">Contact</th>
              <th className="px-3 py-2.5">Package</th>
              <th className="px-3 py-2.5">Owner</th>
              <th className="px-3 py-2.5">Created</th>
              <th className="px-3 py-2.5">Disk used</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <SkeletonRows rows={Math.min(pageSize, 10)} />}
            {!isLoading &&
              users.map((u) => {
                const suspended = Boolean(u.is_suspended);
                const pct = diskPct(u);
                return (
                  <tr
                    key={u.id}
                    className={`border-t transition dark:border-ink-800 ${
                      suspended
                        ? "border-red-200/80 bg-red-50/90 text-red-950 hover:bg-red-100/90 dark:border-red-900/50 dark:bg-red-950/35 dark:text-red-100 dark:hover:bg-red-950/50"
                        : "border-cp-border/80 hover:bg-cp-orange-soft/35 dark:hover:bg-ink-900/50"
                    }`}
                  >
                    <td className="px-3 py-2">
                      {u.primary_domain ? (
                        <a
                          href={`http://${u.primary_domain}`}
                          target="_blank"
                          rel="noreferrer"
                          className={`inline-flex max-w-[12rem] items-center gap-1 truncate font-mono text-xs hover:underline ${
                            suspended ? "text-red-700 dark:text-red-300" : "text-cp-link"
                          }`}
                        >
                          {u.primary_domain}
                          <ExternalLink className="h-3 w-3 shrink-0 opacity-70" />
                        </a>
                      ) : (
                        <span className="text-cp-muted">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{u.username}</div>
                      <div className="text-[10px] capitalize text-cp-muted">{u.role}</div>
                    </td>
                    <td className="max-w-[10rem] truncate px-3 py-2 text-xs text-cp-muted" title={u.email}>
                      {u.email}
                    </td>
                    <td className="px-3 py-2 text-xs">{u.package_name || "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs text-cp-muted">
                      {u.owner_label || u.parent_username || "root"}
                      {isAdmin && u.role === "reseller" && (
                        <Link
                          to={`/whm/resellers?user=${u.id}`}
                          className="ml-1.5 text-cp-link hover:underline"
                          title="Edit Reseller Privileges"
                        >
                          ACL
                        </Link>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-[11px] text-cp-muted">
                      {formatDate(u.date_joined)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="text-[11px] font-medium tabular-nums">{formatDisk(u)}</div>
                      {pct != null && (
                        <div className="mt-1 h-1 w-20 overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
                          <div
                            className={`h-full rounded-full ${
                              pct >= 90 ? "bg-cp-danger" : pct >= 75 ? "bg-amber-500" : "bg-emerald-500"
                            }`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                          suspended
                            ? "bg-red-600 text-white"
                            : u.is_active
                              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                              : "bg-cp-canvas text-cp-muted"
                        }`}
                      >
                        {suspended ? "suspended" : u.is_active ? "active" : "inactive"}
                      </span>
                    </td>
                    <td className="px-2 py-1.5">
                      <div className="flex flex-wrap items-center justify-end gap-0.5">
                        {u.role !== "administrator" && (
                          <IconAction
                            label="Login to cPanel / AngaPanel"
                            tone="accent"
                            size="sm"
                            disabled={loginAs.isPending}
                            onClick={() => loginAs.mutate(u.id)}
                          >
                            <LogIn className="h-3.5 w-3.5" />
                          </IconAction>
                        )}
                        {u.role !== "administrator" && (
                          <IconAction
                            label="View domain logs"
                            tone="info"
                            size="sm"
                            onClick={() => setLogsFor(u)}
                          >
                            <FileText className="h-3.5 w-3.5" />
                          </IconAction>
                        )}
                        {u.role !== "administrator" && (
                          <IconAction
                            label="Reset password (secure)"
                            tone="warning"
                            size="sm"
                            onClick={() => openReset(u)}
                          >
                            <KeyRound className="h-3.5 w-3.5" />
                          </IconAction>
                        )}
                        <IconAction label="Modify" tone="info" size="sm" onClick={() => setEditing(u)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </IconAction>
                        <IconAction
                          label={suspended ? "Unsuspend" : "Suspend"}
                          tone={suspended ? "success" : "warning"}
                          size="sm"
                          onClick={() => suspendUser.mutate({ id: u.id, suspended: !suspended })}
                        >
                          {suspended ? (
                            <PlayCircle className="h-3.5 w-3.5" />
                          ) : (
                            <PauseCircle className="h-3.5 w-3.5" />
                          )}
                        </IconAction>
                        <IconAction
                          label="Terminate"
                          danger
                          size="sm"
                          onClick={() => {
                            if (
                              window.confirm(
                                `Delete account « ${u.username} » and its home directory? This cannot be undone.`,
                              )
                            ) {
                              deleteUser.mutate(u.id);
                            }
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </IconAction>
                      </div>
                    </td>
                  </tr>
                );
              })}
            {!isLoading && users.length === 0 && (
              <tr>
                <td className="px-3 py-10 text-center text-cp-muted" colSpan={9}>
                  No accounts.{" "}
                  <Link to="/whm/accounts/create" className="text-cp-link hover:underline">
                    Create a New Account
                  </Link>
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {totalPages > 1 && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-cp-border px-3 py-2 text-xs dark:border-ink-800">
            <span className="text-cp-muted">
              Page {page} / {totalPages} · {(page - 1) * pageSize + 1}–
              {Math.min(page * pageSize, total)} of {total.toLocaleString("fr-FR")}
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                className="vz-btn-ghost vz-btn-sm"
                disabled={page <= 1 || isFetching}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Prev
              </button>
              <button
                type="button"
                className="vz-btn-ghost vz-btn-sm"
                disabled={page >= totalPages || isFetching}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {logsFor && (
        <AccountLogsModal
          userId={logsFor.id}
          username={logsFor.username}
          onClose={() => setLogsFor(null)}
        />
      )}

      {resetFor && (
        <Modal
          title="Reset password"
          subtitle={`Secure reset for « ${resetFor.username} »`}
          onClose={closeReset}
        >
          {!resetResult ? (
            <div className="space-y-3">
              <p className="text-sm text-cp-text">
                A strong temporary password will be generated server-side. All active sessions for this
                account will be revoked, and the user must change the password at next login.
              </p>
              <ul className="list-inside list-disc text-xs text-cp-muted space-y-1">
                <li>Password never emailed (shown once here only)</li>
                <li>Contact Manager notified without the secret</li>
                <li>Type the username below to confirm</li>
              </ul>
              <label className="block space-y-1">
                <span className="text-xs font-medium text-cp-muted">
                  Confirm username <span className="font-mono text-cp-text">{resetFor.username}</span>
                </span>
                <input
                  className="vz-input w-full font-mono"
                  autoComplete="off"
                  autoFocus
                  spellCheck={false}
                  value={resetConfirm}
                  onChange={(e) => setResetConfirm(e.target.value)}
                  placeholder={resetFor.username}
                />
              </label>
              {error && <p className="text-sm text-cp-danger">{error}</p>}
              <div className="flex justify-end gap-2 pt-1">
                <button type="button" className="vz-btn-ghost" onClick={closeReset}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="vz-btn-primary"
                  disabled={
                    resetPassword.isPending ||
                    resetConfirm.trim() !== resetFor.username
                  }
                  onClick={() => {
                    setError(null);
                    resetPassword.mutate({
                      id: resetFor.id,
                      confirm_username: resetConfirm.trim(),
                    });
                  }}
                >
                  {resetPassword.isPending ? "Resetting…" : "Reset password"}
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="rounded-md border border-amber-300/80 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
                Shown once — copy now and give it to the account owner out-of-band. It will not be
                displayed again.
              </p>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-cp-muted">
                  Temporary password
                </p>
                <div className="mt-1 flex items-stretch gap-1">
                  <code className="flex-1 break-all rounded-md border border-cp-border bg-cp-canvas px-3 py-2 font-mono text-sm dark:border-ink-700 dark:bg-ink-900">
                    {resetResult.temporary_password}
                  </code>
                  <button
                    type="button"
                    className="vz-btn-ghost shrink-0 px-2"
                    onClick={() => void copyTemporaryPassword()}
                    title="Copy"
                  >
                    {copiedPwd ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <p className="text-xs text-cp-muted">
                Sessions revoked: {resetResult.sessions_revoked}. Force password change:{" "}
                {resetResult.must_change_password ? "yes" : "no"}.
              </p>
              <div className="flex justify-end">
                <button type="button" className="vz-btn-primary" onClick={closeReset}>
                  Done
                </button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
