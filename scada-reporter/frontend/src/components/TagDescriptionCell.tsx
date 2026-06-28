import { useId, useState } from 'react'

/**
 * Tag adı hücresi. Açıklama (description) doluysa, ada hover/focus ile
 * erişilebilir bir tooltip gösterir. Tags sayfası ve Dashboard sekmelerinde
 * (Tüm Etiketler + İzleme Listesi) ortak kullanılır.
 */
export default function TagDescriptionCell({
  name,
  description,
}: {
  name: string
  description: string
}) {
  const [open, setOpen] = useState(false)
  const tooltipId = useId()
  const hasDescription = description.trim().length > 0

  if (!hasDescription) {
    return <span className="truncate flex-1">{name}</span>
  }

  return (
    <span className="relative inline-flex min-w-0 max-w-full items-center">
      <button
        type="button"
        className="min-w-0 max-w-full border-0 bg-transparent p-0 text-left text-inherit font-inherit cursor-help focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-blue-500/70 focus-visible:ring-offset-0"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        aria-describedby={open ? tooltipId : undefined}
      >
        {name}
      </button>
      {open && (
        <span
          id={tooltipId}
          role="tooltip"
          className="absolute left-0 top-full z-20 mt-1 max-w-xs rounded-lg border border-edge-strong bg-surface px-2 py-1 text-xs text-gray-200 shadow-lg"
        >
          {description}
        </span>
      )}
    </span>
  )
}
