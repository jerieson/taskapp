/*
 * /support: the shared support dictionary. Search box, filters (type, project, module,
 * show inactive) and result cards that expand to the cause, resolution, notes and
 * query. Search, filters and page live in the URL, so coming back from an entry keeps
 * them.
 */
import { useEffect, useId, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import {
  SUPPORT_PAGE_SIZE,
  useSupportEntries,
  useSupportFacets,
  type SupportEntry,
  type SupportFilters,
} from '../../api/support'
import AsyncState from '../../components/AsyncState'
import EmptyState from '../../components/EmptyState'
import FilterPanel, { LookupFilter } from '../../components/FilterPanel'
import { SelectField } from '../../components/FormField'
import { FilterIcon, LifebuoyIcon, PencilIcon, PlusIcon, SearchIcon } from '../../components/icons'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import { SkeletonCard } from '../../components/Skeleton'
import { formatDate } from '../../lib/format'
import SupportFormModal, { type SupportFormState } from './SupportForm'
import { ActiveToggleModal, EntryDetails, InactiveBadge, TypeBadge } from './SupportBits'
import { placeOf } from './supportText'

const FILTER_PARAMS = ['type', 'project', 'module', 'inactive'] as const

function useSupportParams() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const filters = {
    type: params.get('type') ?? '',
    project: params.get('project') ?? '',
    module: params.get('module') ?? '',
    inactive: params.get('inactive') === '1',
  }
  const offset = Math.max(0, Number(params.get('offset')) || 0)

  /** Set some params; any change other than the page goes back to the first page. */
  function update(changes: Record<string, string | null>) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value)
          else next.delete(key)
        }
        if (!('offset' in changes)) next.delete('offset')
        return next
      },
      { replace: true },
    )
  }

  const apiFilters: SupportFilters = {
    q: q.trim() || undefined,
    type_id: filters.type ? Number(filters.type) : undefined,
    project: filters.project || undefined,
    module: filters.module || undefined,
    include_inactive: filters.inactive || undefined,
  }
  return { params, q, filters, offset, apiFilters, update }
}

/** The search box: updates the URL a moment after typing stops. */
function SearchBox({ value, onChange }: { value: string; onChange: (q: string) => void }) {
  const [text, setText] = useState(value)
  const [shown, setShown] = useState(value)
  const id = useId()
  // The URL changed from outside (e.g. "Clear search"): show the new value.
  if (value !== shown) {
    setShown(value)
    setText(value)
  }

  useEffect(() => {
    if (text === value) return
    const timer = window.setTimeout(() => onChange(text), 300)
    return () => window.clearTimeout(timer)
  }, [text, value, onChange])

  return (
    <div className="mb-3">
      <label htmlFor={id} className="sr-only">
        Search the support dictionary
      </label>
      <label className="input w-full">
        <SearchIcon className="size-5 shrink-0 text-base-content/80" />
        <input
          id={id}
          type="search"
          className="grow"
          placeholder="Search concerns, causes, resolutions, notes, projects, modules…"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') onChange(text)
          }}
        />
      </label>
    </div>
  )
}

function Filters({
  filters,
  onChange,
}: {
  filters: ReturnType<typeof useSupportParams>['filters']
  onChange: (changes: Record<string, string | null>) => void
}) {
  const facets = useSupportFacets()
  const activeCount = [filters.type, filters.project, filters.module, filters.inactive].filter(
    Boolean,
  ).length
  const clear = Object.fromEntries(FILTER_PARAMS.map((key) => [key, null]))

  return (
    <FilterPanel activeCount={activeCount} onClear={() => onChange(clear)}>
      <LookupFilter
        kind="support-types"
        label="Type"
        allLabel="Any type"
        value={filters.type}
        onChange={(type) => onChange({ type })}
      />
      <SelectField
        label="Project"
        value={filters.project}
        disabled={facets.isPending}
        onChange={(event) => onChange({ project: event.target.value })}
      >
        <option value="">Any project</option>
        {withCurrent(facets.data?.projects, filters.project).map((project) => (
          <option key={project} value={project}>
            {project}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="Module"
        value={filters.module}
        disabled={facets.isPending}
        onChange={(event) => onChange({ module: event.target.value })}
      >
        <option value="">Any module</option>
        {withCurrent(facets.data?.modules, filters.module).map((module) => (
          <option key={module} value={module}>
            {module}
          </option>
        ))}
      </SelectField>
      <div className="fieldset">
        <label className="label min-h-11 cursor-pointer gap-3 text-base-content">
          <input
            type="checkbox"
            className="toggle toggle-primary"
            checked={filters.inactive}
            onChange={(event) => onChange({ inactive: event.target.checked ? '1' : null })}
          />
          Show inactive
        </label>
      </div>
    </FilterPanel>
  )
}

/** Keep a filter value from the URL selectable even if no active entry uses it. */
function withCurrent(values: string[] | undefined, current: string): string[] {
  const list = values ?? []
  return current && !list.some((v) => v.toLowerCase() === current.toLowerCase())
    ? [current, ...list]
    : list
}

function EntryCard({
  entry,
  linkState,
  onEdit,
  onToggleActive,
}: {
  entry: SupportEntry
  linkState: { back: string }
  onEdit: () => void
  onToggleActive: () => void
}) {
  const place = placeOf(entry)
  return (
    <li className="rounded-box border border-base-300 bg-base-100">
      <div className="flex flex-col gap-2 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <TypeBadge type={entry.type} />
          {!entry.is_active && <InactiveBadge />}
          {place && (
            <span className="min-w-0 text-sm break-words text-base-content/80">{place}</span>
          )}
        </div>
        <Link
          to={`/support/${entry.id}`}
          state={linkState}
          className="link font-semibold break-words link-hover"
        >
          {entry.concern}
        </Link>
      </div>
      <details className="group border-t border-base-300">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 px-4 py-2 text-sm select-none hover:bg-base-200 [&::-webkit-details-marker]:hidden">
          <span className="font-medium">
            <span className="group-open:hidden">Show details</span>
            <span className="hidden group-open:inline">Hide details</span>
          </span>
          <span className="text-xs text-base-content/80">
            {entry.created_by.username} · {formatDate(entry.created_at)}
          </span>
        </summary>
        <div className="flex flex-col gap-4 px-4 pt-2 pb-4">
          <EntryDetails entry={entry} />
          {entry.can_edit && (
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-sm" onClick={onEdit}>
                <PencilIcon className="size-4" />
                Edit
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={onToggleActive}>
                {entry.is_active ? 'Deactivate' : 'Activate'}
              </button>
            </div>
          )}
        </div>
      </details>
    </li>
  )
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading entries">
      {[0, 1, 2].map((i) => (
        <SkeletonCard key={i} lines={2} />
      ))}
    </div>
  )
}

export default function SupportPage() {
  const navigate = useNavigate()
  const { params, q, filters, offset, apiFilters, update } = useSupportParams()
  const entries = useSupportEntries(apiFilters, offset)
  const [form, setForm] = useState<SupportFormState>(null)
  const [toggling, setToggling] = useState<SupportEntry | null>(null)

  const searching = Boolean(apiFilters.q || filters.type || filters.project || filters.module)
  const search = params.toString()
  const linkState = { back: search ? `/support?${search}` : '/support' }

  const newButton = (
    <button type="button" className="btn btn-primary" onClick={() => setForm('new')}>
      <PlusIcon />
      New entry
    </button>
  )

  return (
    <>
      <PageHeader
        title="Support"
        description="The team’s support dictionary: known concerns, their causes, resolutions and queries."
        actions={newButton}
      />

      <SearchBox value={q} onChange={(next) => update({ q: next || null })} />
      <Filters filters={filters} onChange={update} />

      <AsyncState
        query={entries}
        isEmpty={entries.data?.items.length === 0}
        skeleton={<ListSkeleton />}
        empty={
          searching ? (
            <EmptyState
              icon={<FilterIcon className="size-6" />}
              title="No entries match"
              description="Try other words, or clear the search and filters."
              action={
                <button
                  type="button"
                  className="btn"
                  onClick={() =>
                    update(Object.fromEntries(['q', ...FILTER_PARAMS].map((key) => [key, null])))
                  }
                >
                  Clear search and filters
                </button>
              }
            />
          ) : (
            <EmptyState
              icon={<LifebuoyIcon className="size-6" />}
              title="No support entries yet"
              description="Add the concerns you have solved, so the next person finds the answer here."
              action={newButton}
            />
          )
        }
      >
        {() => {
          const page = entries.data!
          return (
            <>
              <p className="mb-2 text-sm text-base-content/80" aria-live="polite">
                {page.total} {page.total === 1 ? 'entry' : 'entries'}
              </p>
              <ul className="flex flex-col gap-3">
                {page.items.map((entry) => (
                  <EntryCard
                    key={entry.id}
                    entry={entry}
                    linkState={linkState}
                    onEdit={() => setForm(entry)}
                    onToggleActive={() => setToggling(entry)}
                  />
                ))}
              </ul>
              <Pagination
                total={page.total}
                limit={SUPPORT_PAGE_SIZE}
                offset={offset}
                onChange={(next) => update({ offset: next ? String(next) : null })}
              />
            </>
          )
        }}
      </AsyncState>

      <SupportFormModal
        state={form}
        onClose={() => setForm(null)}
        onSaved={(saved, created) => {
          if (created) void navigate(`/support/${saved.id}`, { state: linkState })
        }}
      />
      <ActiveToggleModal entry={toggling} onClose={() => setToggling(null)} />
    </>
  )
}
