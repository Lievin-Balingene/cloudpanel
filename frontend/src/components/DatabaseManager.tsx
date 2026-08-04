import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  Filter,
  Plus,
  ShieldOff,
  Trash2,
} from "lucide-react";
import { apiRequest } from "@/lib/api";

interface DbOverview {
  databases: number;
  mysql_databases: number;
  postgresql_databases: number;
  users: number;
  privileges: number;
  phpmyadmin_url: string;
  pgadmin_url: string;
  provision_mode: string;
}

interface HostedDatabase {
  id: number;
  name: string;
  engine: string;
  charset: string;
  privilege_count: number;
  is_active: boolean;
}

interface DbUser {
  id: number;
  username: string;
  engine: string;
  host: string;
  is_active: boolean;
  privilege_count: number;
}

interface DbPrivilege {
  id: number;
  database: number;
  database_name: string;
  user: number;
  username: string;
  engine: string;
  privileges: string;
}

type WizardStep = 1 | 2 | 3;

function IconAction({
  label,
  onClick,
  disabled,
  danger,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md border border-transparent transition
        hover:border-cp-border hover:bg-cp-canvas disabled:cursor-not-allowed disabled:opacity-40
        ${danger ? "text-cp-danger hover:bg-red-50" : "text-cp-link hover:text-cp-navy"}`}
    >
      {children}
    </button>
  );
}

export function DatabaseManager({ title }: { title: string }) {
  const qc = useQueryClient();
  const { data: overview } = useQuery({
    queryKey: ["databases-overview"],
    queryFn: () => apiRequest<DbOverview>("/databases/overview/"),
  });
  const { data: databases = [], isLoading } = useQuery({
    queryKey: ["databases"],
    queryFn: () => apiRequest<HostedDatabase[]>("/databases/"),
  });
  const { data: users = [] } = useQuery({
    queryKey: ["database-users"],
    queryFn: () => apiRequest<DbUser[]>("/databases/users/"),
  });
  const { data: privileges = [] } = useQuery({
    queryKey: ["database-privileges"],
    queryFn: () => apiRequest<DbPrivilege[]>("/databases/privileges/"),
  });

  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState<WizardStep>(1);
  const [wizard, setWizard] = useState({
    dbName: "",
    engine: "mysql",
    username: "",
    password: "",
    host: "localhost",
    privileges: "ALL",
  });
  const [error, setError] = useState<string | null>(null);
  const [engineFilter, setEngineFilter] = useState<"all" | "mysql" | "postgresql">("all");
  const [confirm, setConfirm] = useState<{
    title: string;
    message: string;
    onConfirm: () => void;
  } | null>(null);

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ["databases-overview"] });
    void qc.invalidateQueries({ queryKey: ["databases"] });
    void qc.invalidateQueries({ queryKey: ["database-users"] });
    void qc.invalidateQueries({ queryKey: ["database-privileges"] });
  };

  const removeDb = useMutation({
    mutationFn: (id: number) => apiRequest(`/databases/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const removeUser = useMutation({
    mutationFn: (id: number) => apiRequest(`/databases/users/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const openPhpMyAdmin = useMutation({
    mutationFn: (userId: number) =>
      apiRequest<{ url: string }>("/databases/phpmyadmin/sso/", {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      }),
    onSuccess: (data) => {
      setError(null);
      window.open(data.url, "_blank", "noopener,noreferrer");
    },
    onError: (err: Error) => setError(err.message),
  });

  const removeGrant = useMutation({
    mutationFn: (id: number) => apiRequest(`/databases/privileges/${id}/`, { method: "DELETE" }),
    onSuccess: () => {
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const visibleDatabases =
    engineFilter === "all" ? databases : databases.filter((d) => d.engine === engineFilter);
  const visibleUsers = engineFilter === "all" ? users : users.filter((u) => u.engine === engineFilter);
  const visiblePrivileges =
    engineFilter === "all" ? privileges : privileges.filter((p) => p.engine === engineFilter);

  const createWizard = useMutation({
    mutationFn: async () => {
      const db = await apiRequest<HostedDatabase>("/databases/", {
        method: "POST",
        body: JSON.stringify({
          name: wizard.dbName,
          engine: wizard.engine,
        }),
      });
      const user = await apiRequest<DbUser>("/databases/users/", {
        method: "POST",
        body: JSON.stringify({
          username: wizard.username,
          password: wizard.password,
          engine: wizard.engine,
          host: wizard.engine === "postgresql" ? "localhost" : wizard.host,
        }),
      });
      await apiRequest("/databases/privileges/", {
        method: "POST",
        body: JSON.stringify({
          database_id: db.id,
          user_id: user.id,
          privileges: wizard.privileges,
        }),
      });
    },
    onSuccess: () => {
      setError(null);
      setWizardOpen(false);
      setWizardStep(1);
      setWizard({
        dbName: "",
        engine: "mysql",
        username: "",
        password: "",
        host: "localhost",
        privileges: "ALL",
      });
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  function askConfirm(title: string, message: string, onConfirm: () => void) {
    setConfirm({ title, message, onConfirm });
  }

  const engineLabel =
    engineFilter === "all" ? "All Databases" : engineFilter === "mysql" ? "MySQL Databases" : "PostgreSQL Databases";
  const provisionBadgeClass =
    overview?.provision_mode === "live"
      ? "bg-emerald-100 text-emerald-800"
      : overview?.provision_mode === "auto"
        ? "bg-amber-100 text-amber-800"
        : "bg-slate-100 text-slate-700";

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{title}</h1>
            <p className="text-sm text-cp-muted">
              Manage MySQL and PostgreSQL databases, users, and privileges.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded border border-cp-border bg-cp-canvas px-2 py-1 text-cp-muted">
                {engineLabel}
              </span>
              <span className={`rounded px-2 py-1 font-semibold uppercase ${provisionBadgeClass}`}>
                Mode: {overview?.provision_mode ?? "unknown"}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-cp-muted" />
            <select
              className="vz-input min-w-40"
              value={engineFilter}
              onChange={(e) => setEngineFilter(e.target.value as "all" | "mysql" | "postgresql")}
            >
              <option value="all">Tous les moteurs</option>
              <option value="mysql">MySQL</option>
              <option value="postgresql">PostgreSQL</option>
            </select>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="vz-btn-primary"
              type="button"
              onClick={() => {
                setWizardOpen(true);
                setWizardStep(1);
              }}
            >
              <Plus className="h-4 w-4" />
              Créer une base de données
            </button>
            {overview?.phpmyadmin_url && (
              <a
                className="vz-btn-primary"
                href={overview.phpmyadmin_url}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink className="h-4 w-4" />
                phpMyAdmin
              </a>
            )}
            {overview?.pgadmin_url && (
              <a
                className="vz-btn-ghost"
                href={overview.pgadmin_url}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink className="h-4 w-4" />
                pgAdmin
              </a>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Bases", value: overview?.databases ?? "—" },
          { label: "MySQL", value: overview?.mysql_databases ?? "—" },
          { label: "PostgreSQL", value: overview?.postgresql_databases ?? "—" },
          { label: "Utilisateurs", value: overview?.users ?? "—" },
        ].map((card) => (
          <div key={card.label} className="vz-panel p-3">
            <p className="text-xs font-semibold uppercase text-cp-muted">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold text-cp-orange">{card.value}</p>
          </div>
        ))}
      </div>

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>
      )}

      <div className="vz-panel overflow-x-auto">
        <div className="border-b border-cp-border bg-cp-header px-3 py-2 text-xs font-semibold uppercase tracking-wide text-white">
          Current Databases
        </div>
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Nom</th>
              <th className="px-3 py-2">Moteur</th>
              <th className="px-3 py-2">Charset</th>
              <th className="px-3 py-2">Privs</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-3 py-4" colSpan={5}>
                  Chargement…
                </td>
              </tr>
            )}
            {visibleDatabases.map((db) => (
              <tr key={db.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-mono text-xs">{db.name}</td>
                <td className="px-3 py-2">{db.engine}</td>
                <td className="px-3 py-2">{db.charset}</td>
                <td className="px-3 py-2">{db.privilege_count}</td>
                <td className="px-3 py-2">
                  <div className="flex justify-end gap-1">
                    <IconAction
                      label={`Supprimer ${db.name}`}
                      danger
                      onClick={() =>
                        askConfirm("Supprimer la base", `Supprimer définitivement « ${db.name} » ?`, () =>
                          removeDb.mutate(db.id),
                        )
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                    </IconAction>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && visibleDatabases.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  No databases found for this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="vz-panel overflow-x-auto">
        <div className="border-b border-cp-border bg-cp-header px-3 py-2 text-xs font-semibold uppercase tracking-wide text-white">
          Current Users
        </div>
        <table className="min-w-full text-left text-sm">
          <thead className="bg-cp-canvas text-xs uppercase text-cp-muted dark:bg-ink-900">
            <tr>
              <th className="px-3 py-2">Utilisateur</th>
              <th className="px-3 py-2">Moteur</th>
              <th className="px-3 py-2">Host</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visibleUsers.map((u) => (
              <tr key={u.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-mono text-xs">{u.username}</td>
                <td className="px-3 py-2">{u.engine}</td>
                <td className="px-3 py-2">{u.host}</td>
                <td className="px-3 py-2">
                  <div className="flex justify-end gap-1">
                    {u.engine === "mysql" && (
                      <IconAction
                        label={`Ouvrir phpMyAdmin (${u.username})`}
                        disabled={openPhpMyAdmin.isPending}
                        onClick={() => openPhpMyAdmin.mutate(u.id)}
                      >
                        <ExternalLink className="h-4 w-4" />
                      </IconAction>
                    )}
                    <IconAction
                      label={`Supprimer ${u.username}`}
                      danger
                      onClick={() =>
                        askConfirm(
                          "Supprimer l'utilisateur",
                          `Supprimer définitivement « ${u.username} » ?`,
                          () => removeUser.mutate(u.id),
                        )
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                    </IconAction>
                  </div>
                </td>
              </tr>
            ))}
            {visibleUsers.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={4}>
                  No SQL users found for this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="vz-panel overflow-x-auto">
        <div className="border-b border-cp-border bg-cp-header px-3 py-2 text-xs font-semibold uppercase tracking-wide text-white">
          Current Privileges
        </div>
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase text-cp-muted">
              <th className="px-3 py-2">User</th>
              <th className="px-3 py-2">Base</th>
              <th className="px-3 py-2">Droits</th>
              <th className="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visiblePrivileges.map((p) => (
              <tr key={p.id} className="border-t border-cp-border dark:border-ink-800">
                <td className="px-3 py-2 font-mono text-xs">{p.username}</td>
                <td className="px-3 py-2 font-mono text-xs">{p.database_name}</td>
                <td className="px-3 py-2">{p.privileges}</td>
                <td className="px-3 py-2">
                  <div className="flex justify-end gap-1">
                    <IconAction
                      label={`Révoquer ${p.username} → ${p.database_name}`}
                      danger
                      disabled={removeGrant.isPending}
                      onClick={() =>
                        askConfirm(
                          "Révoquer les privilèges",
                          `Retirer les droits de « ${p.username} » sur « ${p.database_name} » ?`,
                          () => removeGrant.mutate(p.id),
                        )
                      }
                    >
                      <ShieldOff className="h-4 w-4" />
                    </IconAction>
                  </div>
                </td>
              </tr>
            ))}
            {visiblePrivileges.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={4}>
                  No privileges found for this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {confirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded border border-cp-border bg-white p-4 shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <h2 className="text-base font-semibold">{confirm.title}</h2>
            <p className="mt-2 text-sm text-cp-muted">{confirm.message}</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="vz-btn-ghost" onClick={() => setConfirm(null)}>
                Annuler
              </button>
              <button
                type="button"
                className="vz-btn-primary bg-cp-danger hover:opacity-90"
                onClick={() => {
                  const fn = confirm.onConfirm;
                  setConfirm(null);
                  fn();
                }}
              >
                Confirmer
              </button>
            </div>
          </div>
        </div>
      )}

      {wizardOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-2xl rounded border border-cp-border bg-white shadow-xl dark:border-ink-700 dark:bg-ink-950">
            <div className="flex items-center justify-between border-b border-cp-border bg-cp-header px-4 py-2 text-white dark:border-ink-800">
              <h2 className="text-sm font-semibold uppercase tracking-wide">Database Wizard</h2>
              <button
                type="button"
                className="rounded px-2 py-1 text-xs hover:bg-white/15"
                onClick={() => {
                  setWizardOpen(false);
                  setWizardStep(1);
                }}
              >
                Fermer
              </button>
            </div>
            <div className="p-4">
              <p className="mb-3 text-xs text-cp-muted">
                Follow steps below to create a database, create a user, and assign privileges.
              </p>

            <div className="mb-4 flex items-center gap-2 text-xs">
              {[1, 2, 3].map((n) => (
                <div
                  key={n}
                  className={`rounded-md px-2.5 py-1 font-semibold ${
                    wizardStep === n
                      ? "bg-cp-orange text-white"
                      : wizardStep > n
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-cp-canvas text-cp-muted"
                  }`}
                >
                  Step {n}
                </div>
              ))}
            </div>

            {wizardStep === 1 && (
              <div className="space-y-3">
                <p className="text-sm text-cp-muted">Database Name and Engine.</p>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-cp-muted">Database Name</span>
                  <input
                  className="vz-input"
                  placeholder="ex: app"
                  value={wizard.dbName}
                  onChange={(e) => setWizard({ ...wizard, dbName: e.target.value })}
                />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-cp-muted">Engine</span>
                <select
                  className="vz-input"
                  value={wizard.engine}
                  onChange={(e) => setWizard({ ...wizard, engine: e.target.value })}
                >
                  <option value="mysql">MySQL</option>
                  <option value="postgresql">PostgreSQL</option>
                </select>
                </label>
                <div className="flex justify-end">
                  <button
                    type="button"
                    className="vz-btn-primary"
                    disabled={!wizard.dbName.trim()}
                    onClick={() => setWizardStep(2)}
                  >
                    Suivant
                  </button>
                </div>
              </div>
            )}

            {wizardStep === 2 && (
              <div className="space-y-3">
                <p className="text-sm text-cp-muted">Database User and Password.</p>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-cp-muted">Username</span>
                  <input
                  className="vz-input"
                  placeholder="utilisateur"
                  value={wizard.username}
                  onChange={(e) => setWizard({ ...wizard, username: e.target.value })}
                />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-cp-muted">Password</span>
                  <input
                  className="vz-input"
                  type="password"
                  minLength={8}
                  placeholder="mot de passe"
                  value={wizard.password}
                  onChange={(e) => setWizard({ ...wizard, password: e.target.value })}
                />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-cp-muted">Host</span>
                  <input
                  className="vz-input"
                  placeholder="host"
                  disabled={wizard.engine === "postgresql"}
                  value={wizard.host}
                  onChange={(e) => setWizard({ ...wizard, host: e.target.value })}
                />
                </label>
                <div className="flex justify-between">
                  <button type="button" className="vz-btn-ghost" onClick={() => setWizardStep(1)}>
                    Précédent
                  </button>
                  <button
                    type="button"
                    className="vz-btn-primary"
                    disabled={!wizard.username.trim() || wizard.password.length < 8}
                    onClick={() => setWizardStep(3)}
                  >
                    Suivant
                  </button>
                </div>
              </div>
            )}

            {wizardStep === 3 && (
              <div className="space-y-3">
                <p className="text-sm text-cp-muted">Assign User Privileges.</p>
                <select
                  className="vz-input"
                  value={wizard.privileges}
                  onChange={(e) => setWizard({ ...wizard, privileges: e.target.value })}
                >
                  <option value="ALL">ALL PRIVILEGES</option>
                  <option value="WRITE">WRITE</option>
                  <option value="READ">READ</option>
                </select>
                <div className="rounded border border-cp-border bg-cp-canvas px-3 py-2 text-xs text-cp-muted">
                  Database: <strong>{wizard.dbName || "—"}</strong> · User: <strong>{wizard.username || "—"}</strong>{" "}
                  · Engine: <strong>{wizard.engine}</strong>
                </div>
                <div className="flex justify-between">
                  <button type="button" className="vz-btn-ghost" onClick={() => setWizardStep(2)}>
                    Précédent
                  </button>
                  <button
                    type="button"
                    className="vz-btn-primary"
                    disabled={createWizard.isPending}
                    onClick={() => createWizard.mutate()}
                  >
                    Save Changes
                  </button>
                </div>
              </div>
            )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
