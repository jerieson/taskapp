import { GoogleIcon } from '../../components/icons'

/** Full-page link to the backend's Google OAuth start endpoint. */
export default function GoogleButton({
  href,
  label = 'Continue with Google',
}: {
  href: string
  label?: string
}) {
  return (
    <a href={href} className="btn w-full border-base-300 bg-base-100">
      <GoogleIcon />
      {label}
    </a>
  )
}
