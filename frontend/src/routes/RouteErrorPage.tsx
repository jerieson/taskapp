import { isRouteErrorResponse, Link, useRouteError } from 'react-router'

/** Last-resort error screen for errors thrown while rendering a route. */
export default function RouteErrorPage() {
  const error = useRouteError()
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : 'Something went wrong while showing this page.'

  return (
    <main className="flex min-h-screen items-center justify-center bg-base-100 p-4 text-base-content">
      <div className="card w-full max-w-md bg-base-200">
        <div className="card-body items-center text-center">
          <h1 className="card-title text-2xl">Unexpected error</h1>
          <p>{message}</p>
          <div className="card-actions mt-2">
            <button type="button" className="btn" onClick={() => window.location.reload()}>
              Reload
            </button>
            <Link to="/today" className="btn btn-primary">
              Go to Today
            </Link>
          </div>
        </div>
      </div>
    </main>
  )
}
