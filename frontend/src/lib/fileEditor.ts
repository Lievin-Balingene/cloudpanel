/** Éditeur de fichiers — onglet dédié style cPanel. */

import { FILES_BROADCAST, notifyFilesChanged, PanelBase, resolvePanelBase } from "@/lib/fileUpload";

export { FILES_BROADCAST, notifyFilesChanged, resolvePanelBase };
export type { PanelBase };

export function editPageUrl(base: PanelBase, filePath: string): string {
  const q = new URLSearchParams();
  q.set("path", filePath);
  return `${base}/files/edit?${q.toString()}`;
}

/** Ouvre l'éditeur dans un nouvel onglet (comme cPanel). */
export function openEditTab(base: PanelBase, filePath: string): Window | null {
  const url = editPageUrl(base, filePath);
  const win = window.open(url, "_blank");
  return win;
}
