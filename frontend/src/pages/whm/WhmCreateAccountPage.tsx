import { FormEvent, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Loader2, UserPlus } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { runWithProgress } from "@/stores/operations";
import type { HostingPackage, User } from "@/types";

export type AccountCreatedState = {
  id: number;
  username: string;
  email: string;
  domain: string;
  password: string;
  package_name: string;
  home_directory: string;
  primary_domain: string;
  nameservers: string[];
  public_ip: string;
};

export function WhmCreateAccountPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: packages = [] } = useQuery({
    queryKey: ["packages", "client"],
    queryFn: () => apiRequest<HostingPackage[]>("/packages/?type=client"),
  });
  const { data: serverSetup } = useQuery({
    queryKey: ["server-setup"],
    queryFn: () =>
      apiRequest<{
        nameserver1: string;
        nameserver2: string;
        nameserver3: string;
        nameserver4: string;
        public_ip: string;
      }>("/server-setup/"),
  });

  const [form, setForm] = useState({
    domain: "",
    username: "",
    password: "",
    email: "",
    package_id: "",
    create_welcome_index: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const suggestedUser = useMemo(() => {
    const d = form.domain.trim().toLowerCase();
    if (!d || !d.includes(".")) return "";
    const label = d.split(".")[0].replace(/[^a-z0-9]/g, "").slice(0, 8);
    return label;
  }, [form.domain]);

  const createUser = useMutation({
    mutationFn: async () => {
      const domain = form.domain.trim().toLowerCase();
      const username = (form.username.trim() || suggestedUser).toLowerCase();
      const payload: Record<string, unknown> = {
        email: form.email,
        username,
        password: form.password,
        role: "client",
        domain,
        create_welcome_index: form.create_welcome_index,
      };
      if (form.package_id) payload.package_id = Number(form.package_id);
      const user = await runWithProgress(
        `Création compte · ${username}`,
        () =>
          apiRequest<User>("/auth/users/", {
            method: "POST",
            body: JSON.stringify(payload),
          }),
        {
          tickDetail: (ms) =>
            ms < 2000
              ? "Home + public_html…"
              : ms < 4500
                ? "Domaine principal + DNS…"
                : "Vhost nginx…",
        },
      );
      return { user, domain, username, password: form.password };
    },
    onSuccess: ({ user, domain, username, password }) => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["users"] });
      void qc.invalidateQueries({ queryKey: ["dashboard-overview"] });
      void qc.invalidateQueries({ queryKey: ["domains"] });

      const pkg = packages.find((p) => String(p.id) === form.package_id);
      const ns = [
        serverSetup?.nameserver1,
        serverSetup?.nameserver2,
        serverSetup?.nameserver3,
        serverSetup?.nameserver4,
      ]
        .filter(Boolean)
        .map((n) => String(n).replace(/\.$/, ""));

      const state: AccountCreatedState = {
        id: user.id,
        username: user.username || username,
        email: user.email,
        domain,
        password,
        package_name: pkg?.name || "—",
        home_directory: user.home_directory || "",
        primary_domain: user.primary_domain || domain,
        nameservers: ns,
        public_ip: serverSetup?.public_ip || "",
      };
      navigate("/whm/accounts/created", { state, replace: true });
    },
    onError: (err: Error) => setError(err.message || "Création impossible."),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!form.domain.trim().includes(".")) {
      setError("Indiquez un domaine valide (ex: exemple.com).");
      return;
    }
    createUser.mutate();
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 animate-fade-up">
      <div className="whm-page-head">
        <div className="whm-page-head-bar flex items-center gap-2">
          <UserPlus className="h-4 w-4 text-cp-orange" />
          <h1 className="text-sm font-semibold uppercase tracking-wide">Create a New Account</h1>
        </div>
        <p className="px-4 py-3 text-sm text-cp-muted">
          Comme cPanel : le <strong className="text-cp-text">domaine principal</strong> est
          obligatoire. V-zone crée le home, <code className="font-mono text-xs">public_html</code>,
          la zone DNS et le vhost (OpenLiteSpeed / Nginx). Aucun{" "}
          <code className="font-mono text-xs">index.html</code> n&apos;est créé sauf si vous le
          demandez ci-dessous.
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-cp-danger"
        >
          {error}
        </p>
      )}

      <form className="overflow-hidden rounded-lg border border-cp-border bg-white shadow-panel dark:border-ink-800 dark:bg-ink-950" onSubmit={onSubmit}>
        <div className="border-b border-cp-border bg-cp-orange-soft px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-orange-dark dark:border-ink-800 dark:bg-ink-900 dark:text-cp-orange">
          Domain Information
        </div>

        <div className="whm-form-row">
          <div>
            <p className="whm-form-label">Domain *</p>
            <p className="whm-form-hint">Primary domain for this account</p>
          </div>
          <input
            className="vz-input font-mono text-base"
            placeholder="exemple.com"
            required
            autoFocus
            value={form.domain}
            onChange={(e) => {
              const domain = e.target.value;
              setForm((prev) => ({
                ...prev,
                domain,
                username:
                  !prev.username || prev.username === suggestedUser
                    ? domain.trim().toLowerCase().split(".")[0]?.replace(/[^a-z0-9]/g, "").slice(0, 8) ||
                      prev.username
                    : prev.username,
              }));
            }}
          />
        </div>

        <div className="whm-form-row">
          <div>
            <p className="whm-form-label">Username *</p>
            <p className="whm-form-hint">System / cPanel style (a-z, 0-9)</p>
          </div>
          <input
            className="vz-input font-mono"
            placeholder={suggestedUser || "johndoe"}
            required
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
        </div>

        <div className="whm-form-row">
          <div>
            <p className="whm-form-label">Password *</p>
            <p className="whm-form-hint">Minimum 10 characters</p>
          </div>
          <div className="relative">
            <input
              className="vz-input pr-10 font-mono"
              type={showPassword ? "text" : "password"}
              required
              minLength={10}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-cp-muted hover:text-cp-text"
              onClick={() => setShowPassword((v) => !v)}
              tabIndex={-1}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div className="whm-form-row">
          <div>
            <p className="whm-form-label">Email *</p>
            <p className="whm-form-hint">Contact email for this account</p>
          </div>
          <input
            className="vz-input"
            type="email"
            required
            placeholder="owner@exemple.com"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </div>

        <div className="border-b border-cp-border bg-cp-orange-soft px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-orange-dark dark:border-ink-800 dark:bg-ink-900 dark:text-cp-orange">
          Package
        </div>

        <div className="whm-form-row">
          <div>
            <p className="whm-form-label">Choose a Package</p>
            <p className="whm-form-hint">Resource limits (disk, domains, …)</p>
          </div>
          <select
            className="vz-input"
            value={form.package_id}
            onChange={(e) => setForm({ ...form, package_id: e.target.value })}
          >
            <option value="">— Select a Package —</option>
            {packages.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        <div className="border-b border-cp-border bg-cp-orange-soft px-4 py-2 text-xs font-bold uppercase tracking-wide text-cp-orange-dark dark:border-ink-800 dark:bg-ink-900 dark:text-cp-orange">
          Document Root
        </div>

        <div className="whm-form-row">
          <div>
            <p className="whm-form-label">Page d&apos;accueil</p>
            <p className="whm-form-hint">
              Optionnel — laissez décoché pour un dossier vide (WordPress / OLS)
            </p>
          </div>
          <label className="flex cursor-pointer items-start gap-2 text-sm text-cp-text">
            <input
              type="checkbox"
              className="mt-1"
              checked={form.create_welcome_index}
              onChange={(e) =>
                setForm({ ...form, create_welcome_index: e.target.checked })
              }
            />
            <span>
              Créer <code className="font-mono text-xs">index.html</code> (« Site prêt ») dans{" "}
              <code className="font-mono text-xs">public_html</code>
            </span>
          </label>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 bg-cp-canvas/60 px-4 py-3 dark:bg-ink-900/40">
          <Link to="/whm/accounts" className="vz-btn-ghost">
            Cancel
          </Link>
          <button className="whm-btn-create min-w-[160px]" type="submit" disabled={createUser.isPending}>
            {createUser.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Creating…
              </>
            ) : (
              <>
                <UserPlus className="h-4 w-4" />
                Create
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
