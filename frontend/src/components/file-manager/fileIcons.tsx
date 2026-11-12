import {
  FileArchive,
  FileCode2,
  FileImage,
  FileJson,
  FileText,
  FileType2,
  Folder,
  FolderOpen,
  Music,
  Video,
} from "lucide-react";
import type { FileEntry } from "./types";

export function FileTypeIcon({
  entry,
  open,
  className = "h-3.5 w-3.5 shrink-0",
}: {
  entry: Pick<FileEntry, "name" | "is_dir" | "mime">;
  open?: boolean;
  className?: string;
}) {
  if (entry.is_dir) {
    const Icon = open ? FolderOpen : Folder;
    return <Icon className={`${className} text-cp-orange`} />;
  }
  const n = entry.name.toLowerCase();
  const mime = entry.mime || "";
  if (mime.startsWith("image/") || /\.(png|jpe?g|gif|webp|svg|ico|bmp|avif)$/i.test(n)) {
    return <FileImage className={`${className} text-emerald-600`} />;
  }
  if (mime.startsWith("video/") || /\.(mp4|webm|mkv|mov|avi)$/i.test(n)) {
    return <Video className={`${className} text-violet-600`} />;
  }
  if (mime.startsWith("audio/") || /\.(mp3|wav|ogg|flac|m4a)$/i.test(n)) {
    return <Music className={`${className} text-pink-600`} />;
  }
  if (/\.(zip|tar|gz|tgz|rar|7z|bz2)$/i.test(n)) {
    return <FileArchive className={`${className} text-amber-700`} />;
  }
  if (/\.(json)$/i.test(n)) {
    return <FileJson className={`${className} text-cp-link`} />;
  }
  if (
    /\.(html?|css|js|jsx|ts|tsx|php|py|rb|go|rs|sh|bash|vue|sql|xml|yml|yaml|toml|ini|conf|env|htaccess)$/i.test(
      n,
    )
  ) {
    return <FileCode2 className={`${className} text-sky-700`} />;
  }
  if (/\.(pdf|docx?|odt|rtf)$/i.test(n)) {
    return <FileType2 className={`${className} text-rose-700`} />;
  }
  return <FileText className={`${className} text-cp-link`} />;
}

export function isImageEntry(entry: Pick<FileEntry, "name" | "mime" | "is_dir">) {
  if (entry.is_dir) return false;
  if (entry.mime?.startsWith("image/")) return true;
  return /\.(png|jpe?g|gif|webp|svg|ico|bmp|avif)$/i.test(entry.name);
}

export function isEditableEntry(entry: Pick<FileEntry, "name" | "is_dir" | "is_text">) {
  if (entry.is_dir) return false;
  if (entry.is_text) return true;
  return /\.(txt|html?|css|js|json|md|py|php|env|conf|ini|yml|yaml|xml|sh|sql|log|csv|ts|tsx|jsx|vue|rb|go|rs|toml|cfg|htaccess)$/i.test(
    entry.name,
  );
}

export function isArchiveEntry(entry: Pick<FileEntry, "name" | "is_dir">) {
  if (entry.is_dir) return false;
  return /\.(zip|tar\.gz|tgz|tar)$/i.test(entry.name);
}
