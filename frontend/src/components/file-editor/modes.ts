/** Détection du mode Ace selon l'extension (comme cPanel). */

export type AceModeId =
  | "text"
  | "html"
  | "css"
  | "javascript"
  | "typescript"
  | "json"
  | "php"
  | "python"
  | "ruby"
  | "java"
  | "c_cpp"
  | "xml"
  | "yaml"
  | "markdown"
  | "sql"
  | "sh"
  | "ini"
  | "nginx"
  | "apache_conf"
  | "scss"
  | "less"
  | "svg"
  | "dockerfile"
  | "toml";

export const ACE_MODES: { id: AceModeId; label: string }[] = [
  { id: "text", label: "Texte" },
  { id: "html", label: "HTML" },
  { id: "css", label: "CSS" },
  { id: "javascript", label: "JavaScript" },
  { id: "typescript", label: "TypeScript" },
  { id: "json", label: "JSON" },
  { id: "php", label: "PHP" },
  { id: "python", label: "Python" },
  { id: "ruby", label: "Ruby" },
  { id: "java", label: "Java" },
  { id: "c_cpp", label: "C / C++" },
  { id: "xml", label: "XML" },
  { id: "yaml", label: "YAML" },
  { id: "markdown", label: "Markdown" },
  { id: "sql", label: "SQL" },
  { id: "sh", label: "Shell" },
  { id: "ini", label: "INI / Conf" },
  { id: "nginx", label: "Nginx" },
  { id: "apache_conf", label: "Apache" },
  { id: "scss", label: "SCSS" },
  { id: "less", label: "Less" },
  { id: "svg", label: "SVG" },
  { id: "dockerfile", label: "Dockerfile" },
  { id: "toml", label: "TOML" },
];

export function detectAceMode(filePath: string): AceModeId {
  const name = filePath.split("/").pop()?.toLowerCase() || "";
  if (name === "dockerfile" || name.startsWith("dockerfile.")) return "dockerfile";
  if (name === ".htaccess" || name === "htaccess") return "apache_conf";
  if (name === "nginx.conf" || name.endsWith(".nginx")) return "nginx";
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".") + 1) : "";
  switch (ext) {
    case "html":
    case "htm":
    case "shtml":
      return "html";
    case "css":
      return "css";
    case "scss":
      return "scss";
    case "less":
      return "less";
    case "js":
    case "jsx":
    case "mjs":
    case "cjs":
      return "javascript";
    case "ts":
    case "tsx":
      return "typescript";
    case "json":
    case "jsonc":
      return "json";
    case "php":
    case "phtml":
      return "php";
    case "py":
      return "python";
    case "rb":
      return "ruby";
    case "java":
      return "java";
    case "c":
    case "h":
    case "cpp":
    case "cc":
    case "cxx":
    case "hpp":
      return "c_cpp";
    case "xml":
    case "xsl":
    case "xslt":
      return "xml";
    case "yml":
    case "yaml":
      return "yaml";
    case "md":
    case "markdown":
      return "markdown";
    case "sql":
      return "sql";
    case "sh":
    case "bash":
    case "zsh":
    case "ksh":
      return "sh";
    case "ini":
    case "conf":
    case "cfg":
    case "env":
      return "ini";
    case "svg":
      return "svg";
    case "toml":
      return "toml";
    default:
      return "text";
  }
}
