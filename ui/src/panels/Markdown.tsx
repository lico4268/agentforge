import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

/**
 * Inline Markdown renderer — dark-theme styled to match the Agentforge palette.
 * Used by Inspector (answer / output) and the workspace file viewer.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown-body text-[13px] leading-relaxed text-[#dde4dd]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="mb-2 mt-3 text-[16px] font-bold text-[#4edea3]">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2 mt-3 text-[15px] font-semibold text-[#4edea3]">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-1.5 mt-2 text-[14px] font-semibold text-[#bbcabf]">{children}</h3>
          ),
          p: ({ children }) => <p className="mb-2 leading-relaxed">{children}</p>,
          ul: ({ children }) => (
            <ul className="mb-2 ml-4 list-disc space-y-0.5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-2 ml-4 list-decimal space-y-0.5">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          code: ({ children, className }) => {
            const isBlock = className?.includes('language-')
            if (isBlock) {
              return (
                <code className="block">{children}</code>
              )
            }
            return (
              <code className="rounded bg-[#09100c] px-1 py-0.5 font-mono text-[12px] text-[#4edea3]">
                {children}
              </code>
            )
          },
          pre: ({ children }) => (
            <pre className="mb-2 overflow-x-auto rounded-md border border-[#3c4a42] bg-[#09100c] p-2">
              {children}
            </pre>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#4edea3] underline hover:text-[#86e6c0]"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="mb-2 border-l-2 border-[#3c4a42] pl-3 text-[#86948a]">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <table className="mb-2 w-full border-collapse text-[12px]">{children}</table>
          ),
          th: ({ children }) => (
            <th className="border border-[#3c4a42] bg-[#242c27] px-2 py-1 text-left font-semibold text-[#bbcabf]">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-[#3c4a42] px-2 py-1">{children}</td>
          ),
          hr: () => <hr className="my-3 border-[#3c4a42]/50" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}