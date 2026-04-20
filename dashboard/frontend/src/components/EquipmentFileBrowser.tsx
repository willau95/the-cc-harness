import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText,
  FileCode,
  FileJson,
  FileArchive,
  FileImage,
  Folder,
  FolderOpen,
} from "lucide-react";
import { equipmentApi, type EquipmentFile } from "@/api/equipment";
import { cn } from "@/lib/utils";

/**
 * Two-pane browser: left = file tree, right = preview. Lets you walk the
 * full skill structure (SKILL.md + references/*.md + scripts/*.py + assets
 * + subfolders) without leaving the dashboard.
 */
export function EquipmentFileBrowser({ slug }: { slug: string }) {
  const { data: treeData, isLoading } = useQuery({
    queryKey: ["equipment-tree", slug],
    queryFn: () => equipmentApi.tree(slug),
  });

  // Flat list → nested tree
  const tree = useMemo(() => buildTree(treeData?.files ?? []), [treeData]);

  // Auto-select SKILL.md by default if present
  const defaultPath = useMemo(() => {
    const files = treeData?.files ?? [];
    const skillMd = files.find((f) => f.path === "SKILL.md");
    if (skillMd) return skillMd.path;
    const firstMd = files.find((f) => f.ext === ".md");
    if (firstMd) return firstMd.path;
    const firstText = files.find((f) => f.is_text);
    return firstText?.path ?? null;
  }, [treeData]);

  const [selected, setSelected] = useState<string | null>(null);
  const active = selected ?? defaultPath;

  if (isLoading) {
    return <div className="p-4 text-sm text-muted-foreground">Loading file tree…</div>;
  }

  if (!treeData || treeData.count === 0) {
    return (
      <div className="p-6 text-sm text-muted-foreground text-center border border-border rounded-lg">
        No files in this equipment's content directory.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[280px_1fr] gap-3 border border-border rounded-lg overflow-hidden bg-card/40">
      <div className="border-r border-border bg-background/40 overflow-y-auto max-h-[70vh]">
        <div className="px-3 py-2 border-b border-border text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {treeData.count} file{treeData.count === 1 ? "" : "s"}
        </div>
        <TreeNode
          node={tree}
          depth={0}
          active={active}
          onSelect={setSelected}
        />
      </div>
      <div className="overflow-y-auto max-h-[70vh] min-w-0">
        {active ? (
          <FileViewer slug={slug} path={active} />
        ) : (
          <div className="p-6 text-sm text-muted-foreground text-center">Select a file</div>
        )}
      </div>
    </div>
  );
}

// ─── tree building ─────────────────────────────────────────────────────────

interface TreeDir {
  name: string;
  children: (TreeDir | TreeFile)[];
}
interface TreeFile {
  name: string;
  file: EquipmentFile;
}
function isDir(n: TreeDir | TreeFile): n is TreeDir {
  return (n as TreeDir).children !== undefined;
}

function buildTree(files: EquipmentFile[]): TreeDir {
  const root: TreeDir = { name: "", children: [] };
  for (const f of files) {
    const parts = f.path.split("/");
    let cursor: TreeDir = root;
    for (let i = 0; i < parts.length - 1; i++) {
      let dir = cursor.children.find(
        (c): c is TreeDir => isDir(c) && c.name === parts[i],
      );
      if (!dir) {
        dir = { name: parts[i], children: [] };
        cursor.children.push(dir);
      }
      cursor = dir;
    }
    cursor.children.push({ name: parts[parts.length - 1], file: f });
  }
  // Sort dirs first, then files; alphabetical within each group
  const sort = (node: TreeDir) => {
    node.children.sort((a, b) => {
      if (isDir(a) && !isDir(b)) return -1;
      if (!isDir(a) && isDir(b)) return 1;
      return a.name.localeCompare(b.name);
    });
    for (const c of node.children) if (isDir(c)) sort(c);
  };
  sort(root);
  return root;
}

function TreeNode({
  node, depth, active, onSelect,
}: {
  node: TreeDir;
  depth: number;
  active: string | null;
  onSelect: (path: string) => void;
}) {
  if (depth === 0) {
    return (
      <div className="py-1">
        {node.children.map((c, i) => (
          <TreeEntry key={i} entry={c} depth={0} active={active} onSelect={onSelect} />
        ))}
      </div>
    );
  }
  return (
    <>
      {node.children.map((c, i) => (
        <TreeEntry key={i} entry={c} depth={depth} active={active} onSelect={onSelect} />
      ))}
    </>
  );
}

function TreeEntry({
  entry, depth, active, onSelect,
}: {
  entry: TreeDir | TreeFile;
  depth: number;
  active: string | null;
  onSelect: (path: string) => void;
}) {
  const [open, setOpen] = useState(true);
  if (isDir(entry)) {
    const Icon = open ? FolderOpen : Folder;
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 w-full text-left text-xs py-0.5 hover:bg-accent/40 px-2"
          style={{ paddingLeft: `${8 + depth * 12}px` }}
        >
          <Icon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <span className="text-muted-foreground">{entry.name}/</span>
        </button>
        {open && (
          <TreeNode
            node={entry as TreeDir}
            depth={depth + 1}
            active={active}
            onSelect={onSelect}
          />
        )}
      </div>
    );
  }
  const f = entry.file;
  const FileIcon = fileIcon(f);
  const isActive = active === f.path;
  return (
    <button
      onClick={() => onSelect(f.path)}
      className={cn(
        "flex items-center gap-1.5 w-full text-left text-xs py-0.5 px-2 transition-colors",
        isActive ? "bg-primary/20 text-foreground font-medium" : "hover:bg-accent/40",
      )}
      style={{ paddingLeft: `${8 + depth * 12}px` }}
    >
      <FileIcon className={cn("h-3.5 w-3.5 shrink-0", isActive ? "text-primary" : "text-muted-foreground")} />
      <span className="truncate">{entry.name}</span>
      {!f.is_text && (
        <span className="text-[9px] text-muted-foreground/60 ml-auto shrink-0">
          {formatSize(f.size)}
        </span>
      )}
    </button>
  );
}

function fileIcon(f: EquipmentFile) {
  if (!f.is_text) {
    if (/\.(png|jpg|jpeg|gif|webp|svg)$/i.test(f.path)) return FileImage;
    if (/\.(zip|tar|gz|pdf)$/i.test(f.path)) return FileArchive;
    return FileText;
  }
  if (f.ext === ".json" || f.ext === ".yaml" || f.ext === ".yml") return FileJson;
  if (f.ext === ".md" || f.ext === ".txt") return FileText;
  return FileCode;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}K`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}M`;
}

// ─── file viewer ───────────────────────────────────────────────────────────

function FileViewer({ slug, path }: { slug: string; path: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["equipment-file", slug, path],
    queryFn: () => equipmentApi.file(slug, path),
  });

  if (isLoading) return <div className="p-4 text-sm text-muted-foreground">Loading…</div>;
  if (!data) return <div className="p-4 text-sm text-destructive">Failed to load {path}</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b border-border bg-muted/30 flex items-center gap-2 text-xs">
        <FileCode className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="font-mono truncate flex-1">{data.path}</span>
        <span className="text-muted-foreground tabular-nums">{formatSize(data.size)}</span>
      </div>
      <div className="flex-1 overflow-auto">
        {!data.is_text ? (
          <div className="p-6 text-sm text-muted-foreground text-center">
            <FileArchive className="h-8 w-8 mx-auto mb-2 text-muted-foreground/50" />
            Binary file ({formatSize(data.size)}) — not rendered inline.
          </div>
        ) : data.truncated ? (
          <div className="p-6 text-sm text-muted-foreground text-center">
            File too large ({formatSize(data.size)}). {data.reason}
          </div>
        ) : data.ext === ".md" ? (
          <div className="px-5 py-4 prose prose-sm prose-invert max-w-none prose-headings:mt-4 prose-headings:mb-2 prose-p:my-1.5 prose-pre:my-2 prose-pre:bg-muted prose-code:text-[0.85em] prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-a:text-primary">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.content ?? ""}</ReactMarkdown>
          </div>
        ) : (
          <pre className="px-4 py-3 text-xs font-mono whitespace-pre overflow-x-auto">
            {data.content}
          </pre>
        )}
      </div>
    </div>
  );
}
