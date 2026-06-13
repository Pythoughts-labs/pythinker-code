import { useRef } from "react";
import {
  Search,
  ArrowUpDown,
  FolderOpen,
  Import,
  LayoutGrid,
  List,
  Loader2,
  X,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export type SortMode = "time" | "turns" | "name";
export type ViewMode = "cards" | "compact";
export type FilterMode = "all" | "imported";

const SORT_OPTIONS: { value: SortMode; label: string }[] = [
  { value: "time", label: "Recent" },
  { value: "turns", label: "Turns" },
  { value: "name", label: "Name" },
];

interface ExplorerToolbarProps {
  search: string;
  onSearchChange: (q: string) => void;
  sortMode: SortMode;
  onSortChange: (mode: SortMode) => void;
  grouped: boolean;
  onToggleGrouped: () => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  filterMode: FilterMode;
  onFilterModeChange: (mode: FilterMode) => void;
  totalCount: number;
  filteredCount: number;
  onImport: (file: File) => void;
  importing?: boolean;
}

export function ExplorerToolbar({
  search,
  onSearchChange,
  sortMode,
  onSortChange,
  grouped,
  onToggleGrouped,
  viewMode,
  onViewModeChange,
  filterMode,
  onFilterModeChange,
  totalCount,
  filteredCount,
  onImport,
  importing,
}: ExplorerToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="border-b px-4 py-2">
      <div className="flex items-center gap-2">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search
            size={13}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search sessions..."
            data-session-search
            className="h-8 w-full rounded-md border bg-background pl-8 pr-8 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          {search ? (
            <button
              onClick={() => onSearchChange("")}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X size={12} />
            </button>
          ) : (
            <kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:block">
              /
            </kbd>
          )}
        </div>

        <div className="h-4 w-px bg-border" />

        {/* Sort dropdown */}
        <div className="flex items-center gap-1 text-muted-foreground">
          <ArrowUpDown size={12} className="shrink-0" />
          <Select value={sortMode} onValueChange={(v) => onSortChange(v as SortMode)}>
            <SelectTrigger size="sm" className="h-6 min-w-[5rem] border-none shadow-none px-1.5 py-0 text-[11px] gap-1">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value} className="text-xs">
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="h-4 w-px bg-border" />

        {/* Imported filter toggle */}
        <button
          onClick={() => onFilterModeChange(filterMode === "all" ? "imported" : "all")}
          aria-pressed={filterMode === "imported"}
          className={`flex h-7 items-center gap-1 rounded-md border px-2 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            filterMode === "imported"
              ? "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/30"
              : "text-muted-foreground hover:bg-muted"
          }`}
          title="Show imported sessions only"
        >
          <Import size={12} />
          Imported
        </button>

        {/* Group toggle */}
        <button
          onClick={onToggleGrouped}
          aria-pressed={grouped}
          className={`flex h-7 items-center gap-1 rounded-md border px-2 text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            grouped
              ? "bg-primary/10 text-primary border-primary/30"
              : "text-muted-foreground hover:bg-muted"
          }`}
          title="Group by project"
        >
          <FolderOpen size={12} />
          Group
        </button>

        {/* View toggle */}
        <button
          onClick={() =>
            onViewModeChange(viewMode === "cards" ? "compact" : "cards")
          }
          aria-label={viewMode === "cards" ? "Switch to list view" : "Switch to card view"}
          className="flex h-7 items-center gap-1 rounded-md border px-2 text-[11px] text-muted-foreground hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          title={viewMode === "cards" ? "Switch to list" : "Switch to cards"}
        >
          {viewMode === "cards" ? <List size={12} /> : <LayoutGrid size={12} />}
        </button>

        <div className="h-4 w-px bg-border" />

        {/* Import button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={importing}
          className="flex h-7 items-center gap-1 rounded-md border px-2 text-[11px] text-muted-foreground hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          title="Import session from ZIP"
        >
          {importing ? <Loader2 size={12} className="animate-spin" /> : <Import size={12} />}
          {importing ? "Importing..." : "Import"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onImport(file);
            e.target.value = "";
          }}
        />

        {/* Count */}
        <span className="text-[11px] text-muted-foreground ml-auto shrink-0">
          {filteredCount === totalCount
            ? `${totalCount} sessions`
            : `${filteredCount} / ${totalCount}`}
        </span>
      </div>
    </div>
  );
}
