import { Link } from 'react-router'

import EmptyState from '../components/EmptyState'

export default function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      description="This page does not exist or you do not have access to it."
      action={
        <Link to="/today" className="btn btn-primary">
          Go to Today
        </Link>
      }
    />
  )
}
