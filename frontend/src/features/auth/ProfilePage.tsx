import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'

import { useChangePassword, useCurrentUser, type CurrentUser } from '../../api/auth'
import { errorMessage } from '../../api/client'
import { InputField, SubmitButton } from '../../components/FormField'
import PageHeader from '../../components/PageHeader'
import { useToast } from '../../components/toast-context'
import {
  applyFieldErrors,
  confirmPasswordSchema,
  newPasswordSchema,
  PASSWORDS_DIFFER,
} from '../../lib/forms'
import { ROLE_LABEL } from '../../lib/labels'
import { useTheme, type ThemeMode } from '../../lib/theme'

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'Enter your current password'),
    new_password: newPasswordSchema,
    confirm_password: confirmPasswordSchema,
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: PASSWORDS_DIFFER,
    path: ['confirm_password'],
  })
type PasswordForm = z.infer<typeof passwordSchema>

function AccountCard({ user }: { user: CurrentUser }) {
  const rows: [string, string][] = [
    ['Username', user.username],
    ['Email', user.email],
    ['Role', ROLE_LABEL[user.role]],
    ['Team', user.team?.name ?? '—'],
    ['Google sign-in', user.google_linked ? 'Linked' : 'Not linked'],
  ]
  return (
    <section className="card card-border border-base-300 bg-base-100">
      <div className="card-body">
        <h2 className="card-title">Account</h2>
        <dl className="flex flex-col gap-3 text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="flex flex-col sm:flex-row sm:gap-4">
              <dt className="text-base-content/80 sm:w-32 sm:shrink-0">{label}</dt>
              <dd className="min-w-0 font-medium break-words">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

function ThemeCard() {
  const { mode, setMode } = useTheme()
  return (
    <section className="card card-border border-base-300 bg-base-100">
      <div className="card-body">
        <h2 id="theme-heading" className="card-title">
          Theme
        </h2>
        <p className="text-sm text-base-content/80">
          System follows your device&apos;s light or dark setting.
        </p>
        <div role="radiogroup" aria-labelledby="theme-heading" className="join w-full sm:w-auto">
          {THEME_OPTIONS.map((option) => (
            <input
              key={option.value}
              type="radio"
              name="theme"
              className="btn join-item flex-1 sm:flex-none"
              aria-label={option.label}
              checked={mode === option.value}
              onChange={() => setMode(option.value)}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

function ChangePasswordCard() {
  const toast = useToast()
  const changePassword = useChangePassword()
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<PasswordForm>({ resolver: zodResolver(passwordSchema) })

  function onSubmit({ current_password, new_password }: PasswordForm) {
    changePassword.mutate(
      { current_password, new_password },
      {
        onSuccess: () => {
          reset()
          toast.success('Password changed. Your other sessions were signed out.')
        },
        onError: (error) => {
          const matched = applyFieldErrors(error, setError, ['current_password', 'new_password'])
          if (!matched) toast.error(errorMessage(error))
        },
      },
    )
  }

  return (
    <section className="card card-border border-base-300 bg-base-100">
      <div className="card-body">
        <h2 className="card-title">Change password</h2>
        <p className="text-sm text-base-content/80">
          Changing it signs you out on every other device.
        </p>
        <form
          className="flex max-w-md flex-col gap-2"
          onSubmit={(e) => void handleSubmit(onSubmit)(e)}
          noValidate
        >
          <InputField
            label="Current password"
            type="password"
            autoComplete="current-password"
            error={errors.current_password?.message}
            {...register('current_password')}
          />
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
          <SubmitButton isPending={changePassword.isPending} className="mt-3 sm:self-start">
            Change password
          </SubmitButton>
        </form>
      </div>
    </section>
  )
}

function NoPasswordCard() {
  return (
    <section className="card card-border border-base-300 bg-base-100">
      <div className="card-body">
        <h2 className="card-title">Password</h2>
        <p className="text-sm">
          This account signs in with Google and has no password. Ask an admin for a password reset
          link to set one.
        </p>
      </div>
    </section>
  )
}

export default function ProfilePage() {
  const { data: user } = useCurrentUser()
  // RequireAuth guarantees a user here.
  if (!user) return null

  return (
    <>
      <PageHeader title="Profile" description="Your account, theme and password." />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <AccountCard user={user} />
          <ThemeCard />
        </div>
        {user.has_password ? <ChangePasswordCard /> : <NoPasswordCard />}
      </div>
    </>
  )
}
