// Shared unsaved-changes (dirty) badge (design D6). The profiles list page and
// the editor header SHALL present dirty state with the same badge treatment,
// instead of a list-page badge versus a bare colored dot in the editor.

export function DirtyBadge({ label = '未儲存', title }: { label?: string; title?: string }) {
  return (
    <span
      className="w-fit rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-400"
      title={title}
    >
      ● {label}
    </span>
  );
}
