/*
 * Markdown from the AI (team summaries), rendered with daisyUI/Tailwind classes. Only
 * text formatting is allowed: no raw HTML (react-markdown never renders it), links,
 * images or tables; anything else is unwrapped to its text.
 */
import ReactMarkdown, { type Components } from 'react-markdown'

const ALLOWED = [
  'p',
  'h1',
  'h2',
  'h3',
  'h4',
  'ul',
  'ol',
  'li',
  'strong',
  'em',
  'br',
  'code',
  'blockquote',
  'hr',
]

const COMPONENTS: Components = {
  // Rendered inside a card (h3 title), so headings start at h4.
  h1: ({ children }) => (
    <h4 className="mt-4 mb-1 text-base font-semibold first:mt-0">{children}</h4>
  ),
  h2: ({ children }) => (
    <h4 className="mt-4 mb-1 text-base font-semibold first:mt-0">{children}</h4>
  ),
  h3: ({ children }) => <h5 className="mt-3 mb-1 font-semibold first:mt-0">{children}</h5>,
  h4: ({ children }) => <h5 className="mt-3 mb-1 font-semibold first:mt-0">{children}</h5>,
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  code: ({ children }) => (
    <code className="rounded bg-base-200 px-1 font-mono text-sm">{children}</code>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-4 border-base-300 pl-3">{children}</blockquote>
  ),
  hr: () => <hr className="my-3 border-base-300" />,
}

export default function Markdown({ children }: { children: string }) {
  return (
    <div className="leading-relaxed break-words">
      <ReactMarkdown allowedElements={ALLOWED} unwrapDisallowed components={COMPONENTS}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
