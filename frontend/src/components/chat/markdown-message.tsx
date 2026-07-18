import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownMessageProps {
  content: string;
}

export function MarkdownMessage({ content }: MarkdownMessageProps) {
  return (
    <div className="min-w-0 text-sm leading-6 text-slate-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noreferrer noopener"
              className="text-cyan-300 underline decoration-cyan-300/40 underline-offset-2 hover:text-cyan-200"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-cyan-300/50 pl-4 text-slate-400">
              {children}
            </blockquote>
          ),
          code: ({ children, className, ...props }) => (
            <code
              {...props}
              className={`rounded bg-slate-950/70 px-1.5 py-0.5 font-mono text-[0.85em] text-cyan-100 ${className ?? ""}`}
            >
              {children}
            </code>
          ),
          h1: ({ children }) => <h1 className="mb-3 mt-5 text-xl font-semibold text-white first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-3 mt-5 text-lg font-semibold text-white first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 mt-4 text-base font-semibold text-white first:mt-0">{children}</h3>,
          hr: () => <hr className="my-5 border-white/10" />,
          li: ({ children }) => <li className="my-1 pl-1 marker:text-cyan-300">{children}</li>,
          ol: ({ children }) => <ol className="my-3 list-decimal space-y-1 pl-6">{children}</ol>,
          p: ({ children }) => <p className="my-3 whitespace-pre-wrap first:mt-0 last:mb-0">{children}</p>,
          pre: ({ children }) => (
            <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-slate-950 p-4 text-xs leading-5 [&_code]:bg-transparent [&_code]:p-0">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-xl border border-white/10">
              <table className="w-full min-w-max border-collapse text-left text-sm">{children}</table>
            </div>
          ),
          tbody: ({ children }) => <tbody className="divide-y divide-white/10">{children}</tbody>,
          td: ({ children }) => <td className="px-4 py-2.5 align-top text-slate-300">{children}</td>,
          th: ({ children }) => <th className="bg-white/5 px-4 py-2.5 font-medium text-slate-100">{children}</th>,
          thead: ({ children }) => <thead className="border-b border-white/10">{children}</thead>,
          ul: ({ children }) => <ul className="my-3 list-disc space-y-1 pl-6">{children}</ul>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
