import type { SVGProps } from 'react'

type SmartReportIconProps = SVGProps<SVGSVGElement> & {
  title?: string
}

export default function SmartReportIcon({ title, ...props }: SmartReportIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
      {...props}
    >
      {title && <title>{title}</title>}
      <path d="M6.25 3.5h7.1l4.4 4.4v12.6H6.25z" fill="#f8fafc" stroke="#0f172a" strokeWidth={1.25} />
      <path d="M13.35 3.5v4.4h4.4" fill="#dbeafe" stroke="#0f172a" strokeWidth={1.25} />
      <path d="M8.7 15.9l2.7-3 2.35 1.9 3.1-4" stroke="#0891b2" strokeWidth={1.65} />
      <path d="M8.7 8.8h3.1M8.7 11.1h1.55" stroke="#334155" strokeWidth={1.2} />
      <circle cx={8.7} cy={15.9} r={1.1} fill="#22c55e" />
      <circle cx={13.75} cy={14.8} r={1.1} fill="#22c55e" />
      <circle cx={16.85} cy={10.8} r={1.1} fill="#22c55e" />
      <path d="M18.4 3.75v1.6M17.6 4.55h1.6" stroke="#f59e0b" strokeWidth={1.1} />
    </svg>
  )
}
