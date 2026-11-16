import { BRAND } from '../lib/brand'

export function LogoMark({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="1" y="1" width="38" height="38" rx="11" fill="var(--mint)" />
      <path d="M12 26V15a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v11" fill="none" stroke="#04201a" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="16.5" cy="18.5" r="2" fill="#04201a" />
      <circle cx="23.5" cy="18.5" r="2" fill="#04201a" />
      <path d="M9 28h22" stroke="#04201a" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  )
}

export function Logo() {
  return (
    <div className="logo">
      <LogoMark />
      <div>
        <strong>{BRAND.product}</strong>
        <span>{BRAND.adminSubtitle}</span>
      </div>
    </div>
  )
}
