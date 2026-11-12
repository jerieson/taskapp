import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router'
import { z } from 'zod'

import { googleLoginUrl, useAcceptInvite, useInvite, type Role } from '../../api/auth'
import { ApiError } from '../../api/client'
import ErrorAlert from '../../components/ErrorAlert'
import { InputField, SubmitButton } from '../../components/FormField'
import { SkeletonText } from '../../components/Skeleton'
import AuthLayout from '../../layouts/AuthLayout'
import {
  applyFieldErrors,
  confirmPasswordSchema,
  newPasswordSchema,
  PASSWORDS_DIFFER,
  usernameSchema,
} from '../../lib/forms'
import GoogleButton from './GoogleButton'

const schema = z
  .object({
    username: usernameSchema,
    password: newPasswordSchema,
    confirm_password: confirmPasswordSchema,
  })
  .refine((data) => data.password === data.confirm_password, {
    message: PASSWORDS_DIFFER,
    path: ['confirm_password'],
  })
type InviteForm = z.infer<typeof schema>

const ROLE_LABEL: Record<Role, string> = { admin: 'Admin', manager: 'Manager', dev: 'Developer' }

function InvalidLink() {
  return (
    <AuthLayout title="Invite not valid">
      <p>This invite link is invalid, already used, or expired. Ask your admin for a new one.</p>
      <Link to="/login" className="btn btn-primary">
        Go to sign in
      </Link>
    </AuthLayout>
  )
}

export default function InvitePage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const invite = useInvite(token)
  const accept = useAcceptInvite(token)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<InviteForm>({ resolver: zodResolver(schema) })

  if (invite.isPending) {
    return (
      <AuthLayout title="Accept invite">
        <SkeletonText lines={4} />
      </AuthLayout>
    )
  }
  if (invite.error instanceof ApiError && invite.error.status === 404) return <InvalidLink />
  if (invite.isError) {
    return (
      <AuthLayout title="Accept invite">
        <ErrorAlert error={invite.error} onRetry={() => void invite.refetch()} />
      </AuthLayout>
    )
  }

  const details = invite.data

  function onSubmit({ username, password }: InviteForm) {
    accept.mutate(
      { username, password },
      {
        onSuccess: () => void navigate('/today', { replace: true }),
        onError: (error) => applyFieldErrors(error, setError, ['username', 'password']),
      },
    )
  }

  const acceptError =
    accept.error instanceof ApiError && Object.keys(accept.error.fields).length > 0
      ? null
      : accept.error

  return (
    <AuthLayout
      title="Accept invite"
      subtitle={
        <>
          You are invited to <strong>{details.team_name}</strong> as{' '}
          <strong>{ROLE_LABEL[details.role]}</strong>.
        </>
      }
    >
      {acceptError && <ErrorAlert error={acceptError} />}

      <GoogleButton href={googleLoginUrl(token)} />
      <p className="text-center text-xs text-base-content/80">
        Use the Google account for {details.email}.
      </p>

      <div className="divider my-0 text-sm">or create a password</div>

      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => void handleSubmit(onSubmit)(e)}
        noValidate
      >
        <InputField label="Email" value={details.email} readOnly disabled />
        <InputField
          label="Username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          hint="3-50 characters: letters, digits, dot, underscore or hyphen."
          error={errors.username?.message}
          {...register('username')}
        />
        <InputField
          label="Password"
          type="password"
          autoComplete="new-password"
          hint="At least 8 characters."
          error={errors.password?.message}
          {...register('password')}
        />
        <InputField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          error={errors.confirm_password?.message}
          {...register('confirm_password')}
        />
        <SubmitButton isPending={accept.isPending} className="mt-3">
          Create account
        </SubmitButton>
      </form>
    </AuthLayout>
  )
}
