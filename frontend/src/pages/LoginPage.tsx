import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  detectPortalSync,
  homePathFor,
  resolvePortal,
  roleAllowedOnPortal,
  type PortalKind,
} from "@/lib/portal";
import { useAuthStore } from "@/stores/auth";
import { AdminLoginView } from "./login/AdminLoginView";
import { ClientLoginView } from "./login/ClientLoginView";
import { SharedLoginChooser } from "./login/SharedLoginChooser";

export function LoginPage() {
  const token = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const clearSession = useAuthStore((s) => s.clearSession);
  const [portal, setPortal] = useState<PortalKind>(() => detectPortalSync());
  const [sharedChoice, setSharedChoice] = useState<"admin" | "client" | null>(null);

  useEffect(() => {
    void resolvePortal().then(setPortal);
  }, []);

  useEffect(() => {
    if (token && user && !roleAllowedOnPortal(user.role, portal)) {
      clearSession();
    }
  }, [token, user, portal, clearSession]);

  useEffect(() => {
    const label =
      portal === "admin" || sharedChoice === "admin"
        ? "V-zone Admin"
        : portal === "client" || sharedChoice === "client"
          ? "V-zone Hosting"
          : "V-zone";
    document.title = `Connexion · ${label}`;
  }, [portal, sharedChoice]);

  if (token && user && roleAllowedOnPortal(user.role, portal)) {
    if (user.must_change_password) {
      return <Navigate to="/change-password" replace />;
    }
    return <Navigate to={homePathFor(user.role, portal)} replace />;
  }

  const backToChooser =
    portal === "shared" ? () => setSharedChoice(null) : undefined;

  if (portal === "admin") return <AdminLoginView />;
  if (portal === "client") return <ClientLoginView />;

  if (sharedChoice === "admin") {
    return <AdminLoginView onBack={backToChooser} />;
  }
  if (sharedChoice === "client") {
    return <ClientLoginView onBack={backToChooser} />;
  }
  return <SharedLoginChooser onChoose={setSharedChoice} />;
}
