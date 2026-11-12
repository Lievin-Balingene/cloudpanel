export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified_at: string;
  permissions: string;
  mode: number;
  mime: string | null;
  is_text: boolean;
}

export interface Listing {
  cwd: string;
  root: string;
  entries: FileEntry[];
}

export type ClipMode = "copy" | "cut" | null;

export type SortKey = "name" | "size" | "modified" | "perms";
export type SortDir = "asc" | "desc";

export type ConfirmState = {
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
};

export type ContextMenuState = {
  x: number;
  y: number;
  path: string;
};
