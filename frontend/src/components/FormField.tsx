/*
 * Labelled form controls (daisyUI 5 fieldset classes). They spread their props onto
 * the native element, so React Hook Form's `register()` works directly:
 *
 *   <InputField label="Username" error={errors.username?.message} {...register('username')} />
 *
 * Error text is base-content next to an error-colored icon: status colors are too
 * light to use as text on base surfaces in the light theme.
 */
import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type Ref,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'

import { AlertIcon } from './icons'

interface FieldWrapperProps {
  id: string
  label: string
  error?: string
  hint?: ReactNode
  children: ReactNode
  className?: string
}

export function FieldWrapper({ id, label, error, hint, children, className }: FieldWrapperProps) {
  return (
    <div className={`fieldset ${className ?? ''}`}>
      <label htmlFor={id} className="fieldset-legend pb-0 text-sm">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="flex items-center gap-1.5 text-sm text-base-content">
          <span className="inline-flex rounded-full bg-error p-0.5 text-error-content">
            <AlertIcon className="size-3.5" />
          </span>
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className="label whitespace-normal text-base-content/80">
            {hint}
          </p>
        )
      )}
    </div>
  )
}

function describedBy(id: string, error?: string, hint?: ReactNode): string | undefined {
  if (error) return `${id}-error`
  if (hint) return `${id}-hint`
  return undefined
}

interface CommonProps {
  label: string
  error?: string
  hint?: ReactNode
  /** Classes for the wrapping fieldset. */
  wrapperClassName?: string
}

type InputFieldProps = CommonProps &
  InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> }

export function InputField({
  label,
  error,
  hint,
  wrapperClassName,
  id,
  className,
  ...props
}: InputFieldProps) {
  const autoId = useId()
  const fieldId = id ?? autoId
  return (
    <FieldWrapper id={fieldId} label={label} error={error} hint={hint} className={wrapperClassName}>
      <input
        id={fieldId}
        className={`input w-full ${error ? 'input-error' : ''} ${className ?? ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fieldId, error, hint)}
        {...props}
      />
    </FieldWrapper>
  )
}

type SelectFieldProps = CommonProps &
  SelectHTMLAttributes<HTMLSelectElement> & { ref?: Ref<HTMLSelectElement> }

export function SelectField({
  label,
  error,
  hint,
  wrapperClassName,
  id,
  className,
  children,
  ...props
}: SelectFieldProps) {
  const autoId = useId()
  const fieldId = id ?? autoId
  return (
    <FieldWrapper id={fieldId} label={label} error={error} hint={hint} className={wrapperClassName}>
      <select
        id={fieldId}
        className={`select w-full ${error ? 'select-error' : ''} ${className ?? ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fieldId, error, hint)}
        {...props}
      >
        {children}
      </select>
    </FieldWrapper>
  )
}

type TextareaFieldProps = CommonProps &
  TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: Ref<HTMLTextAreaElement> }

export function TextareaField({
  label,
  error,
  hint,
  wrapperClassName,
  id,
  className,
  ...props
}: TextareaFieldProps) {
  const autoId = useId()
  const fieldId = id ?? autoId
  return (
    <FieldWrapper id={fieldId} label={label} error={error} hint={hint} className={wrapperClassName}>
      <textarea
        id={fieldId}
        className={`textarea w-full ${error ? 'textarea-error' : ''} ${className ?? ''}`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(fieldId, error, hint)}
        {...props}
      />
    </FieldWrapper>
  )
}

/** Submit button with a spinner while pending. */
export function SubmitButton({
  isPending,
  children,
  className,
}: {
  isPending: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <button type="submit" className={`btn btn-primary ${className ?? ''}`} disabled={isPending}>
      {isPending && <span className="loading loading-spinner loading-sm" />}
      {children}
    </button>
  )
}
