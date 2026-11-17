/*
 * Select for a dropdown value (category, status, priority) or project.
 *
 * Offers only active values, but keeps showing the record's current value when it
 * has since been deactivated (marked "inactive"), so editing an old record never
 * silently changes it. Pass the record's own reference as `current`, e.g.
 *
 *   <LookupSelect kind="categories" label="Category" current={task.category}
 *     emptyLabel="No category" {...register('category_id')} />
 *
 * Option values are ids as strings ("" for the empty option); convert them in the
 * form schema (e.g. z.coerce.number()).
 */
import type { ComponentProps } from 'react'

import { useSelectOptions, type CurrentValue, type SelectKind } from '../api/lookups'
import { SelectField } from './FormField'

type LookupSelectProps = Omit<ComponentProps<typeof SelectField>, 'children'> & {
  kind: SelectKind
  current?: CurrentValue | null
  /** Adds a first option with value "" (for optional fields). */
  emptyLabel?: string
}

export default function LookupSelect({
  kind,
  current,
  emptyLabel,
  disabled,
  error,
  ...props
}: LookupSelectProps) {
  const { options, isPending, error: loadError } = useSelectOptions(kind, current)
  return (
    <SelectField
      // Remount once options arrive so React Hook Form re-applies the field value.
      key={isPending ? 'loading' : 'ready'}
      disabled={disabled || isPending}
      error={error ?? (loadError ? 'Could not load the options' : undefined)}
      {...props}
    >
      {isPending ? (
        <option value="">Loading…</option>
      ) : (
        <>
          {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
          {options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.isActive ? option.label : `${option.label} (inactive)`}
            </option>
          ))}
        </>
      )}
    </SelectField>
  )
}
