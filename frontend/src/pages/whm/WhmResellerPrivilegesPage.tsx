import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, RotateCcw, Save, Shield, Users } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import type { User } from "@/types";

type PrivilegeGroup = {
  group: string;
  privileges: { code: string; label: string }[];
};

type ResellerAclPayload = {
  user_id: number;
  username: string;
  privileges: string[];
  enforce_ownership: boolean;
  allow_overselling: boolean;
  notes: string;
  catalog: PrivilegeGroup[];
  defaults: string[];
};

export function WhmResellerPrivilegesPage() {
  const me = useAuthStore((s) => s.user);
  const fetchMe = useAuthStore((s) => s.fetchMe);
  const isAdmin = me?.role === "administrator";
  const [params, setParams] = useSearchParams();
  const selectedId = Number(params.get("user") || 0) || null;
  const qc = useQueryClient();
  const [draft, setDraft] = useState<string[] | null>(null);
  const [enforceOwn, setEnforceOwn] = useState(true);
  const [oversell, setOversell] = useState(false);
  const [notes, setNotes] = useState("");
  const [msg, setMsg] = useState("");

  const { data: users = [] } = useQuery({
    queryKey: ["whm-resellers"],
    queryFn: async () => {
      const rows = await apiRequest<User[]>("/auth/users/");
      return rows.filter((u) => u.role === "reseller");
    },
    enabled: isAdmin,
  });

  const activeId = selectedId || (isAdmin ? users[0]?.id : me?.id) || null;

  const { data: acl, isLoading } = useQuery({
    queryKey: ["reseller-acl", activeId],
    queryFn: () => apiRequest<ResellerAclPayload>(`/auth/reseller-privileges/${activeId}/`),
    enabled: Boolean(activeId),
  });

  const privileges = draft ?? acl?.privileges ?? [];
  const catalog = acl?.catalog ?? [];

  useEffect(() => {
    if (acl && draft === null) {
      setEnforceOwn(acl.enforce_ownership);
      setOversell(acl.allow_overselling);
      setNotes(acl.notes || "");
    }
  }, [acl, draft]);

  const saveMut = useMutation({
    mutationFn: () =>
      apiRequest(`/auth/reseller-privileges/${activeId}/`, {
        method: "PUT",
        body: JSON.stringify({
          privileges,
          enforce_ownership: enforceOwn,
          allow_overselling: oversell,
          notes,
        }),
      }),
    onSuccess: async () => {
      setMsg("Privileges enregistres.");
      setDraft(null);
      await qc.invalidateQueries({ queryKey: ["reseller-acl", activeId] });
      if (me?.id === activeId) await fetchMe();
    },
    onError: (e: Error) => setMsg(e.message),
  });

  function toggle(code: string) {
    if (!isAdmin) return;
    const set = new Set(privileges);
    if (set.has(code)) set.delete(code);
    else set.add(code);
    setDraft([...set].sort());
  }

  function selectAllGroup(group: PrivilegeGroup) {
    if (!isAdmin) return;
    const set = new Set(privileges);
    group.privileges.forEach((p) => set.add(p.code));
    setDraft([...set].sort());
  }

  function clearGroup(group: PrivilegeGroup) {
    if (!isAdmin) return;
    const drop = new Set(group.privileges.map((p) => p.code));
    setDraft(privileges.filter((c) => !drop.has(c)));
  }

  function applyDefaults() {
    if (!isAdmin || !acl) return;
    setDraft([...(acl.defaults || [])]);
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="rounded-lg border border-cp-border bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-cp-orange">
              Account Functions
            </p>
            <h1 className="mt-1 flex items-center gap-2 text-xl font-semibold text-cp-navy">
              <Shield className="h-5 w-5 text-cp-orange" />
              Edit Reseller Privileges
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-cp-muted">
              Controlez exactement ce qu&apos;un revendeur peut faire dans WHM, comme sur cPanel.
              Les comptes clients crees via ce revendeur restent rattaches a son organisation
              (proprietaire = revendeur).
            </p>
          </div>
          <Link
            to="/whm/accounts"
            className="inline-flex items-center gap-1.5 rounded-md border border-cp-border px-3 py-1.5 text-sm text-cp-link hover:bg-cp-canvas"
          >
            <Users className="h-3.5 w-3.5" />
            List Accounts
          </Link>
        </div>
      </header>

      {isAdmin && (
        <div className="rounded-lg border border-cp-border bg-white p-4 shadow-sm">
          <label className="block text-xs font-medium text-cp-muted">Revendeur</label>
          <select
            className="mt-1 w-full max-w-md rounded-md border border-cp-border bg-white px-3 py-2 text-sm"
            value={activeId ?? ""}
            onChange={(e) => {
              setDraft(null);
              setParams(e.target.value ? { user: e.target.value } : {});
            }}
          >
            {users.length === 0 && <option value="">Aucun revendeur</option>}
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.username} — {u.email}
              </option>
            ))}
          </select>
        </div>
      )}

      {!activeId && (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Aucun revendeur selectionne. Creez d&apos;abord un compte avec le role{" "}
          <strong>reseller</strong> et un package revendeur.
        </p>
      )}

      {activeId && isLoading && (
        <p className="text-sm text-cp-muted">Chargement des privileges…</p>
      )}

      {acl && (
        <>
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-cp-border bg-[#f7fafc] px-4 py-3 text-sm">
            <span className="font-semibold text-cp-navy">{acl.username}</span>
            <span className="text-cp-muted">
              {privileges.length} privilege{privileges.length > 1 ? "s" : ""} actif
              {privileges.length > 1 ? "s" : ""}
            </span>
            {isAdmin && (
              <div className="ml-auto flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={applyDefaults}
                  className="inline-flex items-center gap-1 rounded-md border border-cp-border bg-white px-2.5 py-1.5 text-xs hover:bg-cp-canvas"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Defaults cPanel
                </button>
                <button
                  type="button"
                  disabled={saveMut.isPending}
                  onClick={() => saveMut.mutate()}
                  className="inline-flex items-center gap-1 rounded-md bg-cp-orange px-3 py-1.5 text-xs font-semibold text-white hover:brightness-105 disabled:opacity-60"
                >
                  <Save className="h-3.5 w-3.5" />
                  Save
                </button>
              </div>
            )}
          </div>

          {msg && (
            <p
              className={`rounded border px-3 py-2 text-sm ${
                msg.includes("enregistres")
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : "border-red-200 bg-red-50 text-cp-danger"
              }`}
            >
              {msg}
            </p>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            {catalog.map((group) => {
              const enabled = group.privileges.filter((p) => privileges.includes(p.code)).length;
              const isRootGroup = group.group.startsWith("Server");
              return (
                <section
                  key={group.group}
                  className={`rounded-lg border bg-white shadow-sm ${
                    isRootGroup ? "border-amber-300/80" : "border-cp-border"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 border-b border-cp-border px-4 py-2.5">
                    <div>
                      <h2 className="text-sm font-semibold text-cp-navy">{group.group}</h2>
                      <p className="text-[11px] text-cp-muted">
                        {enabled}/{group.privileges.length} selected
                        {isRootGroup ? " · reserve root par defaut" : ""}
                      </p>
                    </div>
                    {isAdmin && (
                      <div className="flex gap-1">
                        <button
                          type="button"
                          className="rounded px-2 py-0.5 text-[11px] text-cp-link hover:bg-cp-canvas"
                          onClick={() => selectAllGroup(group)}
                        >
                          All
                        </button>
                        <button
                          type="button"
                          className="rounded px-2 py-0.5 text-[11px] text-cp-muted hover:bg-cp-canvas"
                          onClick={() => clearGroup(group)}
                        >
                          None
                        </button>
                      </div>
                    )}
                  </div>
                  <ul className="divide-y divide-cp-border/70">
                    {group.privileges.map((p) => {
                      const on = privileges.includes(p.code);
                      return (
                        <li key={p.code}>
                          <label
                            className={`flex cursor-pointer items-start gap-3 px-4 py-2.5 transition hover:bg-cp-canvas/60 ${
                              !isAdmin ? "cursor-default" : ""
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="mt-0.5"
                              checked={on}
                              disabled={!isAdmin}
                              onChange={() => toggle(p.code)}
                            />
                            <span className="min-w-0 flex-1">
                              <span className="block text-sm font-medium text-cp-navy">
                                {p.label}
                              </span>
                              <span className="font-mono text-[10px] text-cp-muted">{p.code}</span>
                            </span>
                            {on && <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" />}
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>

          <section className="rounded-lg border border-cp-border bg-white p-4 shadow-sm">
            <h2 className="text-sm font-semibold text-cp-navy">Security & ownership</h2>
            <p className="mt-1 text-xs text-cp-muted">
              Isolation des comptes crees via ce revendeur (owner.parent = revendeur).
            </p>
            <div className="mt-3 space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={enforceOwn}
                  disabled={!isAdmin}
                  onChange={(e) => {
                    setEnforceOwn(e.target.checked);
                    if (isAdmin) setDraft(privileges);
                  }}
                />
                Enforce ownership (recommandé — style cPanel)
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={oversell}
                  disabled={!isAdmin}
                  onChange={(e) => {
                    setOversell(e.target.checked);
                    if (isAdmin) setDraft(privileges);
                  }}
                />
                Allow overselling (packages clients au-dela du pool)
              </label>
              {isAdmin && (
                <label className="block text-xs text-cp-muted">
                  Notes
                  <input
                    className="mt-1 w-full rounded-md border border-cp-border px-3 py-2 text-sm"
                    value={notes}
                    onChange={(e) => {
                      setNotes(e.target.value);
                      setDraft(privileges);
                    }}
                    placeholder="Optionnel"
                  />
                </label>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
