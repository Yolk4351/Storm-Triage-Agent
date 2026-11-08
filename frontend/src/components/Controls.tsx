import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import type { Storm, Theme } from '../types'
import { byNewest, stormLabel, stormTitle } from '../stormNames'

/** Rounded, frosted dropdown (native <select> menus can't be styled). Arrow keys, Enter, Esc and click-outside work. */
export function StormPicker({ storms, value, onChange }: { storms: Storm[]; value: string; onChange: (id: string) => void }) {
  const list = [...storms].sort(byNewest)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const current = list.find((s) => s.id === value)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const choose = (id: string) => {
    onChange(id)
    setOpen(false)
  }
  const openMenu = () => {
    setActive(Math.max(0, list.findIndex((s) => s.id === value)))
    setOpen(true)
  }
  const onKey = (e: ReactKeyboardEvent) => {
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault()
      openMenu()
    } else if (open && e.key === 'Escape') setOpen(false)
    else if (open && e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(list.length - 1, a + 1))
    } else if (open && e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(0, a - 1))
    } else if (open && e.key === 'Enter') {
      e.preventDefault()
      choose(list[active].id)
    }
  }

  return (
    <div ref={root} className="relative" onKeyDown={onKey}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Storm"
        onClick={() => (open ? setOpen(false) : openMenu())}
        className="flex h-8 items-center gap-2 rounded-full bg-[var(--fill)] pl-3.5 pr-3 text-[12px] font-medium text-[var(--text)] outline-none transition-colors hover:bg-[var(--fill-hover)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]/50"
      >
        <span className="whitespace-nowrap">{current ? stormLabel(current) : 'Loading…'}</span>
        <svg className={`h-3 w-3 text-[var(--text-2)] transition-transform duration-300 ${open ? 'rotate-180' : ''}`} viewBox="0 0 12 12" fill="none">
          <path d="M3 4.5 6 7.5 9 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <ul
        role="listbox"
        aria-label="Storms"
        className="menu absolute left-0 top-[calc(100%+10px)] z-40 min-w-[260px] origin-top-left rounded-[18px] p-1.5 transition-[opacity,transform] duration-200 ease-[cubic-bezier(.32,.72,0,1)]"
        style={{ opacity: open ? 1 : 0, transform: open ? 'scale(1)' : 'scale(0.96) translateY(-4px)', pointerEvents: open ? 'auto' : 'none' }}
      >
        {list.map((s, i) => {
          const selected = s.id === value
          return (
            <li
              key={s.id}
              role="option"
              aria-selected={selected}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(s.id)}
              className={`flex cursor-pointer items-center justify-between gap-4 rounded-xl px-3 py-2 text-[13px] ${
                i === active ? 'bg-[var(--fill-hover)]' : ''
              }`}
            >
              <span>
                <span className="block font-medium text-[var(--text)]">{stormTitle(s)}</span>
                <span className="block text-[11px] text-[var(--text-2)]">
                  {fmtRange(s.start, s.end)}
                  {s.llm_available ? ' · AI run ready' : ''}
                </span>
              </span>
              {selected && (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12.5 10 17.5 19 7" />
                </svg>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const fmtRange = (start: string, end: string) => {
  const a = new Date(start.replace(' ', 'T'))
  const b = new Date(new Date(end.replace(' ', 'T')).getTime() - 3600_000)
  const md = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return `${md(a)} – ${md(b)}, ${b.getFullYear()}`
}

type Option<T extends string> = { id: T; label: string; hint?: string; dim?: boolean }

/** iOS-style segmented control. Every segment has the same fixed width so the sliding pill lines up exactly. */
export function Segmented<T extends string>({ options, value, onChange, label, width = 84 }: {
  options: Option<T>[]
  value: T
  onChange: (v: T) => void
  label: string
  width?: number
}) {
  const i = Math.max(0, options.findIndex((o) => o.id === value))
  return (
    <div className="relative flex h-8 rounded-full bg-[var(--fill)] p-[3px]" role="tablist" aria-label={label}>
      <span
        className="absolute left-[3px] top-[3px] h-[26px] rounded-full bg-[var(--pill)] shadow-[0_1px_4px_rgba(0,0,0,0.14)] transition-transform duration-300 ease-[cubic-bezier(.32,.72,0,1)]"
        style={{ width, transform: `translateX(${i * width}px)` }}
      />
      {options.map((o) => (
        <button
          key={o.id}
          role="tab"
          aria-selected={o.id === value}
          title={o.hint}
          onClick={() => onChange(o.id)}
          style={{ width }}
          className={`relative z-10 shrink-0 text-[12px] font-medium transition-colors ${
            o.id === value ? 'text-[var(--text)]' : 'text-[var(--text-2)] hover:text-[var(--text)]'
          }`}
        >
          {o.label}
          {o.dim && <span className="ml-1 text-[var(--text-3)]">·</span>}
        </button>
      ))}
    </div>
  )
}

export function ThemeToggle({ theme, onChange }: { theme: Theme; onChange: (t: Theme) => void }) {
  const dark = theme === 'dark'
  return (
    <button
      onClick={() => onChange(dark ? 'light' : 'dark')}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={dark ? 'Light mode' : 'Dark mode'}
      className="grid h-8 w-8 place-items-center rounded-full bg-[var(--fill)] text-[var(--text)] transition-colors hover:bg-[var(--fill-hover)]"
    >
      {dark ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
        </svg>
      ) : (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <path d="M20.5 14.6A8.6 8.6 0 0 1 9.4 3.5a.6.6 0 0 0-.8-.7A9.9 9.9 0 1 0 21.2 15.4a.6.6 0 0 0-.7-.8Z" />
        </svg>
      )}
    </button>
  )
}
