"""Persona loader and system prompt generator."""

from dataclasses import dataclass, field
from pathlib import Path
import re


class PersonaError(Exception):
    """Base exception for persona loading and parsing errors."""


class PersonaFileNotFoundError(PersonaError):
    """Raised when a required persona file is missing."""


@dataclass
class FactSection:
    """A tagged section parsed from facts.md."""

    title: str
    content: str
    tags: set[str] = field(default_factory=set)


@dataclass
class PersonaData:
    """Raw content loaded from the persona/ directory."""

    style_guide: str
    examples: str
    facts: str
    rules: str


class PersonaLoader:
    """Loads persona markdown files and constructs the runtime system prompt."""

    REQUIRED_FILES = ("style_guide.md", "examples.md", "facts.md", "rules.md")

    def __init__(self, persona_dir: Path | str) -> None:
        self.persona_dir = Path(persona_dir)
        self._data: PersonaData | None = None
        self._facts_sections: list[FactSection] | None = None

    def load(self, force_reload: bool = False) -> PersonaData:
        """Read and cache persona files from the persona directory."""
        if self._data is not None and not force_reload:
            return self._data

        if not self.persona_dir.exists() or not self.persona_dir.is_dir():
            raise PersonaFileNotFoundError(
                f"Persona directory '{self.persona_dir}' does not exist or is not a directory."
            )

        contents: dict[str, str] = {}
        for filename in self.REQUIRED_FILES:
            file_path = self.persona_dir / filename
            if not file_path.exists():
                raise PersonaFileNotFoundError(
                    f"Required persona file '{filename}' was not found in '{self.persona_dir}'."
                )
            contents[filename.replace(".md", "")] = file_path.read_text(encoding="utf-8")

        self._data = PersonaData(
            style_guide=contents["style_guide"],
            examples=contents["examples"],
            facts=contents["facts"],
            rules=contents["rules"],
        )
        self._facts_sections = None
        return self._data

    def get_fact_sections(self) -> list[FactSection]:
        """Parse facts.md into tagged sections based on markdown headings."""
        if self._facts_sections is not None:
            return self._facts_sections

        data = self.load()
        sections: list[FactSection] = []

        # Split facts.md by markdown headings (e.g. ## Title)
        raw_sections = re.split(r"\n(?=#{1,3}\s+)", data.facts)
        for raw in raw_sections:
            raw = raw.strip()
            if not raw:
                continue
            lines = raw.splitlines()
            header_line = lines[0].strip()
            title = re.sub(r"^#{1,3}\s+", "", header_line).strip()
            body = "\n".join(lines[1:]).strip()

            # Skip the main title of facts.md if it doesn't contain body
            if title.lower() == "facts" and not body:
                continue

            # Extract basic search tags from title and words
            words = set(re.findall(r"\b[a-z0-9_-]{2,}\b", (title + " " + body).lower()))
            sections.append(FactSection(title=title, content=body, tags=words))

        self._facts_sections = sections
        return sections

    def build_system_prompt(
        self,
        persona_name: str,
        retrieved_facts: list[str] | None = None,
    ) -> str:
        """Construct the runtime system prompt combining identity, rules, style, examples, and facts."""
        data = self.load()

        facts_block = ""
        if retrieved_facts:
            joined_facts = "\n\n".join(retrieved_facts)
            facts_block = (
                f"\n\n### Relevant Facts about {persona_name}:\n{joined_facts}"
            )
        else:
            facts_block = (
                f"\n\n### Facts about {persona_name}:\n"
                f"(No specific matching facts retrieved for this query. If the user asks a factual "
                f"or personal question about {persona_name} that you do not know with certainty, "
                f"do NOT guess. State clearly that you are not sure and suggest asking the real {persona_name}.)"
            )

        prompt = (
            f"You are the AI alter ego of {persona_name}. You chat and write in {persona_name}'s authentic style.\n\n"
            f"## CORE RULES & BOUNDARIES\n"
            f"{data.rules.strip()}\n\n"
            f"## STYLE GUIDE\n"
            f"{data.style_guide.strip()}\n\n"
            f"## EXAMPLES OF AUTHENTIC REPLIES\n"
            f"{data.examples.strip()}\n\n"
            f"## GROUNDING FACTS\n"
            f"{facts_block.strip()}\n\n"
            f"REMINDER: You are an AI alter ego of {persona_name}. Always identify yourself as such. "
            f"Never make commitments on {persona_name}'s behalf, never share private credentials/data, "
            f"and if unsure about a fact, say you are not sure and suggest reaching out to the real {persona_name}."
        )
        return prompt

