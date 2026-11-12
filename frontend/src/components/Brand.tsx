import { Link } from 'react-router'

function Mark({ nameClassName }: { nameClassName?: string }) {
  return (
    <>
      <span className="flex size-8 shrink-0 items-center justify-center rounded-field bg-secondary text-secondary-content">
        T
      </span>
      <span className={nameClassName}>Taskapp</span>
    </>
  )
}

interface BrandProps {
  /** Link to /today. */
  linked?: boolean
  /** Classes for the app name, e.g. to hide it in the collapsed sidebar. */
  nameClassName?: string
}

/** App name and logo mark. */
export default function Brand({ linked = false, nameClassName }: BrandProps) {
  const className = 'flex items-center gap-2 text-lg font-bold'
  return linked ? (
    <Link to="/today" className={className}>
      <Mark nameClassName={nameClassName} />
    </Link>
  ) : (
    <span className={className}>
      <Mark nameClassName={nameClassName} />
    </span>
  )
}
