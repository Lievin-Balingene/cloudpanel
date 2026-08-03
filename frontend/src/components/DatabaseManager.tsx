import { FormEvent, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Database,
  ExternalLink,
  ShieldOff,
  Trash2,
  UserPlus,
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

  const [dbForm, setDbForm] = useState({ name: "", engine: "mysql" });
  const [userForm, setUserForm] = useState({
    username: "",
    password: "",
    engine: "mysql",
    host: "localhost",
  });
  const [grantForm, setGrantForm] = useState({
    database_id: 0,
    user_id: 0,
    privileges: "ALL",
  });
  const [error, setError] = useState<string | null>(null);
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

  const createDb = useMutation({
    mutationFn: () =>
      apiRequest("/databases/", { method: "POST", body: JSON.stringify(dbForm) }),
    onSuccess: () => {
      setDbForm({ name: "", engine: "mysql" });
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const createUser = useMutation({
    mutationFn: () =>
      apiRequest("/databases/users/", { method: "POST", body: JSON.stringify(userForm) }),
    onSuccess: () => {
      setUserForm({ username: "", password: "", engine: "mysql", host: "localhost" });
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

  const createGrant = useMutation({
    mutationFn: (payload: typeof grantForm) =>
      apiRequest("/databases/privileges/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      setError(null);
      invalidateAll();
    },
    onError: (err: Error) => setError(err.message),
  });

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

  const selectedDbId = grantForm.database_id || databases[0]?.id || 0;
  const selectedUserId = grantForm.user_id || users[0]?.id || 0;

  function onCreateDb(e: FormEvent) {
    e.preventDefault();
    createDb.mutate();
  }

  function onCreateUser(e: FormEvent) {
    e.preventDefault();
    createUser.mutate();
  }

  function onGrant(e: FormEvent) {
    e.preventDefault();
    if (!selectedDbId || !selectedUserId) {
      setError("Sélectionnez une base et un utilisateur.");
      return;
    }
    const payload = {
      ...grantForm,
      database_id: selectedDbId,
      user_id: selectedUserId,
    };
    setGrantForm(payload);
    createGrant.mutate(payload);
  }

  function askConfirm(title: string, message: string, onConfirm: () => void) {
    setConfirm({ title, message, onConfirm });
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{title}</h1>
            <p className="text-sm text-cp-muted">
              MySQL/MariaDB et PostgreSQL — bases, utilisateurs et privilèges.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
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

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Bases", value: overview?.databases ?? "—" },
          { label: "MySQL", value: overview?.mysql_databases ?? "—" },
          { label: "PostgreSQL", value: overview?.postgresql_databases ?? "—" },
          { label: "Utilisateurs", value: overview?.users ?? "—" },
        ].map((card) => (
          <div key={card.label} className="vz-panel p-4">
            <p className="text-xs font-semibold uppercase text-cp-muted">{card.label}</p>
            <p className="mt-1 text-2xl font-semibold text-cp-orange">{card.value}</p>
          </div>
        ))}
      </div>

      {error && (
        <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger">{error}</p>
      )}

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-4" onSubmit={onCreateDb}>
        <input
          className="vz-input md:col-span-2"
          placeholder="nom (ex: app)"
          required
          value={dbForm.name}
          onChange={(e) => setDbForm({ ...dbForm, name: e.target.value })}
        />
        <select
          className="vz-input"
          value={dbForm.engine}
          onChange={(e) => setDbForm({ ...dbForm, engine: e.target.value })}
        >
          <option value="mysql">MySQL</option>
          <option value="postgresql">PostgreSQL</option>
        </select>
        <button className="vz-btn-primary" type="submit" disabled={createDb.isPending}>
          <Database className="h-4 w-4" />
          Créer base
        </button>
      </form>

      <div className="vz-panel overflow-x-auto">
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
            {databases.map((db) => (
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
            {!isLoading && databases.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={5}>
                  Aucune base.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-5" onSubmit={onCreateUser}>
        <input
          className="vz-input"
          placeholder="utilisateur"
          required
          value={userForm.username}
          onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
        />
        <input
          className="vz-input"
          type="password"
          placeholder="mot de passe"
          required
          minLength={8}
          value={userForm.password}
          onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
        />
        <select
          className="vz-input"
          value={userForm.engine}
          onChange={(e) => setUserForm({ ...userForm, engine: e.target.value })}
        >
          <option value="mysql">MySQL</option>
          <option value="postgresql">PostgreSQL</option>
        </select>
        <input
          className="vz-input"
          placeholder="host"
          value={userForm.host}
          onChange={(e) => setUserForm({ ...userForm, host: e.target.value })}
        />
        <button className="vz-btn-primary" type="submit" disabled={createUser.isPending}>
          <UserPlus className="h-4 w-4" />
          Créer user
        </button>
      </form>

      <div className="vz-panel overflow-x-auto">
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
            {users.map((u) => (
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
            {users.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={4}>
                  Aucun utilisateur SQL.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <form className="vz-panel grid gap-2 p-4 md:grid-cols-4" onSubmit={onGrant}>
        <select
          className="vz-input"
          value={selectedDbId}
          onChange={(e) => setGrantForm({ ...grantForm, database_id: Number(e.target.value) })}
        >
          <option value={0}>Base…</option>
          {databases.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <select
          className="vz-input"
          value={selectedUserId}
          onChange={(e) => setGrantForm({ ...grantForm, user_id: Number(e.target.value) })}
        >
          <option value={0}>User…</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.username}
            </option>
          ))}
        </select>
        <select
          className="vz-input"
          value={grantForm.privileges}
          onChange={(e) => setGrantForm({ ...grantForm, privileges: e.target.value })}
        >
          <option value="ALL">ALL</option>
          <option value="WRITE">WRITE</option>
          <option value="READ">READ</option>
        </select>
        <button className="vz-btn-primary" type="submit" disabled={createGrant.isPending}>
          Accorder
        </button>
      </form>

      <div className="vz-panel overflow-x-auto">
        <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-xs font-semibold uppercase text-cp-muted dark:border-ink-800 dark:bg-ink-900">
          Privilèges
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
            {privileges.map((p) => (
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
            {privileges.length === 0 && (
              <tr>
                <td className="px-3 py-4 text-cp-muted" colSpan={4}>
                  Aucun privilège.
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
    </div>
  );
}
