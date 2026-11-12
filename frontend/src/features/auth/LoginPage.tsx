import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useNavigate, useSearchParams } from 'react-router'
import { z } from 'zod'

import { googleLoginUrl, useLogin } from '../../api/auth'
import ErrorAlert from '../../components/ErrorAlert'
import { InputField, SubmitButton } from '../../components/FormField'
import AuthLayout from '../../layouts/AuthLayout'
import { applyFieldErrors, safeNextPath } from '../../lib/forms'
import GoogleButton from './GoogleButton'

const schema = z.object({
  username: z.string().trim().min(1, 'Enter your username'),
  password: z.string().min(1, 'Enter your password'),
})
type LoginForm = z.infer<typeof schema>

// Codes the backend puts in /login?error=<code> after a failed Google sign-in.
const GOOGLE_ERRORS: Record<string, string> = {
  google_not_configured: 'Google sign-in is not configured on this server.',
  google_cancelled: 'Google sign-in was cancelled.',
  google_state_invalid: 'The Google sign-in session expired. Please try again.',
  google_failed: 'Google sign-in failed. Please try again.',
  google_email_unverified: 'Your Google email address is not verified.',
  google_account_not_found:
    'No account or pending invite exists for this Google email. Ask your admin for an invite.',
  google_account_conflict: 'This account is already linked to a different Google account.',
  account_inactive: 'This account has been deactivated.',
  invite_invalid: 'This invite link is invalid or has expired.',
  invite_email_mismatch: 'Sign in with the Google account for the invited email address.',
  email_taken: 'A user with this email already exists. Sign in instead.',
  account_conflict: 'This account already exists. Sign in instead.',
}

export default function LoginPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const login = useLogin()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginForm>({ resolver: zodResolver(schema) })

  const googleError = params.get('error')
  const next = safeNextPath(params.get('next'))

  function onSubmit(data: LoginForm) {
    login.mutate(data, {
      onSuccess: () => void navigate(next ?? '/today', { replace: true }),
      onError: (error) => applyFieldErrors(error, setError, ['username', 'password']),
    })
  }

  return (
    <AuthLayout title="Sign in" subtitle="Welcome back. Sign in to continue.">
      {googleError && !login.isError && (
        <div role="alert" className="alert alert-warning">
          {GOOGLE_ERRORS[googleError] ?? 'Google sign-in failed. Please try again.'}
        </div>
      )}
      {login.isError && <ErrorAlert error={login.error} />}

      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => void handleSubmit(onSubmit)(e)}
        noValidate
      >
        <InputField
          label="Username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          error={errors.username?.message}
          {...register('username')}
        />
        <InputField
          label="Password"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register('password')}
        />
        <SubmitButton isPending={login.isPending} className="mt-3">
          Sign in
        </SubmitButton>
      </form>

      <div className="divider my-0 text-sm">or</div>
      <GoogleButton href={googleLoginUrl()} />
    </AuthLayout>
  )
}
