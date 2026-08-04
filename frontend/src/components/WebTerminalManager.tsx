import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { apiRequest } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

interface TerminalAccess {
  allowed: boolean;
  reason: string;
  home_directory: string;
  username: string;
}

export function WebTerminalManager({ title }: { title: string }) {
  const token = useAuthStore((s) => s.accessToken);
  const { data: access, isLoading } = useQuery({
    queryKey: ["terminal-access"],
    queryFn: () => apiRequest<TerminalAccess>("/core/terminal/access/"),
  });
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState("Initialisation…");
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const terminalHostRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const wsUrl = useMemo(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}/ws/terminal/?token=${encodeURIComponent(token || "")}`;
  }, [token]);

  useEffect(() => {
    if (!access?.allowed || !token || !terminalHostRef.current) return;

    const host = terminalHostRef.current;
    host.innerHTML = "";

    const term = new Terminal({
      convertEol: true,
      cursorBlink: true,
      cursorStyle: "block",
      disableStdin: false,
      allowProposedApi: true,
      fontFamily: "Consolas, 'Courier New', ui-monospace, monospace",
      fontSize: 14,
      lineHeight: 1.2,
      scrollback: 5000,
      theme: {
        background: "#111111",
        foreground: "#f0f0f0",
        cursor: "#f0f0f0",
        selectionBackground: "#444444",
      },
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(host);
    fitAddon.fit();
    term.focus();
    terminalRef.current = term;
    fitAddonRef.current = fitAddon;
    setStatus("Connexion…");

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    let disposed = false;
    let resizeObserver: ResizeObserver | null = null;
    let dataDisposable: { dispose: () => void } | null = null;

    const sendResize = () => {
      if (disposed || ws.readyState !== WebSocket.OPEN) return;
      try {
        fitAddon.fit();
      } catch {
        // ignore fit races during unmount
      }
      ws.send(
        JSON.stringify({
          type: "resize",
          cols: term.cols,
          rows: term.rows,
        }),
      );
    };

    dataDisposable = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    ws.onopen = () => {
      if (disposed) return;
      setConnected(true);
      setStatus("Connecté — tapez directement dans le terminal");
      term.clear();
      sendResize();
      window.setTimeout(() => {
        sendResize();
        term.focus();
      }, 50);
    };

    ws.onmessage = (evt) => {
      if (disposed) return;
      term.write(String(evt.data || ""));
    };

    ws.onclose = () => {
      if (disposed) return;
      setConnected(false);
      setStatus("Déconnecté");
      term.writeln("\r\n\x1b[1;31m[session fermée]\x1b[0m");
    };

    ws.onerror = () => {
      if (disposed) return;
      setConnected(false);
      setStatus("Erreur de connexion");
      term.writeln("\r\n\x1b[1;31m[erreur WebSocket]\x1b[0m");
    };

    resizeObserver = new ResizeObserver(() => sendResize());
    resizeObserver.observe(host);
    window.addEventListener("resize", sendResize);

    return () => {
      disposed = true;
      window.removeEventListener("resize", sendResize);
      if (resizeObserver) resizeObserver.disconnect();
      if (dataDisposable) dataDisposable.dispose();
      try {
        ws.close();
      } catch {
        // noop
      }
      wsRef.current = null;
      term.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
      setConnected(false);
    };
  }, [access?.allowed, token, wsUrl]);

  function focusTerminal() {
    terminalRef.current?.focus();
  }

  return (
    <div className="space-y-3 animate-fade-up">
      <div className="vz-panel overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cp-border bg-cp-header px-4 py-2 text-white">
          <div>
            <h1 className="text-sm font-semibold uppercase tracking-wide">{title}</h1>
            <p className="text-[11px] text-white/80">
              Terminal interactif (comme cPanel) — saisie clavier directe, pas de champ commande.
            </p>
          </div>
          <div className="text-xs text-white/90">
            {access?.username ? (
              <>
                {access.username}
                <span className="mx-1 opacity-50">·</span>
                {connected ? "en ligne" : "hors ligne"}
              </>
            ) : null}
          </div>
        </div>

        {isLoading && (
          <p className="px-4 py-3 text-sm text-cp-muted">Vérification des droits SSH…</p>
        )}

        {!isLoading && !access?.allowed && (
          <div className="m-4 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Accès refusé : {access?.reason || "Votre package n'autorise pas SSH."}
          </div>
        )}

        {access?.allowed && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cp-border bg-cp-canvas px-3 py-1.5 text-xs text-cp-muted">
              <span>
                Home: <strong className="text-cp-text">{access.home_directory}</strong>
                <span className="mx-1">·</span>
                {status}
              </span>
              <button type="button" className="vz-btn-ghost !px-2 !py-1 text-xs" onClick={focusTerminal}>
                Focus terminal
              </button>
            </div>
            <div
              ref={terminalHostRef}
              className="vzone-xterm-host h-[68vh] w-full cursor-text bg-[#111111] p-2 outline-none"
              onClick={focusTerminal}
              onMouseDown={focusTerminal}
              role="application"
              aria-label="Terminal SSH interactif"
              tabIndex={0}
            />
          </>
        )}
      </div>
    </div>
  );
}
