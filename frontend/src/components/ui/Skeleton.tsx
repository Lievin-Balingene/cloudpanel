/** Skeletons WHM — affichage immédiat de la structure, puis les données. */

export function Skel({ className = "h-3 w-full" }: { className?: string }) {
  return <div className={`vz-skel rounded ${className}`} />;
}

export function FormPageSkeleton({ rows = 7 }: { rows?: number }) {
  return (
    <div
      className="flex flex-col gap-4 lg:flex-row"
      aria-busy="true"
      aria-label="Chargement"
    >
      <aside className="vz-panel w-full shrink-0 space-y-2 overflow-hidden p-2 lg:w-56">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skel key={i} className="h-8 w-full" />
        ))}
      </aside>
      <div className="vz-panel min-w-0 flex-1 space-y-5 p-4">
        <Skel className="h-5 w-40" />
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="flex flex-col gap-2 border-b border-cp-border/40 pb-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0 flex-1 space-y-2">
              <Skel className="h-4 w-2/3" />
              <Skel className="h-3 w-full max-w-md" />
            </div>
            <Skel className="h-7 w-12 shrink-0 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function TablePageSkeleton({ rows = 8, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="vz-panel overflow-hidden" aria-busy="true" aria-label="Chargement">
      <div className="flex gap-3 border-b border-cp-border/70 px-4 py-3">
        <Skel className="h-4 w-32" />
        <Skel className="h-4 w-20" />
      </div>
      <div className="divide-y divide-cp-border/50">
        {Array.from({ length: rows }).map((_, i) => (
          <div
            key={i}
            className="grid gap-3 px-4 py-3"
            style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
          >
            {Array.from({ length: cols }).map((__, j) => (
              <Skel key={j} className="h-3.5 w-full" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function TableSkeletonRows({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <tr key={i} className="border-t border-cp-border/60 dark:border-ink-800">
          {Array.from({ length: cols }).map((__, j) => (
            <td key={j} className="px-3 py-3">
              <Skel className="h-3.5 w-[72%]" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function ListSkeleton({ rows = 6, embedded = false }: { rows?: number; embedded?: boolean }) {
  const body = (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3">
          <Skel className="h-8 w-8 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skel className="h-3.5 w-2/3" />
            <Skel className="h-3 w-1/3" />
          </div>
        </div>
      ))}
    </>
  );
  if (embedded) {
    return (
      <div className="divide-y divide-cp-border/60" aria-busy="true">
        {body}
      </div>
    );
  }
  return (
    <div className="vz-panel divide-y divide-cp-border/60 overflow-hidden" aria-busy="true">
      {body}
    </div>
  );
}

export function PanelSkeleton({ lines = 6 }: { lines?: number }) {
  return (
    <div className="vz-panel space-y-3 p-4" aria-busy="true" aria-label="Chargement">
      <Skel className="h-4 w-48" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skel key={i} className={`h-3 ${i % 2 ? "w-5/6" : "w-full"}`} />
      ))}
    </div>
  );
}

export function CardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="vz-panel space-y-3 p-4">
          <Skel className="h-3 w-20" />
          <Skel className="h-8 w-16" />
          <Skel className="h-2.5 w-full" />
        </div>
      ))}
    </div>
  );
}

export function DlSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="mt-2 space-y-2.5" aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex justify-between gap-2">
          <Skel className="h-3 w-24" />
          <Skel className="h-3 w-16" />
        </div>
      ))}
    </div>
  );
}
