/** Swatch for an admin-chosen dropdown color; a dashed outline when there is none. */
export default function ColorDot({ color }: { color: string | null }) {
  if (!color) {
    return (
      <span
        className="inline-block size-3.5 shrink-0 rounded-full border border-dashed border-base-content/40"
        aria-hidden="true"
      />
    )
  }
  return (
    <span
      className="inline-block size-3.5 shrink-0 rounded-full border border-base-content/20"
      // The color is data chosen by the admin, not a theme color.
      style={{ backgroundColor: color }}
      aria-hidden="true"
    />
  )
}
