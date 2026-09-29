import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/LoginPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { WhmShell } from "./layouts/WhmShell";
import { ClientShell } from "./layouts/ClientShell";
import { WhmHomePage } from "./pages/whm/WhmHomePage";
import { WhmPackagesPage } from "./pages/whm/WhmPackagesPage";
import { WhmPackageCreatePage } from "./pages/whm/WhmPackageCreatePage";
import { WhmPackageEditPage } from "./pages/whm/WhmPackageEditPage";
import { WhmPulsePage } from "./pages/whm/WhmPulsePage";
import { WhmDnsPage } from "./pages/whm/WhmDnsPage";
import { WhmResourcesPage } from "./pages/whm/WhmResourcesPage";
import { WhmAccountsPage } from "./pages/whm/WhmAccountsPage";
import { WhmCreateAccountPage } from "./pages/whm/WhmCreateAccountPage";
import { WhmAccountCreatedPage } from "./pages/whm/WhmAccountCreatedPage";
import { WhmDomainsPage } from "./pages/whm/WhmDomainsPage";
import { WhmFilesPage } from "./pages/whm/WhmFilesPage";
import { WhmFilesUploadPage } from "./pages/whm/WhmFilesUploadPage";
import { WhmFilesEditPage } from "./pages/whm/WhmFilesEditPage";
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
import { WhmSmtpRestrictionsPage } from "./pages/whm/WhmSmtpRestrictionsPage";
import { WhmWordPressPage } from "./pages/whm/WhmWordPressPage";
import { WhmKubernetesPage } from "./pages/whm/WhmKubernetesPage";
import { WhmTerminalPage } from "./pages/whm/WhmTerminalPage";
import { WhmServerSetupPage } from "./pages/whm/WhmServerSetupPage";
import { WhmPanelUpdatePage } from "./pages/whm/WhmPanelUpdatePage";
import { WhmRepairsPage } from "./pages/whm/WhmRepairsPage";
import { WhmOlsPage } from "./pages/whm/WhmOlsPage";
import { WhmTransferPage } from "./pages/whm/WhmTransferPage";
import { WhmResellerPrivilegesPage } from "./pages/whm/WhmResellerPrivilegesPage";
import { WhmAiOpsPage } from "./pages/whm/WhmAiOpsPage";
import { WhmIpFunctionsPage } from "./pages/whm/WhmIpFunctionsPage";
import { WhmTweakSettingsPage } from "./pages/whm/WhmTweakSettingsPage";
import { ClientHomePage } from "./pages/client/ClientHomePage";
import { ClientDnsPage } from "./pages/client/ClientDnsPage";
import { ClientPackagePage } from "./pages/client/ClientPackagePage";
import { ClientPulsePage } from "./pages/client/ClientPulsePage";
import { ClientDomainsPage } from "./pages/client/ClientDomainsPage";
import { ClientFilesPage } from "./pages/client/ClientFilesPage";
import { ClientFilesUploadPage } from "./pages/client/ClientFilesUploadPage";
import { ClientFilesEditPage } from "./pages/client/ClientFilesEditPage";
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
import { ClientTerminalPage } from "./pages/client/ClientTerminalPage";
import { ClientDiskUsagePage } from "./pages/client/ClientDiskUsagePage";
import { ClientDirectoryPrivacyPage } from "./pages/client/ClientDirectoryPrivacyPage";
import { ClientSshKeysPage } from "./pages/client/ClientSshKeysPage";
import { ClientMetricsPage } from "./pages/client/ClientMetricsPage";
import { ClientIpBlockerPage } from "./pages/client/ClientIpBlockerPage";
import { ClientPreferencesPage } from "./pages/client/ClientPreferencesPage";
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
  // Sur le port Client, tout le monde (y compris reseller) reste en cPanel
  if (portal === "client") return <Navigate to="/panel" replace />;
  if (role === "client") return <Navigate to="/panel" replace />;
  return <>{children}</>;
}

function RequireClient({ children }: { children: ReactNode }) {
  const role = useAuthStore((s) => s.user?.role);
  const portal = detectPortalSync();
  // Sur le port Admin, rediriger vers WHM
  if (portal === "admin") return <Navigate to="/whm" replace />;
  // Root admin n'utilise pas le cPanel ici
  if (role === "administrator") return <Navigate to="/whm" replace />;
  // client + reseller OK (style cPanel)
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
        <Route path="packages/create" element={<WhmPackageCreatePage />} />
        <Route path="packages/:id/edit" element={<WhmPackageEditPage />} />
        <Route path="packages" element={<WhmPackagesPage />} />
        <Route path="pulse" element={<WhmPulsePage />} />
        <Route path="resellers" element={<WhmResellerPrivilegesPage />} />
        <Route path="server-setup" element={<WhmServerSetupPage />} />
        <Route path="tweak-settings" element={<WhmTweakSettingsPage />} />
        <Route path="ip-functions" element={<WhmIpFunctionsPage />} />
        <Route path="ai-ops" element={<WhmAiOpsPage />} />
        <Route path="panel-update" element={<WhmPanelUpdatePage />} />
        <Route path="repairs" element={<WhmRepairsPage />} />
        <Route path="ols" element={<WhmOlsPage />} />
        <Route path="domains" element={<WhmDomainsPage />} />
        <Route path="files" element={<WhmFilesPage />} />
        <Route path="files/upload" element={<WhmFilesUploadPage />} />
        <Route path="files/edit" element={<WhmFilesEditPage />} />
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
        <Route path="smtp-restrictions" element={<WhmSmtpRestrictionsPage />} />
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
        <Route path="files/edit" element={<ClientFilesEditPage />} />
        <Route path="ftp" element={<ClientFtpPage />} />
        <Route path="cron" element={<ClientCronPage />} />
        <Route path="email" element={<ClientEmailPage />} />
        <Route path="databases" element={<ClientDatabasesPage />} />
        <Route path="python" element={<ClientPythonPage />} />
        <Route path="node" element={<ClientNodePage />} />
        <Route path="php" element={<ClientPhpPage />} />
        <Route path="wordpress" element={<ClientWordPressPage />} />
        <Route path="kubernetes" element={<Navigate to="/panel" replace />} />
        <Route path="terminal" element={<ClientTerminalPage />} />
        <Route path="git" element={<ClientGitPage />} />
        <Route path="docker" element={<ClientDockerPage />} />
        <Route path="backups" element={<ClientBackupPage />} />
        <Route path="security" element={<ClientSecurityPage />} />
        <Route path="disk-usage" element={<ClientDiskUsagePage />} />
        <Route path="directory-privacy" element={<ClientDirectoryPrivacyPage />} />
        <Route path="ssh-keys" element={<ClientSshKeysPage />} />
        <Route path="metrics" element={<ClientMetricsPage />} />
        <Route path="ip-blocker" element={<ClientIpBlockerPage />} />
        <Route path="preferences" element={<ClientPreferencesPage />} />
        <Route path="dns" element={<ClientDnsPage />} />
        <Route path="package" element={<ClientPackagePage />} />
        <Route path="pulse" element={<ClientPulsePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
