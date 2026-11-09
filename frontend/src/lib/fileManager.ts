/** Gestionnaire de fichiers — onglet dédié style cPanel. */

import type { PanelBase } from "@/lib/fileUpload";
import { resolvePanelBase } from "@/lib/fileUpload";

export function fileManagerUrl(base?: PanelBase): string {
  const b = base ?? resolvePanelBase(window.location.pathname);
  return `${b}/fm`;
}

/** Ouvre le File Manager dans un nouvel onglet (plein écran, sans sidebar). */
export function openFileManagerTab(base?: PanelBase): Window | null {
  const url = fileManagerUrl(base);
  const win = window.open(url, "_blank");
  return win;
}
