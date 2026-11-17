import { useState, type FormEvent } from 'react'

import { errorMessage } from '../../api/client'
import { useImportDataTab, type DataTabImport } from '../../api/lookups'
import { AlertIcon, UploadIcon } from '../../components/icons'
import Modal from '../../components/Modal'
import { useToast } from '../../components/toast-context'

const CREATED: { key: keyof DataTabImport['created']; label: string }[] = [
  { key: 'categories', label: 'Categories' },
  { key: 'projects', label: 'Projects' },
  { key: 'activity_groups', label: 'Activity groups' },
  { key: 'activities', label: 'Activities' },
  { key: 'om_projects', label: 'O&M projects' },
]

const LINKED: { key: keyof DataTabImport['linked']; label: string }[] = [
  { key: 'project_categories', label: 'Projects linked to a category' },
  { key: 'project_groups', label: 'Projects given an activity group' },
  { key: 'group_activities', label: 'Activities added to a group' },
  { key: 'om_flags', label: 'Categories now offering an O&M project' },
]

function NoteList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div className="mt-4">
      <h4 className="text-sm font-semibold">{title}</h4>
      <ul className="mt-1 list-disc pl-5 text-sm break-words text-base-content/80">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function CountTable({
  caption,
  rows,
}: {
  caption: string
  rows: { label: string; value: number }[]
}) {
  return (
    <table className="table table-sm">
      <caption className="text-left text-sm font-semibold">{caption}</caption>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <td className="pl-0">{row.label}</td>
            <td className="pr-0 text-right font-semibold tabular-nums">{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ImportResult({ result }: { result: DataTabImport }) {
  const nothingNew =
    Object.values(result.created).every((n) => n === 0) &&
    Object.values(result.linked).every((n) => n === 0)
  return (
    <div>
      {nothingNew && (
        <p className="mb-3 rounded-box bg-base-200 p-3 text-sm">
          Everything in the file was already here. Nothing changed.
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <CountTable
          caption="Created"
          rows={CREATED.map(({ key, label }) => ({ label, value: result.created[key] }))}
        />
        <CountTable
          caption="Linked"
          rows={LINKED.map(({ key, label }) => ({ label, value: result.linked[key] }))}
        />
      </div>
      {result.group_conflicts.length > 0 && (
        <div role="alert" className="alert alert-warning mt-4 items-start text-sm">
          <AlertIcon className="size-5 shrink-0" />
          <div className="min-w-0 break-words">
            <p className="font-semibold">Activity groups kept as they are</p>
            <ul className="mt-1 list-disc pl-5">
              {result.group_conflicts.map((c) => (
                <li key={c.project}>
                  {c.project}: keeps “{c.current_group}” (the file says “{c.file_group}”)
                </li>
              ))}
            </ul>
            <p className="mt-1">Change them in Admin › Projects if the file is right.</p>
          </div>
        </div>
      )}
      <NoteList
        title="Groups imported without a project (assign them in Projects)"
        items={result.unlinked_groups}
      />
      <NoteList
        title="Inactive values the file mentions (linked, still inactive)"
        items={result.inactive_reused}
      />
      <NoteList title="Columns not recognised (ignored)" items={result.unrecognised_columns} />
      <NoteList title="Empty columns (ignored)" items={result.empty_columns} />
    </div>
  )
}

/** "Import from sheet": upload the Data tab CSV, then show what was created and linked. */
export default function ImportDataTab() {
  const toast = useToast()
  const upload = useImportDataTab()
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const result = upload.data

  function close() {
    setOpen(false)
    setFile(null)
    setError(null)
    upload.reset()
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!file) {
      setError('Choose the CSV file')
      return
    }
    upload.mutate(file, {
      onSuccess: () => toast.success('Data tab imported'),
      onError: (err) => setError(errorMessage(err)),
    })
  }

  return (
    <>
      <button type="button" className="btn" onClick={() => setOpen(true)}>
        <UploadIcon />
        Import from sheet
      </button>
      <Modal
        open={open}
        title={result ? 'Import finished' : 'Import from sheet'}
        onClose={close}
        locked={upload.isPending}
      >
        {result ? (
          <>
            <ImportResult result={result} />
            <div className="modal-action">
              <button type="button" className="btn btn-primary" onClick={close}>
                Done
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={submit} noValidate>
            <p className="text-sm text-base-content/80">
              Upload the productivity log’s <strong>Data</strong> tab saved as CSV (in Google
              Sheets: File › Download › Comma-separated values, with the Data tab open). Missing
              categories, projects, activity groups, activities and O&amp;M projects are created and
              linked. Existing values are reused; nothing is deleted or renamed, so it is safe to
              import again.
            </p>
            <fieldset className="fieldset mt-3">
              <label className="fieldset-legend pb-0 text-sm" htmlFor="data-tab-file">
                CSV file
              </label>
              <input
                id="data-tab-file"
                type="file"
                accept=".csv,text/csv"
                className={`file-input w-full ${error ? 'file-input-error' : ''}`}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'data-tab-file-error' : undefined}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null)
                  setError(null)
                }}
              />
              {error && (
                <p id="data-tab-file-error" className="flex items-center gap-1 text-sm">
                  <AlertIcon className="size-4 shrink-0" />
                  {error}
                </p>
              )}
            </fieldset>
            <div className="modal-action">
              <button type="button" className="btn btn-ghost" onClick={close}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={upload.isPending}>
                {upload.isPending && <span className="loading loading-spinner loading-sm" />}
                Import
              </button>
            </div>
          </form>
        )}
      </Modal>
    </>
  )
}
