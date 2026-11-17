/*
 * Filter controls for a list. From md up they are always visible in a grid; below md
 * they collapse behind a "Filters" button showing how many are active.
 */
import { useId, useState, type ReactNode } from 'react'

import { useSelectOptions, type SelectKind } from '../api/lookups'
import { SelectField } from './FormField'
import { FilterIcon } from './icons'

interface FilterPanelProps {
  activeCount: number
  onClear: () => void
  children: ReactNode
}

export default function FilterPanel({ activeCount, onClear, children }: FilterPanelProps) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <div className="mb-4">
      <button
        type="button"
        className="btn w-full md:hidden"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        <FilterIcon />
        Filters
        {activeCount > 0 && <span className="badge badge-sm badge-primary">{activeCount}</span>}
      </button>
      <div
        id={id}
        className={`${open ? 'grid' : 'hidden'} mt-2 grid-cols-1 gap-x-3 sm:grid-cols-2 md:mt-0 md:grid md:grid-cols-4 md:items-end`}
      >
        {children}
        <div className="fieldset">
          <button
            type="button"
            className="btn btn-ghost"
            disabled={activeCount === 0}
            onClick={onClear}
          >
            Clear filters
          </button>
        </div>
      </div>
    </div>
  )
}

/** A filter select over a dropdown's active values or projects ("" = any). */
export function LookupFilter({
  kind,
  label,
  allLabel,
  value,
  onChange,
}: {
  kind: SelectKind
  label: string
  allLabel: string
  value: string
  onChange: (value: string) => void
}) {
  const { options, isPending } = useSelectOptions(kind)
  return (
    <SelectField
      label={label}
      value={value}
      disabled={isPending}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{allLabel}</option>
      {options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.label}
        </option>
      ))}
    </SelectField>
  )
}
