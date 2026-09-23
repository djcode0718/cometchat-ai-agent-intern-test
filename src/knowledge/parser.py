"""Markdown and YAML frontmatter parser for knowledge-base documents."""

import re
from pathlib import Path
from typing import List, Tuple, Union

import yaml
from pydantic import ValidationError

from src.core.models import DocumentMetadata, KnowledgeDocument, Section
from src.knowledge.exceptions import (
    DocumentNotFoundError,
    FrontmatterParsingError,
    MissingMetadataError,
)

FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


def extract_frontmatter_and_body(
    content: str, filename: str = ""
) -> Tuple[dict, str, int]:
    """Extract raw YAML frontmatter dictionary, body text, and body starting line number."""
    stripped_content = content.lstrip()
    if not stripped_content.startswith("---"):
        raise FrontmatterParsingError(
            f"Document {filename or 'content'} missing opening frontmatter delimiter '---'."
        )

    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        raise FrontmatterParsingError(
            f"Document {filename or 'content'} has malformed or unclosed YAML frontmatter."
        )

    yaml_text = match.group(1)
    body = content[match.end():]
    # Count how many lines were consumed by the frontmatter
    frontmatter_lines = content[: match.end()].count("\n")

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise FrontmatterParsingError(
            f"YAML syntax error in {filename or 'frontmatter'}: {e}"
        ) from e

    if not isinstance(data, dict):
        raise FrontmatterParsingError(
            f"Frontmatter in {filename or 'content'} must be a YAML mapping/dictionary."
        )

    return data, body, frontmatter_lines + 1


def extract_sections(body: str, base_line_offset: int = 1) -> List[Section]:
    """Parse markdown body into structured Section objects based on headings (#, ##, etc.)."""
    lines = body.split("\n")
    sections: List[Section] = []

    current_heading = ""
    current_level = 1
    current_content_lines: List[str] = []
    current_start_line = base_line_offset

    for idx, line in enumerate(lines):
        line_num = base_line_offset + idx
        match = HEADING_PATTERN.match(line.strip())

        if match:
            # If we were accumulating a previous section, finish it
            if current_heading or any(c.strip() for c in current_content_lines):
                content_str = "\n".join(current_content_lines).strip()
                if current_heading or content_str:
                    sections.append(
                        Section(
                            heading=current_heading or "Overview",
                            level=current_level,
                            content=content_str,
                            start_line=current_start_line,
                            end_line=line_num - 1,
                        )
                    )

            # Start new section
            hashes, heading_text = match.groups()
            current_level = len(hashes)
            current_heading = heading_text.strip()
            current_content_lines = []
            current_start_line = line_num
        else:
            current_content_lines.append(line)

    # Append the final section
    if current_heading or any(c.strip() for c in current_content_lines):
        content_str = "\n".join(current_content_lines).strip()
        if current_heading or content_str:
            sections.append(
                Section(
                    heading=current_heading or "Overview",
                    level=current_level,
                    content=content_str,
                    start_line=current_start_line,
                    end_line=base_line_offset + len(lines) - 1,
                )
            )

    return sections


class MarkdownDocumentParser:
    """Parses markdown files with YAML frontmatter into structured KnowledgeDocument models."""

    @staticmethod
    def parse_string(content: str, filename: str = "memory.md", file_path: Union[Path, str] = "memory.md") -> KnowledgeDocument:
        """Parse raw markdown string into KnowledgeDocument."""
        raw_metadata, body, body_start_line = extract_frontmatter_and_body(
            content, filename=filename
        )

        try:
            metadata = DocumentMetadata(**raw_metadata)
        except ValidationError as e:
            raise MissingMetadataError(
                f"Metadata validation error in {filename}: {e}"
            ) from e

        sections = extract_sections(body, base_line_offset=body_start_line)

        return KnowledgeDocument(
            file_path=Path(file_path).resolve() if not isinstance(file_path, Path) else file_path,
            filename=filename,
            metadata=metadata,
            raw_content=content,
            body=body,
            sections=sections,
        )

    @classmethod
    def parse_file(cls, file_path: Union[str, Path]) -> KnowledgeDocument:
        """Read and parse a Markdown document file from disk."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise DocumentNotFoundError(f"Knowledge file not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            raise FrontmatterParsingError(f"Failed to read file {path}: {e}") from e

        return cls.parse_string(content, filename=path.name, file_path=path)
