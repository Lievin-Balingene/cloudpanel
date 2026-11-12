import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Home, Globe2 } from "lucide-react";
import { useState } from "react";
import { apiRequest } from "@/lib/api";
import type { Listing } from "./types";
import { FileTypeIcon } from "./fileIcons";

function TreeNode({
  path,
  label,
  cwd,
  depth,
  onNavigate,
  enabled,
}: {
  path: string;
  label: string;
  cwd: string;
  depth: number;
  onNavigate: (path: string) => void;
  enabled: boolean;
}) {
  const [open, setOpen] = useState(depth < 1 || cwd === path || cwd.startsWith(`${path}/`));
  const active = cwd === path;
  const { data } = useQuery({
    queryKey: ["files-tree", path],
    queryFn: () => apiRequest<Listing>(`/files/?path=${encodeURIComponent(path)}`),
    enabled: enabled && open,
    staleTime: 30_000,
  });
  const dirs = (data?.entries ?? []).filter((e) => e.is_dir && !e.name.startsWith("."));

  return (
    <div>
      <button
        type="button"
        className={`flex w-full items-center gap-0.5 rounded px-1 py-0.5 text-left text-[11px] ${
          active
            ? "bg-cp-orange-soft font-semibold text-cp-orange-dark"
            : "text-cp-text hover:bg-cp-canvas dark:hover:bg-ink-900"
        }`}
        style={{ paddingLeft: 4 + depth * 10 }}
        onClick={() => onNavigate(path)}
        onDoubleClick={() => setOpen((v) => !v)}
      >
        <span
          className="inline-flex h-4 w-4 shrink-0 items-center justify-center text-cp-muted"
          onClick={(e) => {
            e.stopPropagation();
            setOpen((v) => !v);
          }}
        >
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </span>
        <FileTypeIcon entry={{ name: label, is_dir: true, mime: null }} open={open} />
        <span className="truncate">{label}</span>
      </button>
      {open &&
        dirs.map((d) => (
          <TreeNode
            key={d.path}
            path={d.path}
            label={d.name}
            cwd={cwd}
            depth={depth + 1}
            onNavigate={onNavigate}
            enabled={enabled}
          />
        ))}
    </div>
  );
}

const QUICK = [
  { label: "Accueil", path: "", icon: Home },
  { label: "public_html", path: "public_html", icon: Globe2 },
];

export function DirectoryTree({
  cwd,
  onNavigate,
  enabled,
}: {
  cwd: string;
  onNavigate: (path: string) => void;
  enabled: boolean;
}) {
  return (
    <aside className="flex h-full min-h-0 flex-col overflow-hidden border-r border-cp-border bg-[#f7fafc] dark:border-ink-800 dark:bg-ink-950">
      <p className="shrink-0 border-b border-cp-border px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-cp-muted dark:border-ink-800">
        Dossiers
      </p>
      <div className="shrink-0 space-y-0.5 border-b border-cp-border px-1.5 py-1.5 dark:border-ink-800">
        {QUICK.map((q) => {
          const Icon = q.icon;
          const active = cwd === q.path;
          return (
            <button
              key={q.path || "home"}
              type="button"
              className={`flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-[11px] ${
                active
                  ? "bg-cp-orange-soft font-semibold text-cp-orange-dark"
                  : "hover:bg-white dark:hover:bg-ink-900"
              }`}
              onClick={() => onNavigate(q.path)}
            >
              <Icon className="h-3.5 w-3.5 text-cp-orange" />
              {q.label}
            </button>
          );
        })}
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-1 py-1">
        <TreeNode
          path=""
          label="home"
          cwd={cwd}
          depth={0}
          onNavigate={onNavigate}
          enabled={enabled}
        />
      </div>
    </aside>
  );
}
