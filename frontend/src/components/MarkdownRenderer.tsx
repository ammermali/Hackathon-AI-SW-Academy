import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownRendererProps {
  content: string;
}

/**
 * Prevent CommonMark from merging outer numbered source headers (`1. **Title** (Sezione: *...*)`)
 * with inner `1. 2. 3.` procedural lists stored in earlier QueryHistory records.
 */
function normalizeLegacySourceHeaders(markdown: string): string {
  return markdown.replace(
    /^(\d+)\.\s+\*\*([^*]+)\*\*\s+\(Sezione:\s+\*([^*]*)\*\)\s*$/gm,
    (_match, num: string, title: string, section: string) => {
      const cleanTitle = title.trim();
      const cleanSection = section.trim();
      const heading = `### ${num}. ${cleanTitle}`;
      if (cleanSection && cleanSection.toLowerCase() !== cleanTitle.toLowerCase()) {
        return `${heading}\n\n*Sezione: ${cleanSection}*\n`;
      }
      return `${heading}\n`;
    }
  );
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const normalizedContent = normalizeLegacySourceHeaders(content);

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="markdown-table-wrap">
              <table>{children}</table>
            </div>
          ),
          code: ({ className, children, ...props }) => {
            const isBlock = Boolean(className) || String(children).includes("\n");
            if (isBlock) {
              return (
                <code className={`code-block ${className ?? ""}`} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className="code-inline" {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
