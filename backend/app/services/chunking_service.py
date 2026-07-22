import logging
from typing import List, Optional
from pydantic import BaseModel
from backend.app.config.settings import settings
from backend.app.services.pdf_parser import ParsedPage

logger = logging.getLogger("omnibrain.chunking")

# Separator hierarchy used to recursively split text at the most
# "natural" boundary first, falling back to smaller boundaries.
DEFAULT_SEPARATORS: List[str] = ["\n\n", "\n", ". ", " ", ""]


class TextChunk(BaseModel):
    """A single chunk of text produced by the chunking pipeline."""

    chunk_index: int
    page_number: int
    content: str
    char_count: int


class RecursiveChunkingService:
    """Splits document text into overlapping chunks using a recursive
    character-based strategy, similar in spirit to LangChain's
    RecursiveCharacterTextSplitter, without taking on that dependency.

    The splitter tries a hierarchy of separators (paragraph, line,
    sentence, word, character) so that chunk boundaries fall on the
    most natural break point available, then merges the resulting
    pieces into chunks that respect the configured size and overlap.
    """

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        separators: Optional[List[str]] = None,
    ):
        self.chunk_size = chunk_size or settings.DEFAULT_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.DEFAULT_CHUNK_OVERLAP

        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

        self.separators = separators or DEFAULT_SEPARATORS

    def chunk_document(self, pages: List[ParsedPage]) -> List[TextChunk]:
        """Chunks every page of a parsed document, preserving page numbers
        and assigning a document-wide sequential chunk index.
        """
        chunks: List[TextChunk] = []
        chunk_index = 0

        for page in pages:
            page_text = (page.text or "").strip()
            if not page_text:
                continue

            for piece in self._split_text(page_text, self.chunk_size):
                cleaned = piece.strip()
                if not cleaned:
                    continue
                chunks.append(
                    TextChunk(
                        chunk_index=chunk_index,
                        page_number=page.page_number,
                        content=cleaned,
                        char_count=len(cleaned),
                    )
                )
                chunk_index += 1

        logger.info(f"Generated {len(chunks)} chunk(s) across {len(pages)} page(s).")
        return chunks

    def _split_text(self, text: str, chunk_size: int) -> List[str]:
        """Recursively splits `text` into atomic pieces no larger than
        `chunk_size`, then merges those pieces into overlapping chunks.
        """
        atomic_pieces = self._recursive_split(text, self.separators)
        return self._merge_pieces(atomic_pieces, chunk_size, self.chunk_overlap)

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        """Breaks `text` down using the first usable separator; recurses
        into any resulting piece that is still larger than chunk_size,
        with the remaining (narrower) separators.
        """
        if len(text) <= self.chunk_size:
            return [text] if text else []

        if not separators:
            # Base case: no separators left, hard-slice by character count.
            return [
                text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)
            ]

        separator, remaining_separators = separators[0], separators[1:]

        if separator == "":
            return [
                text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)
            ]

        parts = text.split(separator)
        pieces: List[str] = []
        for idx, part in enumerate(parts):
            # Re-attach the separator except on the very last part.
            fragment = part + separator if idx < len(parts) - 1 else part
            if not fragment:
                continue
            if len(fragment) > self.chunk_size:
                pieces.extend(self._recursive_split(fragment, remaining_separators))
            else:
                pieces.append(fragment)
        return pieces

    def _merge_pieces(self, pieces: List[str], chunk_size: int, overlap: int) -> List[str]:
        """Greedily merges small atomic pieces into chunks up to `chunk_size`,
        carrying `overlap` trailing characters from one chunk into the next.
        """
        if not pieces:
            return []

        chunks: List[str] = []
        current = ""

        for piece in pieces:
            if not current:
                current = piece
                continue

            if len(current) + len(piece) <= chunk_size:
                current += piece
            else:
                chunks.append(current)
                # Carry over trailing characters for continuity, but never let
                # the overlap push the new chunk past chunk_size -- atomic
                # pieces are already <= chunk_size, so the overlap budget
                # simply shrinks (down to zero) to make room for a large piece.
                tail_budget = max(0, chunk_size - len(piece))
                tail_len = min(overlap, tail_budget)
                tail = current[-tail_len:] if tail_len > 0 else ""
                current = tail + piece

        if current:
            chunks.append(current)

        return chunks
