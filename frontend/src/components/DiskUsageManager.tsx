import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Folder, HardDrive, Home, RefreshCw } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { EmptyState, PageHeader } from "@/components/ui/PageChrome";

interface DiskNode {
  name: string;
  path: string;
  is_dir: boolean;
  size_bytes: number;
  children?: DiskNode[];
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} o`;
  const units = ["Ko", "Mo", "Go", "To"];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; value >= 1024 && index < units.length; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} ${unit}`;
}

function UsageNode({
  node,
  maxSize,
  depth = 0,
  onOpen,
}: {
  node: DiskNode;
  maxSize: number;
  depth?: number;
  onOpen: (path: string) => void;
}) {
  const percent = maxSize ? Math.max(2, (node.size_bytes / maxSize) * 100) : 0;
  return (
    <>
      <button
        type="button"
        className="group flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-cp-canvas/70 dark:hover:bg-ink-900/60"
        style={{ paddingLeft: `${16 + depth * 22}px` }}
        onClick={() => node.is_dir && onOpen(node.path)}
        disabled={!node.is_dir}
      >
        <Folder className="h-4 w-4 shrink-0 text-cp-orange" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <span className="truncate text-sm font-medium text-cp-text">{node.name}</span>
            <span className="shrink-0 text-xs tabular-nums text-cp-muted">
              {formatBytes(node.size_bytes)}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-cp-canvas dark:bg-ink-800">
            <div className="h-full rounded-full bg-cp-orange" style={{ width: `${percent}%` }} />
          </div>
        </div>
        {node.is_dir && <ChevronRight className="h-4 w-4 text-cp-muted group-hover:text-cp-text" />}
      </button>
      {node.children?.map((child) => (
        <UsageNode
          key={child.path}
          node={child}
          maxSize={maxSize}
          depth={depth + 1}
          onOpen={onOpen}
        />
      ))}
    </>
  );
}

export function DiskUsageManager({ title }: { title: string }) {
  const [path, setPath] = useState("");
  const query = useQuery({
    queryKey: ["disk-usage", path],
    queryFn: () =>
      apiRequest<DiskNode[]>(
        `/files/disk-usage/?path=${encodeURIComponent(path)}&depth=2`,
      ),
  });
  const nodes = query.data ?? [];
  const total = nodes.reduce((sum, node) => sum + node.size_bytes, 0);
  const maxSize = Math.max(...nodes.map((node) => node.size_bytes), 0);
  const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";

  return (
    <div className="space-y-4 animate-fade-up">
      <PageHeader
        title={title}
        subtitle="Visualisez l’espace occupé par chaque dossier et explorez votre répertoire personnel."
        stats={[{ label: "Taille affichée", value: formatBytes(total) }]}
        actions={
          <button type="button" className="vz-btn-ghost" onClick={() => void query.refetch()}>
            <RefreshCw className={`h-4 w-4 ${query.isFetching ? "animate-spin" : ""}`} />
            Actualiser
          </button>
        }
      />
      <div className="vz-panel overflow-hidden">
        <div className="flex items-center gap-2 border-b border-cp-border px-4 py-3 dark:border-ink-800">
          <button type="button" className="vz-btn-ghost !p-2" onClick={() => setPath("")}>
            <Home className="h-4 w-4" />
          </button>
          {path && (
            <button type="button" className="vz-btn-ghost !py-1.5 text-xs" onClick={() => setPath(parent)}>
              Dossier parent
            </button>
          )}
          <code className="truncate text-xs text-cp-muted">/{path}</code>
        </div>
        {query.isLoading ? (
          <p className="px-4 py-10 text-center text-sm text-cp-muted">Analyse en cours…</p>
        ) : query.error ? (
          <p className="px-4 py-10 text-center text-sm text-rose-600">{query.error.message}</p>
        ) : nodes.length === 0 ? (
          <EmptyState icon={<HardDrive className="h-5 w-5" />} message="Ce dossier est vide." />
        ) : (
          <div className="divide-y divide-cp-border dark:divide-ink-800">
            {nodes.map((node) => (
              <UsageNode key={node.path} node={node} maxSize={maxSize} onOpen={setPath} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
