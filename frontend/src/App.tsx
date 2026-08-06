import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { WhmShell } from "./layouts/WhmShell";
import { ClientShell } from "./layouts/ClientShell";
import { WhmHomePage } from "./pages/whm/WhmHomePage";
import { WhmPackagesPage } from "./pages/whm/WhmPackagesPage";
import { WhmDnsPage } from "./pages/whm/WhmDnsPage";
import { WhmResourcesPage } from "./pages/whm/WhmResourcesPage";
import { WhmAccountsPage } from "./pages/whm/WhmAccountsPage";
import { WhmCreateAccountPage } from "./pages/whm/WhmCreateAccountPage";
import { WhmAccountCreatedPage } from "./pages/whm/WhmAccountCreatedPage";
import { WhmDomainsPage } from "./pages/whm/WhmDomainsPage";
import { WhmFilesPage } from "./pages/whm/WhmFilesPage";
import { WhmFilesUploadPage } from "./pages/whm/WhmFilesUploadPage";
import { WhmFtpPage } from "./pages/whm/WhmFtpPage";
import { WhmCronPage } from "./pages/whm/WhmCronPage";
import { WhmEmailPage } from "./pages/whm/WhmEmailPage";
import { WhmDatabasesPage } from "./pages/whm/WhmDatabasesPage";
import { WhmPythonPage } from "./pages/whm/WhmPythonPage";
import { WhmNodePage } from "./pages/whm/WhmNodePage";
import { WhmPhpPage } from "./pages/whm/WhmPhpPage";
import { WhmGitPage } from "./pages/whm/WhmGitPage";
import { WhmDockerPage } from "./pages/whm/WhmDockerPage";
import { WhmBackupPage } from "./pages/whm/WhmBackupPage";
import { WhmMonitoringPage } from "./pages/whm/WhmMonitoringPage";
import { WhmFirewallPage } from "./pages/whm/WhmFirewallPage";
import { WhmSecurityPage } from "./pages/whm/WhmSecurityPage";
import { WhmWordPressPage } from "./pages/whm/WhmWordPressPage";
import { WhmKubernetesPage } from "./pages/whm/WhmKubernetesPage";
import { WhmTerminalPage } from "./pages/whm/WhmTerminalPage";
import { WhmServerSetupPage } from "./pages/whm/WhmServerSetupPage";
import { WhmPanelUpdatePage } from "./pages/whm/WhmPanelUpdatePage";
import { WhmRepairsPage } from "./pages/whm/WhmRepairsPage";
import { WhmOlsPage } from "./pages/whm/WhmOlsPage";
import { WhmTransferPage } from "./pages/whm/WhmTransferPage";
import { ClientHomePage } from "./pages/client/ClientHomePage";
import { ClientDnsPage } from "./pages/client/ClientDnsPage";
import { ClientPackagePage } from "./pages/client/ClientPackagePage";
import { ClientDomainsPage } from "./pages/client/ClientDomainsPage";
import { ClientFilesPage } from "./pages/client/ClientFilesPage";
import { ClientFilesUploadPage } from "./pages/client/ClientFilesUploadPage";
import { ClientFtpPage } from "./pages/client/ClientFtpPage";
import { ClientCronPage } from "./pages/client/ClientCronPage";
import { ClientEmailPage } from "./pages/client/ClientEmailPage";
import { ClientDatabasesPage } from "./pages/client/ClientDatabasesPage";
import { ClientPythonPage } from "./pages/client/ClientPythonPage";
import { ClientNodePage } from "./pages/client/ClientNodePage";
import { ClientPhpPage } from "./pages/client/ClientPhpPage";
import { ClientGitPage } from "./pages/client/ClientGitPage";
import { ClientDockerPage } from "./pages/client/ClientDockerPage";
import { ClientBackupPage } from "./pages/client/ClientBackupPage";
import { ClientSecurityPage } from "./pages/client/ClientSecurityPage";
import { ClientWordPressPage } from "./pages/client/ClientWordPressPage";
import { ClientKubernetesPage } from "./pages/client/ClientKubernetesPage";
import { ClientTerminalPage } from "./pages/client/ClientTerminalPage";
import { useAuthStore } from "./stores/auth";
import {
  detectPortalSync,
  homePathFor,
  roleAllowedOnPortal,
} from "./lib/portal";

function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const clearSession = useAuthStore((s) => s.clearSession);
  const mustChange = user?.must_change_password;
  const portal = detectPortalSync();
  const wrongPortal = Boolean(token && user && !roleAllowedOnPortal(user.role, portal));

  if (wrongPortal) {
    clearSession();
    return <Navigate to="/login" replace />;
  }
  if (!token) return <Navigate to="/login" replace />;
  if (mustChange) return <Navigate to="/change-password" replace />;
  return <>{children}</>;
}

function RequireWhm({ children }: { children: ReactNode }) {
  const role = useAuthStore((s) => s.user?.role);
  const portal = detectPortalSync();
  if (portal === "client") return <Navigate to="/panel" replace />;
  if (role === "client") return <Navigate to="/panel" replace />;
  return <>{children}</>;
}

function RequireClient({ children }: { children: ReactNode }) {
  const role = useAuthStore((s) => s.user?.role);
  const portal = detectPortalSync();
  if (portal === "admin") return <Navigate to="/whm" replace />;
  if (role === "administrator" || role === "reseller") {
    return <Navigate to="/whm" replace />;
  }
  return <>{children}</>;
}

function PostLoginRedirect() {
  const role = useAuthStore((s) => s.user?.role);
  const mustChange = useAuthStore((s) => s.user?.must_change_password);
  if (!role) return <Navigate to="/login" replace />;
  if (mustChange) return <Navigate to="/change-password" replace />;
  return <Navigate to={homePathFor(role, detectPortalSync())} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/change-password" element={<ChangePasswordPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <PostLoginRedirect />
          </RequireAuth>
        }
      />
      <Route
        path="/whm"
        element={
          <RequireAuth>
            <RequireWhm>
              <WhmShell />
            </RequireWhm>
          </RequireAuth>
        }
      >
        <Route index element={<WhmHomePage />} />
        <Route path="accounts/create" element={<WhmCreateAccountPage />} />
        <Route path="accounts/created" element={<WhmAccountCreatedPage />} />
        <Route path="accounts" element={<WhmAccountsPage />} />
        <Route path="transfer" element={<WhmTransferPage />} />
        <Route path="packages" element={<WhmPackagesPage />} />
        <Route path="server-setup" element={<WhmServerSetupPage />} />
        <Route path="panel-update" element={<WhmPanelUpdatePage />} />
        <Route path="repairs" element={<WhmRepairsPage />} />
        <Route path="ols" element={<WhmOlsPage />} />
        <Route path="domains" element={<WhmDomainsPage />} />
        <Route path="files" element={<WhmFilesPage />} />
        <Route path="files/upload" element={<WhmFilesUploadPage />} />
        <Route path="ftp" element={<WhmFtpPage />} />
        <Route path="cron" element={<WhmCronPage />} />
        <Route path="email" element={<WhmEmailPage />} />
        <Route path="databases" element={<WhmDatabasesPage />} />
        <Route path="python" element={<WhmPythonPage />} />
        <Route path="node" element={<WhmNodePage />} />
        <Route path="php" element={<WhmPhpPage />} />
        <Route path="wordpress" element={<WhmWordPressPage />} />
        <Route path="kubernetes" element={<WhmKubernetesPage />} />
        <Route path="terminal" element={<WhmTerminalPage />} />
        <Route path="git" element={<WhmGitPage />} />
        <Route path="docker" element={<WhmDockerPage />} />
        <Route path="backups" element={<WhmBackupPage />} />
        <Route path="monitoring" element={<WhmMonitoringPage />} />
        <Route path="firewall" element={<WhmFirewallPage />} />
        <Route path="security" element={<WhmSecurityPage />} />
        <Route path="account-security" element={<ClientSecurityPage />} />
        <Route path="dns" element={<WhmDnsPage />} />
        <Route path="resources" element={<WhmResourcesPage />} />
      </Route>
      <Route
        path="/panel"
        element={
          <RequireAuth>
            <RequireClient>
              <ClientShell />
            </RequireClient>
          </RequireAuth>
        }
      >
        <Route index element={<ClientHomePage />} />
        <Route path="domains" element={<ClientDomainsPage />} />
        <Route path="files" element={<ClientFilesPage />} />
        <Route path="files/upload" element={<ClientFilesUploadPage />} />
        <Route path="ftp" element={<ClientFtpPage />} />
        <Route path="cron" element={<ClientCronPage />} />
        <Route path="email" element={<ClientEmailPage />} />
        <Route path="databases" element={<ClientDatabasesPage />} />
        <Route path="python" element={<ClientPythonPage />} />
        <Route path="node" element={<ClientNodePage />} />
        <Route path="php" element={<ClientPhpPage />} />
        <Route path="wordpress" element={<ClientWordPressPage />} />
        <Route path="kubernetes" element={<ClientKubernetesPage />} />
        <Route path="terminal" element={<ClientTerminalPage />} />
        <Route path="git" element={<ClientGitPage />} />
        <Route path="docker" element={<ClientDockerPage />} />
        <Route path="backups" element={<ClientBackupPage />} />
        <Route path="security" element={<ClientSecurityPage />} />
        <Route path="dns" element={<ClientDnsPage />} />
        <Route path="package" element={<ClientPackagePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
