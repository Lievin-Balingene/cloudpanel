/** Préférences éditeur persistées (mieux que cPanel qui les perd). */

export type AceThemeId =
  | "chrome"
  | "clouds"
  | "github"
  | "github_dark"
  | "xcode"
  | "textmate"
  | "tomorrow"
  | "solarized_light"
  | "monokai"
  | "dracula"
  | "twilight"
  | "tomorrow_night"
  | "solarized_dark"
  | "one_dark"
  | "nord_dark"
  | "ambiance";

export const ACE_THEMES: { id: AceThemeId; label: string; dark?: boolean }[] = [
  { id: "chrome", label: "Chrome" },
  { id: "clouds", label: "Clouds" },
  { id: "github", label: "GitHub" },
  { id: "xcode", label: "Xcode" },
  { id: "textmate", label: "TextMate" },
  { id: "tomorrow", label: "Tomorrow" },
  { id: "solarized_light", label: "Solarized Light" },
  { id: "monokai", label: "Monokai", dark: true },
  { id: "dracula", label: "Dracula", dark: true },
  { id: "one_dark", label: "One Dark", dark: true },
  { id: "github_dark", label: "GitHub Dark", dark: true },
  { id: "nord_dark", label: "Nord", dark: true },
  { id: "twilight", label: "Twilight", dark: true },
  { id: "tomorrow_night", label: "Tomorrow Night", dark: true },
  { id: "solarized_dark", label: "Solarized Dark", dark: true },
  { id: "ambiance", label: "Ambiance", dark: true },
];

export type EditorPrefs = {
  theme: AceThemeId;
  fontSize: number;
  wrap: boolean;
  showInvisibles: boolean;
  showPrintMargin: boolean;
  printMarginColumn: number;
  showGutter: boolean;
  softTabs: boolean;
  tabSize: number;
  highlightActiveLine: boolean;
};

const KEY = "vzone.fileEditor.prefs";

export const DEFAULT_PREFS: EditorPrefs = {
  theme: "chrome",
  fontSize: 14,
  wrap: true,
  showInvisibles: false,
  showPrintMargin: false,
  printMarginColumn: 80,
  showGutter: true,
  softTabs: true,
  tabSize: 2,
  highlightActiveLine: true,
};

export function loadEditorPrefs(): EditorPrefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_PREFS };
    const parsed = JSON.parse(raw) as Partial<EditorPrefs>;
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function saveEditorPrefs(prefs: EditorPrefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* ignore quota */
  }
}
