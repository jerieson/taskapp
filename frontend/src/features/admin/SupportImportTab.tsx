/*
 * Admin › Support import: upload the team's support dictionary sheet (CSV), preview
 * what would be imported (nothing saved), then import it.
 */
import { useId, useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { errorMessage } from '../../api/client'
import { useImportSupport, type SupportImport } from '../../api/support'
import { AlertIcon, CheckCircleIcon, UploadIcon } from '../../components/icons'
import { useToast } from '../../components/toast-context'

function Counts({ result }: { result: SupportImport }) {
  const stats = [
    { label: result.dry_run ? 'Would be created' : 'Created', value: result.created },
    { label: 'Skipped', value: result.skipped },
    { label: 'New types', value: result.types_created.length },
  ]
  return (
    <div className="stats stats-vertical w-full border border-base-300 bg-base-100 sm:stats-horizontal">
      {stats.map((stat) => (
        <div key={stat.label} className="stat">
          <div className="stat-title text-base-content/80">{stat.label}</div>
          <div className="stat-value text-3xl tabular-nums">{stat.value}</div>
        </div>
      ))}
    </div>
  )
}

function NoteList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div>
      <h4 className="text-sm font-semibold">{title}</h4>
      <ul className="mt-1 list-disc pl-5 text-sm break-words text-base-content/80">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

function ImportReport({ result }: { result: SupportImport }) {
  const verb = result.dry_run ? 'will be' : 'were'
  return (
    <div className="flex flex-col gap-4">
      <Counts result={result} />
      <NoteList title={`Types that ${verb} created`} items={result.types_created} />
      <NoteList
        title="Types matched by the start of their name"
        items={result.types_matched.map((m) => `“${m.file_label}” → ${m.type_label}`)}
      />
      <NoteList
        title={`Authors matched to a user (they ${verb} the authors)`}
        items={result.authors_matched}
      />
      <NoteList
        title={`Authors without a user (kept in the notes; you ${result.dry_run ? 'will be' : 'are'} the author)`}
        items={result.authors_unmatched}
      />
      {result.errors.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold">Skipped rows</h4>
          <div className="mt-1 max-h-72 overflow-auto rounded-box border border-base-300">
            <table className="table table-sm">
              <thead>
                <tr>
                  <th scope="col" className="w-16">
                    Row
                  </th>
                  <th scope="col">Reason</th>
                </tr>
              </thead>
              <tbody>
                {result.errors.map((error) => (
                  <tr key={`${error.row}-${error.message}`}>
                    <td className="tabular-nums">{error.row}</td>
                    <td className="break-words">{error.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export default function SupportImportTab() {
  const toast = useToast()
  const upload = useImportSupport()
  const inputId = useId()
  const [file, setFile] = useState<File | null>(null)
  const [inputKey, setInputKey] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<SupportImport | null>(null)

  function run(dryRun: boolean) {
    if (!file) {
      setError('Choose the CSV file')
      return
    }
    setError(null)
    upload.mutate(
      { file, dryRun },
      {
        onSuccess: (data) => {
          setResult(data)
          if (!data.dry_run) {
            toast.success(`${data.created} ${data.created === 1 ? 'entry' : 'entries'} imported`)
          }
        },
        onError: (err) => setError(errorMessage(err)),
      },
    )
  }

  function preview(event: FormEvent) {
    event.preventDefault()
    run(true)
  }

  function reset() {
    setFile(null)
    setResult(null)
    setError(null)
    setInputKey((k) => k + 1)
  }

  const imported = result !== null && !result.dry_run

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold">Import the support dictionary</h2>
        <p className="mt-1 text-sm text-base-content/80">
          Upload the team’s support dictionary sheet saved as CSV (columns: author, Type, Project,
          Module, Sub-module, Concern, Cause, Resolution, Query, Notes, Date Inputted). Preview
          first: nothing is saved until you import. Rows already in the dictionary (same type,
          project, module, sub-module and concern) are skipped, so importing the same file again
          adds nothing.
        </p>
      </div>

      {imported ? (
        <div role="status" className="alert alert-success">
          <CheckCircleIcon />
          <span>Import finished.</span>
        </div>
      ) : (
        <form onSubmit={preview} noValidate className="flex flex-col gap-3">
          <fieldset className="fieldset">
            <label className="fieldset-legend pb-0 text-sm" htmlFor={inputId}>
              CSV file
            </label>
            <input
              key={inputKey}
              id={inputId}
              type="file"
              accept=".csv,text/csv"
              className={`file-input w-full ${error ? 'file-input-error' : ''}`}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${inputId}-error` : undefined}
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null)
                setResult(null)
                setError(null)
              }}
            />
            {error && (
              <p id={`${inputId}-error`} className="flex items-center gap-1.5 text-sm">
                <span className="inline-flex rounded-full bg-error p-0.5 text-error-content">
                  <AlertIcon className="size-3.5" />
                </span>
                {error}
              </p>
            )}
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn" disabled={upload.isPending}>
              {upload.isPending && upload.variables?.dryRun && (
                <span className="loading loading-spinner loading-sm" />
              )}
              Preview
            </button>
            {result?.dry_run && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={upload.isPending || result.created === 0}
                onClick={() => run(false)}
              >
                {upload.isPending && !upload.variables?.dryRun ? (
                  <span className="loading loading-spinner loading-sm" />
                ) : (
                  <UploadIcon />
                )}
                Import {result.created} {result.created === 1 ? 'entry' : 'entries'}
              </button>
            )}
          </div>
        </form>
      )}

      {result && (
        <section aria-label={result.dry_run ? 'Preview' : 'Result'} className="flex flex-col gap-3">
          <h3 className="font-semibold">{result.dry_run ? 'Preview' : 'Result'}</h3>
          {result.dry_run && result.created === 0 && (
            <p className="rounded-box bg-base-200 p-3 text-sm">
              Nothing new to import: every row is already in the dictionary or was skipped.
            </p>
          )}
          <ImportReport result={result} />
        </section>
      )}

      {imported && (
        <div className="flex flex-wrap gap-2">
          <Link to="/support" className="btn btn-primary">
            Open the support dictionary
          </Link>
          <button type="button" className="btn" onClick={reset}>
            Import another file
          </button>
        </div>
      )}
    </div>
  )
}
