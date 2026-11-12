import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router'
import { z } from 'zod'

import { usePasswordResetCheck, useResetPassword } from '../../api/auth'
import { ApiError } from '../../api/client'
import ErrorAlert from '../../components/ErrorAlert'
import { InputField, SubmitButton } from '../../components/FormField'
import { CheckCircleIcon } from '../../components/icons'
import { SkeletonText } from '../../components/Skeleton'
import AuthLayout from '../../layouts/AuthLayout'
import {
  applyFieldErrors,
  confirmPasswordSchema,
  newPasswordSchema,
  PASSWORDS_DIFFER,
} from '../../lib/forms'

const schema = z
  .object({ new_password: newPasswordSchema, confirm_password: confirmPasswordSchema })
  .refine((data) => data.new_password === data.confirm_password, {
    message: PASSWORDS_DIFFER,
    path: ['confirm_password'],
  })
type ResetForm = z.infer<typeof schema>

function InvalidLink() {
  return (
    <AuthLayout title="Link not valid">
      <p>
        This password reset link is invalid, already used, or expired. Ask your admin for a new one.
      </p>
      <Link to="/login" className="btn btn-primary">
        Go to sign in
      </Link>
    </AuthLayout>
  )
}

export default function ResetPasswordPage() {
  const { token = '' } = useParams()
  const check = usePasswordResetCheck(token)
  const reset = useResetPassword(token)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ResetForm>({ resolver: zodResolver(schema) })

  if (reset.isSuccess) {
    return (
      <AuthLayout title="Password updated">
        <div role="status" className="alert alert-success">
          <CheckCircleIcon />
          <span>Your new password is set. Sign in with it now.</span>
        </div>
        <Link to="/login" className="btn btn-primary">
          Go to sign in
        </Link>
      </AuthLayout>
    )
  }
  if (check.isPending) {
    return (
      <AuthLayout title="Set a new password">
        <SkeletonText lines={4} />
      </AuthLayout>
    )
  }
  if (check.isError) {
    return (
      <AuthLayout title="Set a new password">
        <ErrorAlert error={check.error} onRetry={() => void check.refetch()} />
      </AuthLayout>
    )
  }
  if (!check.data.valid) return <InvalidLink />

  function onSubmit({ new_password }: ResetForm) {
    reset.mutate(
      { new_password },
      {
        onError: (error) => applyFieldErrors(error, setError, ['new_password']),
      },
    )
  }

  // The link was used or expired after the page loaded.
  if (reset.error instanceof ApiError && reset.error.code === 'reset_invalid')
    return <InvalidLink />

  return (
    <AuthLayout
      title="Set a new password"
      subtitle={
        check.data.username && (
          <>
            For user <strong>{check.data.username}</strong>. You will be signed out everywhere.
          </>
        )
      }
    >
      {reset.isError && <ErrorAlert error={reset.error} />}
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => void handleSubmit(onSubmit)(e)}
        noValidate
      >
        <InputField
          label="New password"
          type="password"
          autoComplete="new-password"
          hint="At least 8 characters."
          error={errors.new_password?.message}
          {...register('new_password')}
        />
        <InputField
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          error={errors.confirm_password?.message}
          {...register('confirm_password')}
        />
        <SubmitButton isPending={reset.isPending} className="mt-3">
          Set password
        </SubmitButton>
      </form>
    </AuthLayout>
  )
}
