import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { z } from 'zod'

import { errorMessage } from '../../api/client'
import {
  useCreateProject,
  useLookups,
  useProjectPage,
  useSetProjectActive,
  useUpdateProject,
  type Project,
} from '../../api/lookups'
import ConfirmModal from '../../components/ConfirmModal'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import { InputField, SelectField, SubmitButton, TextareaField } from '../../components/FormField'
import { FolderIcon, PencilIcon, PlusIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import Pagination from '../../components/Pagination'
import { useToast } from '../../components/toast-context'
import { applyFieldErrors } from '../../lib/forms'
import { formatDate } from '../../lib/format'

const projectSchema = z.object({
  name: z.string().trim().min(1, 'Enter a project name').max(100, 'Use at most 100 characters'),
  description: z.string().trim().max(2000, 'Use at most 2000 characters'),
  categoryIds: z.array(z.number()),
  activityGroupId: z.string(),
})
type ProjectForm = z.infer<typeof projectSchema>

/** Active values plus the inactive ones already on the project, in display order. */
function offered<T extends { id: number; is_active: boolean }>(rows: T[], keep: number[]): T[] {
  return rows.filter((row) => row.is_active || keep.includes(row.id))
}

function ProjectFormBody({ project, onDone }: { project: Project | null; onDone: () => void }) {
  const toast = useToast()
  const create = useCreateProject()
  const update = useUpdateProject()
  const mutation = project ? update : create
  const categories = useLookups('categories', true)
  const groups = useLookups('activity-groups', true)
  const keptCategories = project?.category_ids ?? []
  const keptGroup = project?.activity_group_id ?? null
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors },
  } = useForm<ProjectForm>({
    resolver: zodResolver(projectSchema),
    defaultValues: {
      name: project?.name ?? '',
      description: project?.description ?? '',
      categoryIds: keptCategories,
      activityGroupId: keptGroup === null ? '' : String(keptGroup),
    },
  })

  function onSubmit(data: ProjectForm) {
    const options = {
      onSuccess: (saved: Project) => {
        toast.success(project ? `Saved “${saved.name}”` : `Project “${saved.name}” created`)
        onDone()
      },
      onError: (error: unknown) => {
        if (!applyFieldErrors(error, setError, ['name', 'description'])) {
          toast.error(errorMessage(error))
        }
      },
    }
    const body = {
      name: data.name,
      description: data.description,
      category_ids: data.categoryIds,
      activity_group_id: data.activityGroupId ? Number(data.activityGroupId) : null,
    }
    if (project) update.mutate({ id: project.id, ...body }, options)
    else create.mutate(body, options)
  }

  return (
    <form onSubmit={(e) => void handleSubmit(onSubmit)(e)} noValidate>
      <InputField
        label="Name"
        autoFocus
        autoComplete="off"
        error={errors.name?.message}
        {...register('name')}
      />
      <Controller
        control={control}
        name="categoryIds"
        render={({ field }) => (
          <fieldset className="fieldset">
            <legend className="fieldset-legend pb-0 text-sm">Categories</legend>
            {categories.isPending ? (
              <span className="loading loading-dots loading-sm" aria-label="Loading categories" />
            ) : (
              <div className="grid gap-x-4 sm:grid-cols-2">
                {offered(categories.data ?? [], keptCategories).map((category) => (
                  <label
                    key={category.id}
                    className="label min-h-11 cursor-pointer gap-3 text-base-content"
                  >
                    <input
                      type="checkbox"
                      className="checkbox checkbox-primary"
                      checked={field.value.includes(category.id)}
                      onChange={(event) =>
                        field.onChange(
                          event.target.checked
                            ? [...field.value, category.id]
                            : field.value.filter((id) => id !== category.id),
                        )
                      }
                    />
                    <span className="break-words whitespace-normal">
                      {category.label}
                      {!category.is_active && ' (inactive)'}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <p className="text-xs text-base-content/80">
              Log rows can use this project only under these categories.
            </p>
            {errors.categoryIds?.message && <p className="text-sm">{errors.categoryIds.message}</p>}
          </fieldset>
        )}
      />
      <SelectField
        // Remount once options arrive so React Hook Form re-applies the value.
        key={groups.isPending ? 'loading' : 'ready'}
        label="Activity group"
        hint="Decides which activities can be logged against this project."
        disabled={groups.isPending}
        error={errors.activityGroupId?.message}
        {...register('activityGroupId')}
      >
        <option value="">No group</option>
        {offered(groups.data ?? [], keptGroup === null ? [] : [keptGroup]).map((group) => (
          <option key={group.id} value={group.id}>
            {group.is_active ? group.label : `${group.label} (inactive)`}
          </option>
        ))}
      </SelectField>
      <TextareaField
        label="Description (optional)"
        rows={3}
        error={errors.description?.message}
        {...register('description')}
      />
      <div className="modal-action">
        <button type="button" className="btn btn-ghost" onClick={onDone}>
          Cancel
        </button>
        <SubmitButton isPending={mutation.isPending}>
          {project ? 'Save' : 'Create project'}
        </SubmitButton>
      </div>
    </form>
  )
}

export default function ProjectsTab() {
  const toast = useToast()
  const [offset, setOffset] = useState(0)
  const projects = useProjectPage(offset)
  const setActive = useSetProjectActive()
  const categories = useLookups('categories', true)
  const groups = useLookups('activity-groups', true)
  const categoryLabel = new Map((categories.data ?? []).map((c) => [c.id, c.label]))
  const groupLabel = new Map((groups.data ?? []).map((g) => [g.id, g.label]))
  // undefined = closed, null = new project, Project = edit.
  const [editing, setEditing] = useState<Project | null | undefined>(undefined)
  const [deactivating, setDeactivating] = useState<Project | null>(null)

  function activate(project: Project) {
    setActive.mutate(
      { id: project.id, active: true },
      {
        onSuccess: () => toast.success(`“${project.name}” activated`),
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  function confirmDeactivate() {
    if (!deactivating) return
    const project = deactivating
    setActive.mutate(
      { id: project.id, active: false },
      {
        onSuccess: () => toast.success(`“${project.name}” deactivated`),
        onError: (error) => toast.error(errorMessage(error)),
        onSettled: () => setDeactivating(null),
      },
    )
  }

  const columns: Column<Project>[] = [
    {
      key: 'name',
      header: 'Name',
      isTitle: true,
      cell: (project) => (
        <span className="flex flex-wrap items-center gap-2">
          <span className="break-words">{project.name}</span>
          {!project.is_active && <span className="badge badge-sm badge-neutral">Inactive</span>}
        </span>
      ),
    },
    {
      key: 'categories',
      header: 'Categories',
      cell: (project) =>
        project.category_ids.length > 0 ? (
          <span className="flex flex-wrap gap-1">
            {project.category_ids.map((id) => (
              <span key={id} className="badge badge-sm h-auto badge-ghost break-words">
                {categoryLabel.get(id) ?? '…'}
              </span>
            ))}
          </span>
        ) : (
          <span className="text-base-content/80">—</span>
        ),
    },
    {
      key: 'group',
      header: 'Activity group',
      className: 'md:w-48',
      cell: (project) =>
        project.activity_group_id !== null ? (
          <span className="break-words">{groupLabel.get(project.activity_group_id) ?? '…'}</span>
        ) : (
          <span className="text-base-content/80">—</span>
        ),
    },
    {
      key: 'created',
      header: 'Created',
      cell: (project) => formatDate(project.created_at),
      className: 'md:w-32',
    },
    {
      key: 'actions',
      header: 'Actions',
      hideLabelOnCard: true,
      className: 'md:text-right',
      cell: (project) => (
        <div className="flex flex-wrap gap-2 md:flex-nowrap md:justify-end">
          <button type="button" className="btn btn-sm" onClick={() => setEditing(project)}>
            <PencilIcon className="size-4" />
            Edit
          </button>
          {project.is_active ? (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => setDeactivating(project)}
            >
              Deactivate
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => activate(project)}
              disabled={setActive.isPending}
            >
              Activate
            </button>
          )}
        </div>
      ),
    },
  ]

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Projects</h2>
        <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
          <PlusIcon />
          New project
        </button>
      </div>

      <DataTable
        caption="Projects"
        columns={columns}
        rows={projects.data?.items}
        rowKey={(project) => project.id}
        isLoading={projects.isPending}
        error={projects.error}
        onRetry={() => void projects.refetch()}
        empty={
          <EmptyState
            icon={<FolderIcon className="size-6" />}
            title="No projects yet"
            description="Projects let tasks and prod logs be grouped and reported on."
            action={
              <button type="button" className="btn btn-primary" onClick={() => setEditing(null)}>
                <PlusIcon />
                New project
              </button>
            }
          />
        }
      />
      {projects.data && (
        <Pagination
          total={projects.data.total}
          limit={projects.data.limit}
          offset={projects.data.offset}
          onChange={setOffset}
        />
      )}

      <Modal
        open={editing !== undefined}
        title={editing ? 'Edit project' : 'New project'}
        onClose={() => setEditing(undefined)}
      >
        {editing !== undefined && (
          <ProjectFormBody project={editing} onDone={() => setEditing(undefined)} />
        )}
      </Modal>

      <ConfirmModal
        open={deactivating !== null}
        title="Deactivate project?"
        confirmLabel="Deactivate"
        isPending={setActive.isPending}
        onConfirm={confirmDeactivate}
        onCancel={() => setDeactivating(null)}
      >
        <p>
          <strong>{deactivating?.name}</strong> will no longer be offered in selects. Tasks and logs
          that already use it keep it. You can activate it again at any time.
        </p>
      </ConfirmModal>
    </>
  )
}
