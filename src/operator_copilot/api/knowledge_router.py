"""Knowledge Base management endpoints restricted to Knowledge Manager / Admin roles."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from operator_copilot.api.dependencies import build_knowledge_manager_context_dependency
from operator_copilot.config.settings import Settings
from operator_copilot.db.models import DocumentMetadata
from operator_copilot.ingestion.scanner import SUPPORTED_EXTENSIONS, DataScanner
from operator_copilot.retrieval.rag_engine import RAGEngine
from operator_copilot.schemas.response import IngestResponse

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_PREVIEW_CHARS = 120_000


class KnowledgeDocumentItem(BaseModel):
    document_id: str
    filename: str
    relative_path: str
    area: str
    extension: str
    size_bytes: int
    status: str
    chunk_count: int
    updated_at: str
    indexed_at: str | None = None


class KnowledgeDocumentsPageResponse(BaseModel):
    total: int
    page: int
    page_size: int
    indexed_total: int
    total_chunks: int
    areas: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    supported_extensions: list[str] = Field(default_factory=list)
    items: list[KnowledgeDocumentItem] = Field(default_factory=list)


class KnowledgeDocumentContentResponse(BaseModel):
    document_id: str
    filename: str
    relative_path: str
    area: str
    extension: str
    size_bytes: int
    content: str
    truncated: bool = False


class KnowledgeUploadFileOutcome(BaseModel):
    filename: str
    relative_path: str = ""
    status: str  # uploaded | overwritten | skipped_exists | rejected
    detail: str = ""
    size_bytes: int = 0


class KnowledgeUploadResponse(BaseModel):
    uploaded_count: int
    skipped_count: int
    rejected_count: int
    results: list[KnowledgeUploadFileOutcome] = Field(default_factory=list)
    ingest: IngestResponse | None = None


def _derive_area(relative_path: str) -> str:
    parts = relative_path.split("/")
    return parts[0] if len(parts) > 1 else "Generale"


def _sanitize_area_folder(raw_area: str) -> Path:
    cleaned = (raw_area or "").strip().replace("\\", "/")
    if not cleaned or cleaned.lower() in {"generale", "root", "/"}:
        return Path()
    segments: list[str] = []
    for seg in cleaned.split("/"):
        s = re.sub(r'[<>:"|?*\x00-\x1f]', "", seg).strip(" .")
        if not s or s in {".", ".."}:
            continue
        segments.append(s)
    return Path(*segments) if segments else Path()


def _sanitize_filename(raw_name: str | None) -> str:
    base = Path((raw_name or "").replace("\\", "/")).name
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")
    return cleaned


def create_knowledge_router(
    *,
    get_rag_engine: Callable[[], RAGEngine],
    settings: Settings,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Base"])
    require_km = build_knowledge_manager_context_dependency(settings)

    @router.get(
        "/documents",
        response_model=KnowledgeDocumentsPageResponse,
        summary="Lista completa dei file presenti nella Knowledge Base con stato di indicizzazione",
    )
    def list_knowledge_documents(
        search: str | None = Query(default=None),
        area: str | None = Query(default=None),
        extension: str | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=25, ge=1, le=100),
        _ctx: dict[str, str] = Depends(require_km),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> KnowledgeDocumentsPageResponse:
        scanner = DataScanner(
            rag.settings.data_dir,
            skip_index_files=rag.settings.skip_index_files,
        )
        scanned = scanner.scan()

        with rag.db.session() as db:
            meta_rows = db.query(DocumentMetadata).all()
        meta_by_path = {row.source: row for row in meta_rows}
        meta_by_id = {row.document_id: row for row in meta_rows}

        all_items: list[KnowledgeDocumentItem] = []
        areas_set: set[str] = set()
        ext_set: set[str] = set()
        indexed_total = 0
        total_chunks = 0

        for sf in scanned:
            meta = meta_by_path.get(sf.relative_path) or meta_by_id.get(sf.document_id)
            item_area = _derive_area(sf.relative_path)
            areas_set.add(item_area)
            ext_set.add(sf.extension)
            doc_status = meta.status if meta is not None else "pending"
            chunks = int(meta.chunk_count) if meta is not None else 0
            if doc_status == "indexed":
                indexed_total += 1
            total_chunks += chunks

            all_items.append(
                KnowledgeDocumentItem(
                    document_id=sf.document_id,
                    filename=sf.absolute_path.name,
                    relative_path=sf.relative_path,
                    area=item_area,
                    extension=sf.extension,
                    size_bytes=sf.size_bytes,
                    status=doc_status,
                    chunk_count=chunks,
                    updated_at=sf.updated_at,
                    indexed_at=meta.indexed_at.isoformat() if meta and meta.indexed_at else None,
                )
            )

        filtered = all_items
        if search and search.strip():
            needle = search.strip().lower()
            filtered = [
                it
                for it in filtered
                if needle in it.filename.lower()
                or needle in it.relative_path.lower()
                or needle in it.area.lower()
            ]
        if area and area.strip():
            target_area = area.strip().lower()
            filtered = [it for it in filtered if it.area.lower() == target_area]
        if extension and extension.strip():
            target_ext = extension.strip().lower()
            if not target_ext.startswith("."):
                target_ext = f".{target_ext}"
            filtered = [it for it in filtered if it.extension.lower() == target_ext]

        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size

        return KnowledgeDocumentsPageResponse(
            total=total,
            page=page,
            page_size=page_size,
            indexed_total=indexed_total,
            total_chunks=total_chunks,
            areas=sorted(areas_set),
            extensions=sorted(ext_set),
            supported_extensions=sorted(SUPPORTED_EXTENSIONS),
            items=filtered[start:end],
        )

    @router.get(
        "/documents/{document_id}/content",
        response_model=KnowledgeDocumentContentResponse,
        summary="Anteprima del contenuto di un documento della Knowledge Base",
    )
    def get_knowledge_document_content(
        document_id: str,
        _ctx: dict[str, str] = Depends(require_km),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> KnowledgeDocumentContentResponse:
        scanner = DataScanner(
            rag.settings.data_dir,
            skip_index_files=rag.settings.skip_index_files,
        )
        match = next((sf for sf in scanner.scan() if sf.document_id == document_id), None)
        if match is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento non trovato.")

        root_resolved = rag.settings.data_dir.resolve()
        file_resolved = match.absolute_path.resolve()
        if not file_resolved.is_relative_to(root_resolved):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Percorso non autorizzato.")

        raw = file_resolved.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        truncated = len(text) > _MAX_PREVIEW_CHARS
        if truncated:
            text = text[:_MAX_PREVIEW_CHARS]

        return KnowledgeDocumentContentResponse(
            document_id=match.document_id,
            filename=match.absolute_path.name,
            relative_path=match.relative_path,
            area=_derive_area(match.relative_path),
            extension=match.extension,
            size_bytes=match.size_bytes,
            content=text,
            truncated=truncated,
        )

    @router.post(
        "/upload",
        response_model=KnowledgeUploadResponse,
        summary="Carica uno o più file nella Knowledge Base e avvia l'ingestion incrementale",
    )
    async def upload_knowledge_documents(
        files: list[UploadFile] = File(...),
        area: str = Form(default=""),
        overwrite: bool = Form(default=False),
        _ctx: dict[str, str] = Depends(require_km),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> KnowledgeUploadResponse:
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Seleziona almeno un file da caricare.",
            )

        rag.settings.data_dir.mkdir(parents=True, exist_ok=True)
        root_resolved = rag.settings.data_dir.resolve()
        area_subpath = _sanitize_area_folder(area)
        target_dir = (rag.settings.data_dir / area_subpath).resolve()
        if not target_dir.is_relative_to(root_resolved):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cartella di destinazione non valida.")

        outcomes: list[KnowledgeUploadFileOutcome] = []
        uploaded_count = 0
        skipped_count = 0
        rejected_count = 0

        for upload in files:
            safe_name = _sanitize_filename(upload.filename)
            if not safe_name:
                rejected_count += 1
                outcomes.append(
                    KnowledgeUploadFileOutcome(
                        filename=upload.filename or "file",
                        status="rejected",
                        detail="Nome file non valido.",
                    )
                )
                continue

            ext = Path(safe_name).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                rejected_count += 1
                outcomes.append(
                    KnowledgeUploadFileOutcome(
                        filename=safe_name,
                        status="rejected",
                        detail=f"Estensione '{ext or 'nessuna'}' non supportata. Ammesse: {', '.join(sorted(SUPPORTED_EXTENSIONS))}.",
                    )
                )
                continue

            raw_bytes = await upload.read()
            if len(raw_bytes) == 0:
                rejected_count += 1
                outcomes.append(
                    KnowledgeUploadFileOutcome(
                        filename=safe_name,
                        status="rejected",
                        detail="File vuoto.",
                    )
                )
                continue
            if len(raw_bytes) > _MAX_UPLOAD_BYTES:
                rejected_count += 1
                outcomes.append(
                    KnowledgeUploadFileOutcome(
                        filename=safe_name,
                        status="rejected",
                        detail="Dimensione superiore al limite di 10 MB.",
                        size_bytes=len(raw_bytes),
                    )
                )
                continue

            try:
                raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                rejected_count += 1
                outcomes.append(
                    KnowledgeUploadFileOutcome(
                        filename=safe_name,
                        status="rejected",
                        detail="Il file deve essere testo valido codificato UTF-8.",
                        size_bytes=len(raw_bytes),
                    )
                )
                continue

            target_dir.mkdir(parents=True, exist_ok=True)
            dest = (target_dir / safe_name).resolve()
            if not dest.is_relative_to(root_resolved):
                rejected_count += 1
                outcomes.append(
                    KnowledgeUploadFileOutcome(
                        filename=safe_name,
                        status="rejected",
                        detail="Percorso di destinazione non consentito.",
                    )
                )
                continue

            rel_posix = dest.relative_to(root_resolved).as_posix()
            existed = dest.exists()
            if existed and not overwrite:
                skipped_count += 1
                outcomes.append(
                    KnowledgeUploadFileOutcome(
                        filename=safe_name,
                        relative_path=rel_posix,
                        status="skipped_exists",
                        detail="File già presente (attiva 'Sovrascrivi' per aggiornarlo).",
                        size_bytes=len(raw_bytes),
                    )
                )
                continue

            dest.write_bytes(raw_bytes)
            uploaded_count += 1
            outcomes.append(
                KnowledgeUploadFileOutcome(
                    filename=safe_name,
                    relative_path=rel_posix,
                    status="overwritten" if existed else "uploaded",
                    detail="File salvato e pronto per l'indicizzazione.",
                    size_bytes=len(raw_bytes),
                )
            )

        ingest_res: IngestResponse | None = None
        if uploaded_count > 0:
            ingest_res = rag.indexer.run_ingestion(rebuild=False)

        return KnowledgeUploadResponse(
            uploaded_count=uploaded_count,
            skipped_count=skipped_count,
            rejected_count=rejected_count,
            results=outcomes,
            ingest=ingest_res,
        )

    @router.post(
        "/ingest",
        response_model=IngestResponse,
        summary="Avvia sincronizzazione incrementale della Knowledge Base",
    )
    def sync_knowledge_base(
        _ctx: dict[str, str] = Depends(require_km),
        rag: RAGEngine = Depends(get_rag_engine),
    ) -> IngestResponse:
        return rag.indexer.run_ingestion(rebuild=False)

    return router
