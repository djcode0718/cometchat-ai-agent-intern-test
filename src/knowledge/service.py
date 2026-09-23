"""Knowledge base ingestion service for loading, parsing, and chunking documents."""

from pathlib import Path
from typing import List, Optional, Tuple, Union

from src.core.config import Settings, get_settings
from src.core.models import KnowledgeChunk, KnowledgeDocument
from src.knowledge.chunker import SectionAwareChunker
from src.knowledge.exceptions import DocumentNotFoundError
from src.knowledge.parser import MarkdownDocumentParser


class IngestionResult:
    """Container holding ingestion output."""

    def __init__(
        self,
        documents: List[KnowledgeDocument],
        chunks: List[KnowledgeChunk],
    ) -> None:
        self.documents = documents
        self.chunks = chunks

    @property
    def document_count(self) -> int:
        return len(self.documents)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def get_document_by_id(self, document_id: str) -> Optional[KnowledgeDocument]:
        for doc in self.documents:
            if doc.metadata.document_id == document_id:
                return doc
        return None

    def get_chunks_for_document(self, document_id: str) -> List[KnowledgeChunk]:
        return [c for c in self.chunks if c.document_id == document_id]


class KnowledgeIngestionService:
    """Service for discovering, parsing, and chunking all knowledge-base documents."""

    def __init__(
        self,
        kb_path: Optional[Union[str, Path]] = None,
        chunker: Optional[SectionAwareChunker] = None,
    ) -> None:
        if kb_path is not None:
            self.kb_path = Path(kb_path).resolve()
        else:
            settings: Settings = get_settings()
            self.kb_path = settings.knowledge_base_path
        self.chunker = chunker or SectionAwareChunker()
        self.parser = MarkdownDocumentParser()

    def discover_files(self) -> List[Path]:
        """Discover all .md markdown files in the knowledge base directory, sorted deterministically."""
        if not self.kb_path.exists() or not self.kb_path.is_dir():
            raise DocumentNotFoundError(
                f"Knowledge base directory does not exist: {self.kb_path}"
            )

        md_files = sorted(list(self.kb_path.glob("*.md")), key=lambda p: p.name)
        return md_files

    def ingest(self) -> IngestionResult:
        """Parse and chunk all markdown files in the knowledge-base directory."""
        files = self.discover_files()
        documents: List[KnowledgeDocument] = []
        all_chunks: List[KnowledgeChunk] = []

        for file_path in files:
            doc = self.parser.parse_file(file_path)
            documents.append(doc)
            chunks = self.chunker.chunk_document(doc)
            all_chunks.extend(chunks)

        return IngestionResult(documents=documents, chunks=all_chunks)


def ingest_knowledge_base(
    kb_path: Optional[Union[str, Path]] = None,
) -> IngestionResult:
    """Convenience functional interface for ingesting knowledge base."""
    service = KnowledgeIngestionService(kb_path=kb_path)
    return service.ingest()
