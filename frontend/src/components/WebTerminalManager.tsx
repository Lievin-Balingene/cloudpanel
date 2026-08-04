import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
  const [output, setOutput] = useState("");
  const [line, setLine] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const preRef = useRef<HTMLPreElement | null>(null);
  const wsUrl = useMemo(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}/ws/terminal/?token=${encodeURIComponent(token || "")}`;
  }, [token]);

  useEffect(() => {
    if (!access?.allowed || !token) return;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      try {
        ws.send(JSON.stringify({ type: "resize", cols: 140, rows: 34 }));
      } catch {
        // noop
      }
    };
    ws.onmessage = (evt) => {
      setOutput((prev) => prev + String(evt.data || ""));
    };
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [access?.allowed, token, wsUrl]);

  useEffect(() => {
    const el = preRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [output]);

  function sendCommand() {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "input", data: `${line}\n` }));
    setLine("");
  }

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
          <div className="vz-panel p-0 overflow-hidden">
            <pre
              ref={preRef}
              className="h-[60vh] overflow-auto bg-black p-3 font-mono text-xs text-green-300"
            >
              {output || "Connexion terminal..."}
            </pre>
            <div className="flex gap-2 border-t border-cp-border p-2">
              <input
                className="vz-input flex-1 font-mono text-sm"
                placeholder="commande..."
                value={line}
                onChange={(e) => setLine(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    sendCommand();
                  }
                }}
              />
              <button className="vz-btn-primary" type="button" disabled={!connected} onClick={sendCommand}>
                Exécuter
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
