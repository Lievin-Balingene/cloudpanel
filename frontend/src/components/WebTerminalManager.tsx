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
  const { data: access } = useQuery({
    queryKey: ["terminal-access"],
    queryFn: () => apiRequest<TerminalAccess>("/core/terminal/access/"),
  });
  const [connected, setConnected] = useState(false);
  const terminalRef = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const terminalHostRef = useRef<HTMLDivElement | null>(null);
  const wsUrl = useMemo(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}/ws/terminal/?token=${encodeURIComponent(token || "")}`;
  }, [token]);

  useEffect(() => {
    if (!terminalHostRef.current || terminalRef.current) return;
    const term = new Terminal({
      convertEol: true,
      cursorBlink: true,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
      fontSize: 13,
      lineHeight: 1.25,
      scrollback: 4000,
      theme: {
        background: "#0b1220",
        foreground: "#d8e1ee",
        cursor: "#f59e0b",
      },
    });
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalHostRef.current);
    fitAddon.fit();
    term.focus();
    terminalRef.current = term;
    fitAddonRef.current = fitAddon;
    return () => {
      term.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!access?.allowed || !token) return;
    const term = terminalRef.current;
    const fitAddon = fitAddonRef.current;
    if (!term || !fitAddon) return;
    const ws = new WebSocket(wsUrl);
    let disposeDataHandler: { dispose: () => void } | null = null;
    let resizeObserver: ResizeObserver | null = null;

    const sendResize = () => {
      if (ws.readyState !== WebSocket.OPEN) return;
      fitAddon.fit();
      ws.send(
        JSON.stringify({
          type: "resize",
          cols: term.cols,
          rows: term.rows,
        }),
      );
    };

    ws.onopen = () => {
      setConnected(true);
      term.reset();
      term.writeln("\x1b[1;32mConnected to V-zone terminal.\x1b[0m");
      sendResize();
      disposeDataHandler = term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "input", data }));
        }
      });
      resizeObserver = new ResizeObserver(() => sendResize());
      if (terminalHostRef.current) resizeObserver.observe(terminalHostRef.current);
    };
    ws.onmessage = (evt) => {
      term.write(String(evt.data || ""));
    };
    ws.onclose = () => {
      setConnected(false);
      term.writeln("\r\n\x1b[1;31mDisconnected.\x1b[0m");
    };
    ws.onerror = () => {
      setConnected(false);
      term.writeln("\r\n\x1b[1;31mConnection error.\x1b[0m");
    };
    return () => {
      if (disposeDataHandler) disposeDataHandler.dispose();
      if (resizeObserver) resizeObserver.disconnect();
      ws.close();
    };
  }, [access?.allowed, token, wsUrl]);

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="vz-panel p-4">
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="text-sm text-cp-muted">
          Terminal web sécurisé (PTY) — accès contrôlé par package (option SSH).
        </p>
      </div>

      {!access?.allowed ? (
        <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Accès refusé : {access?.reason || "Votre package n'autorise pas SSH."}
        </div>
      ) : (
        <>
          <div className="vz-panel p-3 text-xs text-cp-muted">
            Utilisateur: <strong>{access.username}</strong> · Home: <strong>{access.home_directory}</strong> ·
            Statut: <strong>{connected ? "connecté" : "déconnecté"}</strong>
          </div>
          <div className="vz-panel overflow-hidden p-0">
            <div className="border-b border-cp-border bg-cp-canvas px-3 py-2 text-xs text-cp-muted">
              Terminal interactif direct (clavier/souris) — double-cliquez pour focus.
            </div>
            <div ref={terminalHostRef} className="vzone-xterm-host h-[62vh] w-full bg-[#0b1220] p-2" />
          </div>
        </>
      )}
    </div>
  );
}
