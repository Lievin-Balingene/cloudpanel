import {
  Archive,
  Copy,
  Download,
  Eye,
  FolderOpen,
  Pencil,
  Scissors,
  Shield,
  Trash2,
} from "lucide-react";
import { useEffect, useRef } from "react";
import type { FileEntry } from "./types";
import { isArchiveEntry, isEditableEntry, isImageEntry } from "./fileIcons";

type Action =
  | "open"
  | "edit"
  | "preview"
  | "download"
  | "copy"
  | "cut"
  | "rename"
  | "chmod"
  | "extract"
  | "delete";

export function ContextMenu({
  x,
  y,
  entry,
  onAction,
  onClose,
}: {
  x: number;
  y: number;
  entry: FileEntry;
  onAction: (action: Action) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
      el.style.left = `${Math.max(8, x - rect.width)}px`;
    }
    if (rect.bottom > window.innerHeight) {
      el.style.top = `${Math.max(8, y - rect.height)}px`;
    }
  }, [x, y]);

  const items: { id: Action; label: string; icon: typeof Pencil; danger?: boolean; show: boolean }[] =
    [
      { id: "open", label: entry.is_dir ? "Ouvrir" : "Ouvrir", icon: FolderOpen, show: entry.is_dir },
      { id: "edit", label: "Modifier", icon: Pencil, show: isEditableEntry(entry) },
      { id: "preview", label: "Aperçu", icon: Eye, show: isImageEntry(entry) },
      { id: "download", label: "Télécharger", icon: Download, show: !entry.is_dir },
      { id: "copy", label: "Copier", icon: Copy, show: true },
      { id: "cut", label: "Couper", icon: Scissors, show: true },
      { id: "rename", label: "Renommer", icon: Pencil, show: true },
      { id: "chmod", label: "Permissions", icon: Shield, show: true },
      { id: "extract", label: "Décompresser", icon: Archive, show: isArchiveEntry(entry) },
      { id: "delete", label: "Supprimer", icon: Trash2, danger: true, show: true },
    ];

  return (
    <div
      ref={ref}
      className="fixed z-[80] min-w-[180px] overflow-hidden rounded-md border border-cp-border bg-white py-1 shadow-xl dark:border-ink-700 dark:bg-ink-950"
      style={{ left: x, top: y }}
      role="menu"
    >
      {items
        .filter((i) => i.show)
        .map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-cp-canvas dark:hover:bg-ink-900 ${
                item.danger ? "text-cp-danger" : "text-cp-text"
              }`}
              onClick={() => {
                onAction(item.id);
                onClose();
              }}
            >
              <Icon className="h-3.5 w-3.5 opacity-80" />
              {item.label}
            </button>
          );
        })}
    </div>
  );
}
