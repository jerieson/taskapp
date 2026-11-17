import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { errorMessage } from '../../api/client'
import {
  useCreateProject,
  useProjectPage,
  useSetProjectActive,
  useUpdateProject,
  type Project,
} from '../../api/lookups'
import ConfirmModal from '../../components/ConfirmModal'
import DataTable, { type Column } from '../../components/DataTable'
import EmptyState from '../../components/EmptyState'
import { InputField, SubmitButton, TextareaField } from '../../components/FormField'
import { FolderIcon, PencilIcon, PlusIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import Pagination from '../../components/Pagination'
import { useToast } from '../../components/toast-context'
import { applyFieldErrors } from '../../lib/forms'
import { formatDate } from '../../lib/format'

const projectSchema = z.object({
  name: z.string().trim().min(1, 'Enter a project name').max(100, 'Use at most 100 characters'),
  description: z.string().trim().max(2000, 'Use at most 2000 characters'),
})
type ProjectForm = z.infer<typeof projectSchema>

function ProjectFormBody({ project, onDone }: { project: Project | null; onDone: () => void }) {
  const toast = useToast()
  const create = useCreateProject()
  const update = useUpdateProject()
  const mutation = project ? update : create
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ProjectForm>({
    resolver: zodResolver(projectSchema),
    defaultValues: { name: project?.name ?? '', description: project?.description ?? '' },
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
    if (project) update.mutate({ id: project.id, ...data }, options)
    else create.mutate(data, options)
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
      <TextareaField
        label="Description (optional)"
        rows={4}
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
      key: 'description',
      header: 'Description',
      cell: (project) =>
        project.description ? (
          <span className="line-clamp-2 break-words text-base-content/80">
            {project.description}
          </span>
        ) : (
          <span className="text-base-content/80">—</span>
        ),
    },
    {
      key: 'created',
      header: 'Created',
      cell: (project) => formatDate(project.created_at),
      className: 'md:w-36',
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
