import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import {
  CheckCircle2,
  Database,
  Eye,
  FileText,
  FolderUp,
  RefreshCw,
  Search,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import {
  ErrorBanner,
  LoadingState,
  StatusBadge,
} from "../../components/common/PlatformPrimitives";
import { useAuth } from "../../context/AuthContext";
import {
  getKnowledgeDocumentContent,
  listKnowledgeDocuments,
  syncKnowledgeBase,
  uploadKnowledgeDocuments,
} from "../../services/knowledgeApi";
import type {
  KnowledgeDocumentContent,
  KnowledgeDocumentsPage,
  KnowledgeUploadResponse,
} from "../../types/platform";
import { formatItalianDate } from "../../utils/courseHelpers";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function KnowledgeBasePage() {
  const { authContext, contextVersion } = useAuth();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [docsPage, setDocsPage] = useState<KnowledgeDocumentsPage | null>(null);
  const [search, setSearch] = useState("");
  const [areaFilter, setAreaFilter] = useState("");
  const [extFilter, setExtFilter] = useState("");
  const [page, setPage] = useState(1);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Drag-and-drop upload state
  const [isDragging, setIsDragging] = useState(false);
  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [targetArea, setTargetArea] = useState("");
  const [overwriteExisting, setOverwriteExisting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [uploadReport, setUploadReport] = useState<KnowledgeUploadResponse | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  // Preview panel
  const [previewDoc, setPreviewDoc] = useState<KnowledgeDocumentContent | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const loadDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await listKnowledgeDocuments(authContext, {
        search: search.trim() || undefined,
        area: areaFilter || undefined,
        extension: extFilter || undefined,
        page,
        page_size: 25,
      });
      setDocsPage(res);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Impossibile caricare i documenti della Knowledge Base."
      );
    } finally {
      setIsLoading(false);
    }
  }, [areaFilter, authContext, extFilter, page, search]);

  useEffect(() => {
    void loadDocuments();
  }, [contextVersion, loadDocuments]);

  const appendFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    if (list.length === 0) return;
    setQueuedFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const next = [...prev];
      for (const file of list) {
        const key = `${file.name}:${file.size}`;
        if (!seen.has(key)) {
          seen.add(key);
          next.push(file);
        }
      }
      return next;
    });
    setUploadReport(null);
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDragging) setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      appendFiles(e.dataTransfer.files);
    }
  };

  const handleUploadAndIngest = async () => {
    if (queuedFiles.length === 0 || isUploading) return;
    setIsUploading(true);
    setError(null);
    setSyncMessage(null);
    try {
      const res = await uploadKnowledgeDocuments(authContext, {
        files: queuedFiles,
        area: targetArea.trim() || undefined,
        overwrite: overwriteExisting,
      });
      setUploadReport(res);
      if (res.uploaded_count > 0) {
        setQueuedFiles([]);
        await loadDocuments();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore durante il caricamento dei file.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleManualSync = async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    setError(null);
    setSyncMessage(null);
    try {
      const res = await syncKnowledgeBase(authContext);
      setSyncMessage(
        `Sincronizzazione completata: ${res.files_indexed} indicizzati, ${res.chunks_created} nuovi chunk, ${res.files_skipped_unchanged} invariati (${res.processing_time_ms} ms).`
      );
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore durante la sincronizzazione.");
    } finally {
      setIsSyncing(false);
    }
  };

  const handleOpenPreview = async (documentId: string) => {
    setIsLoadingPreview(true);
    setError(null);
    try {
      const data = await getKnowledgeDocumentContent(authContext, documentId);
      setPreviewDoc(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossibile aprire l'anteprima del documento.");
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const totalPages = docsPage ? Math.max(1, Math.ceil(docsPage.total / docsPage.page_size)) : 1;

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1>Base di conoscenza e caricamento</h1>
          <p>
            Consulta tutti i documenti indicizzati per il RAG e carica nuovi manuali o FAQ con
            indicizzazione incrementale immediata.
          </p>
        </div>

        <button
          type="button"
          className="btn btn-secondary"
          disabled={isSyncing}
          onClick={() => void handleManualSync()}
        >
          <RefreshCw size={15} className={isSyncing ? "spin" : ""} aria-hidden="true" />
          <span>{isSyncing ? "Sincronizzazione..." : "Sincronizza KB"}</span>
        </button>
      </div>

      {docsPage && (
        <section className="kpi-grid" aria-label="Riepilogo Knowledge Base">
          <div className="kpi-card">
            <div className="kpi-label">File nella KB</div>
            <div className="kpi-value">{docsPage.total}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">File indicizzati</div>
            <div className="kpi-value">{docsPage.indexed_total}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Chunk totali</div>
            <div className="kpi-value">{docsPage.total_chunks}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Formati supportati</div>
            <div className="kpi-value" style={{ fontSize: "1.05rem" }}>
              {docsPage.supported_extensions.join("  ")}
            </div>
          </div>
        </section>
      )}

      {error && <ErrorBanner message={error} onRetry={() => void loadDocuments()} />}

      {syncMessage && (
        <div className="panel-card" role="status">
          <div className="user-title-inline">
            <CheckCircle2 size={18} className="text-success" aria-hidden="true" />
            <span>{syncMessage}</span>
          </div>
        </div>
      )}

      {/* Drag-and-drop Upload Section */}
      <section className="panel-card stack-md" aria-label="Caricamento documenti">
        <div className="panel-card-header">
          <div>
            <h2>
              <FolderUp size={18} style={{ verticalAlign: "text-bottom", marginRight: "0.4rem" }} />
              Carica nuovi documenti nella Knowledge Base
            </h2>
            <p className="muted-meta">
              Trascina uno o più file (.md, .txt, .json, .csv) per aggiungerli alla cartella dati e
              indicizzarli subito nel RAG.
            </p>
          </div>
        </div>

        <div
          className={`kb-dropzone ${isDragging ? "kb-dropzone-active" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".md,.txt,.json,.csv"
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files) {
                appendFiles(e.target.files);
                e.target.value = "";
              }
            }}
          />
          <UploadCloud size={32} aria-hidden="true" />
          <strong>Trascina qui i file oppure clicca per sfogliare</strong>
          <span className="muted-meta">Estensioni ammesse: .md, .txt, .json, .csv (max 10 MB ciascuno)</span>
        </div>

        <div className="filter-bar">
          <div style={{ flex: 1, minWidth: "220px" }}>
            <label htmlFor="kb-area-input" className="muted-meta" style={{ display: "block", marginBottom: "0.25rem" }}>
              Area / sottocartella di destinazione (opzionale)
            </label>
            <input
              id="kb-area-input"
              type="text"
              list="kb-areas-datalist"
              className="filter-input"
              style={{ width: "100%" }}
              value={targetArea}
              onChange={(e) => setTargetArea(e.target.value)}
              placeholder="Es. 01 - Informazioni Generali oppure lascia vuoto per root"
            />
            <datalist id="kb-areas-datalist">
              {(docsPage?.areas ?? []).map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>
          </div>

          <label className="user-title-inline" style={{ cursor: "pointer", paddingTop: "1rem" }}>
            <input
              type="checkbox"
              checked={overwriteExisting}
              onChange={(e) => setOverwriteExisting(e.target.checked)}
            />
            <span>Sovrascrivi se già presente</span>
          </label>
        </div>

        {queuedFiles.length > 0 && (
          <div className="stack-sm">
            <div className="panel-card-header">
              <strong>File selezionati ({queuedFiles.length})</strong>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={() => setQueuedFiles([])}
              >
                Svuota coda
              </button>
            </div>
            <ul className="topic-list">
              {queuedFiles.map((file, idx) => (
                <li key={`${file.name}-${idx}`} className="topic-list-item">
                  <div className="gap-row-top">
                    <span>
                      <FileText size={14} style={{ verticalAlign: "middle", marginRight: "0.35rem" }} />
                      <strong>{file.name}</strong>{" "}
                      <span className="muted-meta">({formatFileSize(file.size)})</span>
                    </span>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Rimuovi ${file.name}`}
                      onClick={() =>
                        setQueuedFiles((prev) => prev.filter((_, i) => i !== idx))
                      }
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>

            <div className="quiz-submit-row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={isUploading}
                onClick={() => void handleUploadAndIngest()}
              >
                <UploadCloud size={16} aria-hidden="true" />
                <span>
                  {isUploading
                    ? "Caricamento e indicizzazione..."
                    : `Carica e indicizza (${queuedFiles.length})`}
                </span>
              </button>
            </div>
          </div>
        )}

        {uploadReport && (
          <div className="stack-sm" role="status">
            <div className="user-title-inline">
              <StatusBadge tone={uploadReport.uploaded_count > 0 ? "success" : "warning"}>
                Caricati: {uploadReport.uploaded_count} • Saltati: {uploadReport.skipped_count} • Scartati:{" "}
                {uploadReport.rejected_count}
              </StatusBadge>
              {uploadReport.ingest && (
                <span className="muted-meta">
                  Ingestion: {uploadReport.ingest.files_indexed} indicizzati,{" "}
                  {uploadReport.ingest.chunks_created} chunk creati (
                  {uploadReport.ingest.processing_time_ms} ms)
                </span>
              )}
            </div>
            <ul className="topic-list">
              {uploadReport.results.map((r, idx) => (
                <li key={`${r.filename}-${idx}`} className="topic-list-item">
                  <div className="gap-row-top">
                    <strong>{r.relative_path || r.filename}</strong>
                    <StatusBadge
                      tone={
                        r.status === "uploaded" || r.status === "overwritten"
                          ? "success"
                          : r.status === "skipped_exists"
                            ? "warning"
                            : "danger"
                      }
                    >
                      {r.status}
                    </StatusBadge>
                  </div>
                  <span className="muted-meta">{r.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* Complete Knowledge Base File List */}
      <section className="panel-card stack-md" aria-label="Elenco file Knowledge Base">
        <div className="panel-card-header">
          <h2>
            <Database size={18} style={{ verticalAlign: "text-bottom", marginRight: "0.4rem" }} />
            Archivio completo Knowledge Base
          </h2>
        </div>

        <div className="filter-bar">
          <div className="filter-search">
            <Search size={16} aria-hidden="true" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setPage(1);
                setSearch(e.target.value);
              }}
              placeholder="Cerca file o percorso..."
            />
          </div>

          <select
            value={areaFilter}
            onChange={(e) => {
              setPage(1);
              setAreaFilter(e.target.value);
            }}
            aria-label="Filtra per area"
          >
            <option value="">Tutte le aree</option>
            {(docsPage?.areas ?? []).map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>

          <select
            value={extFilter}
            onChange={(e) => {
              setPage(1);
              setExtFilter(e.target.value);
            }}
            aria-label="Filtra per formato"
          >
            <option value="">Tutti i formati</option>
            {(docsPage?.extensions ?? []).map((ext) => (
              <option key={ext} value={ext}>
                {ext}
              </option>
            ))}
          </select>
        </div>

        {isLoading ? (
          <LoadingState label="Scansione Knowledge Base..." />
        ) : !docsPage || docsPage.items.length === 0 ? (
          <div className="empty-card">
            <p>Nessun documento trovato con i filtri selezionati.</p>
          </div>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Documento</th>
                    <th>Area</th>
                    <th>Formato</th>
                    <th>Dimensione</th>
                    <th>Chunk</th>
                    <th>Stato</th>
                    <th>Aggiornato</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {docsPage.items.map((doc) => (
                    <tr key={doc.document_id}>
                      <td>
                        <strong>{doc.filename}</strong>
                        <div className="muted-meta">{doc.relative_path}</div>
                      </td>
                      <td>{doc.area}</td>
                      <td>
                        <code>{doc.extension}</code>
                      </td>
                      <td>{formatFileSize(doc.size_bytes)}</td>
                      <td>{doc.chunk_count}</td>
                      <td>
                        <StatusBadge tone={doc.status === "indexed" ? "success" : "warning"}>
                          {doc.status}
                        </StatusBadge>
                      </td>
                      <td>{formatItalianDate(doc.updated_at, true)}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          onClick={() => void handleOpenPreview(doc.document_id)}
                        >
                          <Eye size={14} aria-hidden="true" /> Anteprima
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination-row">
                <button
                  type="button"
                  className="btn btn-sm btn-secondary"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Precedente
                </button>
                <span>
                  Pagina {page} di {totalPages} ({docsPage.total} documenti)
                </span>
                <button
                  type="button"
                  className="btn btn-sm btn-secondary"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Successiva
                </button>
              </div>
            )}
          </>
        )}
      </section>

      {(previewDoc || isLoadingPreview) && (
        <section className="panel-card stack-sm" aria-label="Anteprima documento">
          {isLoadingPreview ? (
            <LoadingState label="Caricamento contenuto..." />
          ) : (
            previewDoc && (
              <>
                <div className="panel-card-header">
                  <div>
                    <h3>{previewDoc.filename}</h3>
                    <p className="muted-meta">
                      {previewDoc.relative_path} • {formatFileSize(previewDoc.size_bytes)}
                      {previewDoc.truncated ? " • Anteprima troncata a 120.000 caratteri" : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="Chiudi anteprima"
                    onClick={() => setPreviewDoc(null)}
                  >
                    <X size={16} />
                  </button>
                </div>
                <pre className="kb-preview-box">{previewDoc.content}</pre>
              </>
            )
          )}
        </section>
      )}
    </div>
  );
}
