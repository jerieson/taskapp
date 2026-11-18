import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useSearchParams } from 'react-router'
import { z } from 'zod'

import { errorMessage } from '../../api/client'
import {
  useCreateLookup,
  useLookups,
  useReorderLookups,
  useSetLookupActive,
  useSetLookupDefault,
  useUpdateLookup,
  type ActivityGroup,
  type Category,
  type DefaultKind,
  type LookupKind,
  type LookupRow,
  type Status,
} from '../../api/lookups'
import ConfirmModal from '../../components/ConfirmModal'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import { InputField, SubmitButton } from '../../components/FormField'
import {
  ArrowDownIcon,
  ArrowUpIcon,
  ListIcon,
  PencilIcon,
  PlusIcon,
  StarIcon,
} from '../../components/icons'
import Modal from '../../components/Modal'
import { useToast } from '../../components/toast-context'
import { applyFieldErrors } from '../../lib/forms'
import ColorDot from '../../components/ColorDot'
import GroupActivitiesEditor from './GroupActivitiesEditor'
import ImportDataTab from './ImportDataTab'

const LISTS = [
  {
    kind: 'categories',
    label: 'Categories',
    singular: 'category',
    hasColor: true,
    maxLength: 50,
    hint: '“Has O&M project” categories offer Project (For O&M) on log rows.',
  },
  {
    kind: 'statuses',
    label: 'Statuses',
    singular: 'status',
    hasColor: true,
    maxLength: 50,
    hint: 'New tasks get the default status.',
  },
  {
    kind: 'priorities',
    label: 'Priorities',
    singular: 'priority',
    hasColor: true,
    maxLength: 50,
    hint: 'New tasks get the default priority. Order them from lowest to highest: sorting tasks by priority uses this order.',
  },
  {
    kind: 'work-setups',
    label: 'Work set-ups',
    singular: 'work set-up',
    hasColor: true,
    maxLength: 50,
    hint: 'New log rows get the default work set-up.',
  },
  {
    kind: 'activities',
    label: 'Activities',
    singular: 'activity',
    hasColor: true,
    maxLength: 100,
    hint: 'A project offers the activities of its activity group.',
  },
  {
    kind: 'activity-groups',
    label: 'Activity groups',
    singular: 'activity group',
    hasColor: false,
    maxLength: 50,
    hint: 'Each project uses one group; pick and order the activities it offers.',
  },
  {
    kind: 'om-projects',
    label: 'O&M projects',
    singular: 'O&M project',
    hasColor: false,
    maxLength: 100,
    hint: 'Offered as Project (For O&M) on rows whose category has “Has O&M project”.',
  },
  {
    kind: 'deviation-reasons',
    label: 'Deviation reasons',
    singular: 'reason for deviation',
    hasColor: false,
    maxLength: 100,
    hint: 'Offered as Reason for deviation on log rows (optional).',
  },
  {
    kind: 'support-types',
    label: 'Support types',
    singular: 'support type',
    hasColor: true,
    maxLength: 50,
    hint: 'The Type of a support dictionary entry (Concern, Inquiry, Bug, …).',
  },
] as const satisfies readonly {
  kind: LookupKind
  label: string
  singular: string
  hasColor: boolean
  maxLength: number
  hint: string
}[]

type ListMeta = (typeof LISTS)[number]

function isKind(value: string | null): value is LookupKind {
  return LISTS.some((list) => list.kind === value)
}

const DEFAULT_COLOR = '#13294B'

function valueSchema(maxLength: number) {
  return z.object({
    label: z
      .string()
      .trim()
      .min(1, 'Enter a label')
      .max(maxLength, `Use at most ${maxLength} characters`),
    hasColor: z.boolean(),
    color: z.string().regex(/^#[0-9A-Fa-f]{6}$/, 'Pick a color'),
    isDone: z.boolean(),
    requiresOm: z.boolean(),
  })
}
type ValueForm = z.infer<ReturnType<typeof valueSchema>>

function isDefaultKind(kind: LookupKind): kind is DefaultKind {
  return kind === 'statuses' || kind === 'priorities' || kind === 'work-setups'
}

function hasDefault(row: LookupRow): row is LookupRow & { is_default: boolean } {
  return 'is_default' in row
}

function rowColor(row: LookupRow): string | null {
  return 'color' in row ? row.color : null
}

function isCategory(row: LookupRow): row is Category {
  return 'requires_om_project' in row
}

function isGroup(row: LookupRow): row is ActivityGroup {
  return 'activity_ids' in row
}

function isStatus(row: LookupRow): row is Status {
  return 'is_done' in row
}

// ------------------------------------------------------------------ add / edit form

function ValueFormBody({
  list,
  row,
  onDone,
}: {
  list: ListMeta
  row: LookupRow | null
  onDone: () => void
}) {
  const toast = useToast()
  const create = useCreateLookup(list.kind)
  const update = useUpdateLookup(list.kind)
  const mutation = row ? update : create
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<ValueForm>({
    resolver: zodResolver(valueSchema(list.maxLength)),
    defaultValues: {
      label: row?.label ?? '',
      hasColor: Boolean(row && rowColor(row)),
      color: (row && rowColor(row)) ?? DEFAULT_COLOR,
      isDone: false,
      requiresOm: row !== null && isCategory(row) && row.requires_om_project,
    },
  })
  const hasColor = useWatch({ control, name: 'hasColor' })
  const color = useWatch({ control, name: 'color' })

  function onSubmit(data: ValueForm) {
    const color = data.hasColor ? data.color.toUpperCase() : null
    const fields = {
      label: data.label,
      ...(list.hasColor ? { color } : {}),
      ...(list.kind === 'categories' ? { requires_om_project: data.requiresOm } : {}),
    }
    const options = {
      onSuccess: (saved: LookupRow) => {
        toast.success(row ? `Saved “${saved.label}”` : `Added “${saved.label}”`)
        onDone()
      },
      onError: (error: unknown) => {
        if (!applyFieldErrors(error, setError, ['label', 'color'])) toast.error(errorMessage(error))
      },
    }
    if (row) update.mutate({ id: row.id, ...fields }, options)
    else
      create.mutate(
        list.kind === 'statuses' ? { ...fields, is_done: data.isDone } : fields,
        options,
      )
  }

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      <InputField
        label="Label"
        autoFocus
        autoComplete="off"
        error={errors.label?.message}
        {...register('label')}
      />
      {list.hasColor && (
        <fieldset className="fieldset">
          <legend className="fieldset-legend pb-0 text-sm">Color</legend>
          <label className="label min-h-11 cursor-pointer gap-3 text-base-content">
            <input
              type="checkbox"
              className="checkbox checkbox-primary"
              {...register('hasColor')}
            />
            Show a color
          </label>
          {hasColor && (
            <div className="flex items-center gap-3">
              <input
                type="color"
                aria-label="Color"
                className="h-11 w-16 cursor-pointer rounded-field border border-base-300 bg-base-100 p-1"
                {...register('color')}
              />
              <span className="font-mono text-sm text-base-content/80">{color.toUpperCase()}</span>
            </div>
          )}
        </fieldset>
      )}
      {list.kind === 'categories' && (
        <label className="label mt-2 min-h-11 cursor-pointer gap-3 text-base-content">
          <input
            type="checkbox"
            className="checkbox checkbox-primary"
            {...register('requiresOm')}
          />
          Has O&amp;M project (log rows offer Project (For O&amp;M))
        </label>
      )}
      {list.kind === 'statuses' && !row && (
        <label className="label mt-2 min-h-11 cursor-pointer gap-3 text-base-content">
          <input type="checkbox" className="checkbox checkbox-primary" {...register('isDone')} />
          Counts as done
        </label>
      )}
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <SubmitButton isPending={mutation.isPending}>{row ? 'Save' : 'Add'}</SubmitButton>
      </div>
    </form>
  )
}

// ------------------------------------------------------------------ one list

function LookupList({ list }: { list: ListMeta }) {
  const toast = useToast()
  const rows = useLookups(list.kind, true)
  const reorder = useReorderLookups(list.kind)
  const setActive = useSetLookupActive(list.kind)
  // Hooks can't be conditional; lists without a default never call this one.
  const setDefault = useSetLookupDefault(isDefaultKind(list.kind) ? list.kind : 'statuses')
  const update = useUpdateLookup('statuses')
  const updateCategory = useUpdateLookup('categories')
  // undefined = closed, null = new value, row = edit.
  const [editing, setEditing] = useState<LookupRow | null | undefined>(undefined)
  const [deactivating, setDeactivating] = useState<LookupRow | null>(null)
  const [groupMembers, setGroupMembers] = useState<ActivityGroup | null>(null)

  const items = rows.data ?? []
  const supportsDefault = isDefaultKind(list.kind)

  function move(index: number, delta: -1 | 1) {
    const ids = items.map((row) => row.id)
    const target = index + delta
    if (target < 0 || target >= ids.length) return
    const [moved] = ids.splice(index, 1)
    if (moved === undefined) return
    ids.splice(target, 0, moved)
    reorder.mutate(ids, { onError: (error) => toast.error(errorMessage(error)) })
  }

  function activate(row: LookupRow) {
    setActive.mutate(
      { id: row.id, active: true },
      {
        onSuccess: () => toast.success(`“${row.label}” activated`),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  function confirmDeactivate() {
    if (!deactivating) return
    const row = deactivating
    setActive.mutate(
      { id: row.id, active: false },
      {
        onSuccess: () => toast.success(`“${row.label}” deactivated`),
        onError: (error) => toast.error(errorMessage(error)),
        onSettled: () => setDeactivating(null),
      },
    )
  }

  function makeDefault(row: LookupRow) {
    setDefault.mutate(row.id, {
      onSuccess: () => toast.success(`“${row.label}” is now the default`),
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  function toggleDone(row: Status) {
    update.mutate(
      { id: row.id, is_done: !row.is_done },
      {
        onSuccess: (saved) =>
          toast.success(
            saved.is_done
              ? `“${saved.label}” counts as done`
              : `“${saved.label}” no longer counts as done`,
          ),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  function toggleOm(row: Category) {
    updateCategory.mutate(
      { id: row.id, requires_om_project: !row.requires_om_project },
      {
        onSuccess: (saved) =>
          toast.success(
            saved.requires_om_project
              ? `“${saved.label}” rows now offer an O&M project`
              : `“${saved.label}” rows no longer offer an O&M project`,
          ),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  const columns: Column<LookupRow>[] = [
    {
      key: 'label',
      header: 'Label',
      isTitle: true,
      cell: (row) => (
        <span className="flex flex-wrap items-center gap-2">
          {list.hasColor && <ColorDot color={rowColor(row)} />}
          <span className="break-words">{row.label}</span>
          {hasDefault(row) && row.is_default && (
            <span className="badge badge-sm badge-primary">Default</span>
          )}
          {!row.is_active && <span className="badge badge-sm badge-neutral">Inactive</span>}
        </span>
      ),
    },
    {
      key: 'order',
      header: 'Order',
      className: 'md:w-28',
      cell: (row) => {
        const index = items.findIndex((item) => item.id === row.id)
        return (
          <span className="join">
            <button
              type="button"
              className="btn btn-sm btn-square join-item"
              onClick={() => move(index, -1)}
              disabled={index === 0 || reorder.isPending}
              aria-label={`Move “${row.label}” up`}
            >
              <ArrowUpIcon className="size-4" />
            </button>
            <button
              type="button"
              className="btn btn-sm btn-square join-item"
              onClick={() => move(index, 1)}
              disabled={index === items.length - 1 || reorder.isPending}
              aria-label={`Move “${row.label}” down`}
            >
              <ArrowDownIcon className="size-4" />
            </button>
          </span>
        )
      },
    },
    ...(list.kind === 'statuses'
      ? [
          {
            key: 'done',
            header: 'Counts as done',
            className: 'md:w-36',
            cell: (row: LookupRow) =>
              isStatus(row) && (
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={row.is_done}
                  onChange={() => toggleDone(row)}
                  disabled={update.isPending}
                  aria-label={`“${row.label}” counts as done`}
                />
              ),
          },
        ]
      : []),
    ...(list.kind === 'categories'
      ? [
          {
            key: 'om',
            header: 'Has O&M project',
            className: 'md:w-40',
            cell: (row: LookupRow) =>
              isCategory(row) && (
                <input
                  type="checkbox"
                  className="toggle toggle-primary"
                  checked={row.requires_om_project}
                  onChange={() => toggleOm(row)}
                  disabled={updateCategory.isPending}
                  aria-label={`“${row.label}” has an O&M project`}
                />
              ),
          },
        ]
      : []),
    ...(list.kind === 'activity-groups'
      ? [
          {
            key: 'members',
            header: 'Activities',
            className: 'md:w-48',
            cell: (row: LookupRow) =>
              isGroup(row) && (
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setGroupMembers(row)}
                  aria-label={`Edit the activities of “${row.label}”`}
                >
                  <ListIcon className="size-4" />
                  {row.activity_ids.length === 1
                    ? '1 activity'
                    : `${row.activity_ids.length} activities`}
                </button>
              ),
          },
        ]
      : []),
    {
      key: 'actions',
      header: 'Actions',
      hideLabelOnCard: true,
      className: 'md:text-right',
      cell: (row) => {
        const isDefault = hasDefault(row) && row.is_default
        return (
          <div className="flex flex-wrap gap-2 md:flex-nowrap md:justify-end">
            <button type="button" className="btn btn-sm" onClick={() => setEditing(row)}>
              <PencilIcon className="size-4" />
              Edit
            </button>
            {supportsDefault && row.is_active && !isDefault && (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => makeDefault(row)}
                disabled={setDefault.isPending}
              >
                <StarIcon className="size-4" />
                Make default
              </button>
            )}
            {row.is_active ? (
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => setDeactivating(row)}
                disabled={isDefault}
                title={isDefault ? `Make another ${list.singular} the default first` : undefined}
              >
                Deactivate
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => activate(row)}
                disabled={setActive.isPending}
              >
                Activate
              </button>
            )}
          </div>
        )
      },
    },
  ]

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-base-content/80">
          {list.hint} Inactive values are hidden from selection but stay on existing records.
        </p>
        <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
          <PlusIcon />
          Add {list.singular}
        </button>
      </div>

      <DataTable
        caption={list.label}
        columns={columns}
        rows={rows.data}
        rowKey={(row) => row.id}
        isLoading={rows.isPending}
        error={rows.error}
        onRetry={() => void rows.refetch()}
        empty={
          <EmptyState
            icon={<ListIcon className="size-6" />}
            title={`No ${list.label.toLowerCase()} yet`}
            description={`Add the first ${list.singular}.`}
            action={
              <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
                <PlusIcon />
                Add {list.singular}
              </button>
            }
          />
        }
      />

      <Modal
        open={editing !== undefined}
        title={editing ? `Edit ${list.singular}` : `Add ${list.singular}`}
        onClose={() => setEditing(undefined)}
      >
        {editing !== undefined && (
          <ValueFormBody list={list} row={editing} onDone={() => setEditing(undefined)} />
        )}
      </Modal>

      <Modal
        open={groupMembers !== null}
        title={`Activities in “${groupMembers?.label ?? ''}”`}
        onClose={() => setGroupMembers(null)}
      >
        {groupMembers && (
          <GroupActivitiesEditor group={groupMembers} onDone={() => setGroupMembers(null)} />
        )}
      </Modal>

      <ConfirmModal
        open={deactivating !== null}
        title={`Deactivate ${list.singular}?`}
        confirmLabel="Deactivate"
        isPending={setActive.isPending}
        onConfirm={confirmDeactivate}
        onCancel={() => setDeactivating(null)}
      >
        <p>
          <strong>{deactivating?.label}</strong> will no longer be offered in selects. Records that
          already use it keep it. You can activate it again at any time.
        </p>
      </ConfirmModal>
    </>
  )
}

// ------------------------------------------------------------------ tab

export default function DropdownsTab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const param = searchParams.get('list')
  const active: LookupKind = isKind(param) ? param : 'categories'
  const list = LISTS.find((item) => item.kind === active) ?? LISTS[0]

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-base-content/80">
          Load categories, projects and activities from the productivity log’s Data tab.
        </p>
        <ImportDataTab />
      </div>
      <div className="mb-4 overflow-x-auto">
        <div
          role="tablist"
          aria-label="Dropdown lists"
          className="tabs tabs-border w-max min-w-full"
        >
          {LISTS.map((item) => (
            <button
              key={item.kind}
              type="button"
              role="tab"
              id={`dropdown-tab-${item.kind}`}
              aria-selected={item.kind === active}
              aria-controls="dropdown-tabpanel"
              className={`tab ${item.kind === active ? 'tab-active' : ''}`}
              onClick={() => setSearchParams({ tab: 'dropdowns', list: item.kind })}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <section id="dropdown-tabpanel" role="tabpanel" aria-labelledby={`dropdown-tab-${active}`}>
        {/* key: reset modal state when switching lists. */}
        <LookupList key={list.kind} list={list} />
      </section>
    </>
  )
}
