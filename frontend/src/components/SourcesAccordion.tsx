import { useState } from "react";
import { BookOpen, ChevronDown, ChevronRight, FileText } from "lucide-react";
import type { SourceCitation } from "../types/rag";

interface SourcesAccordionProps {
  sources: SourceCitation[];
}

function extractDocumentName(docPath: string): string {
  const parts = docPath.split(/[\\/]/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : docPath;
}

function formatRelevance(score: number | null): string | null {
  if (score === null || score === undefined || Number.isNaN(score)) return null;
  return `${(score * 100).toFixed(0)}% (score ${score.toFixed(2)})`;
}

export function SourcesAccordion({ sources }: SourcesAccordionProps) {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <section className="sources-section" aria-label="Fonti documentali utilizzate">
      <button
        type="button"
        className="sources-toggle"
        aria-expanded={expanded}
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span className="sources-toggle-left">
          <BookOpen size={15} aria-hidden="true" />
          <span>Fonti utilizzate ({sources.length})</span>
        </span>
        {expanded ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
      </button>

      {expanded && (
        <ul className="sources-list">
          {sources.map((src, index) => {
            const docName = extractDocumentName(src.document);
            const relevanceText = formatRelevance(src.relevance_score);

            return (
              <li key={`${src.document}-${src.section}-${index}`} className="source-card">
                <div className="source-card-header">
                  <span className="source-doc-name">
                    <FileText size={14} aria-hidden="true" />
                    <strong>{docName}</strong>
                  </span>
                  {relevanceText && (
                    <span className="source-score-badge" title="Punteggio di rilevanza retrieval">
                      Rilevanza: {relevanceText}
                    </span>
                  )}
                </div>

                <div className="source-meta-grid">
                  {src.section && (
                    <div className="source-meta-row">
                      <span className="source-meta-label">Sezione:</span>
                      <span>{src.section}</span>
                    </div>
                  )}
                  {src.page !== null && src.page !== undefined && (
                    <div className="source-meta-row">
                      <span className="source-meta-label">Pagina:</span>
                      <span>{src.page}</span>
                    </div>
                  )}
                  {src.area && (
                    <div className="source-meta-row">
                      <span className="source-meta-label">Area:</span>
                      <span>{src.area}</span>
                    </div>
                  )}
                  <div className="source-meta-row">
                    <span className="source-meta-label">Riferimento:</span>
                    <span className="source-path">{src.document}</span>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
