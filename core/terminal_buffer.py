from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TerminalLine:
    text: str
    revealed: int = 0
    style: str = "normal"
    kind: str = "text"
    progress: float = 0.0
    progress_target: float = 0.0
    progress_label: str = ""

    @property
    def visible_text(self) -> str:
        return self.text[: self.revealed]

    @property
    def done(self) -> bool:
        return self.revealed >= len(self.text)


@dataclass
class TerminalBuffer:
    lines: list[TerminalLine] = field(default_factory=list)
    scroll_offset: float = 0.0

    def append_line(
        self,
        text: str,
        style: str = "normal",
        revealed: int = 0,
        kind: str = "text",
        progress: float = 0.0,
        progress_target: float = 0.0,
        progress_label: str = "",
    ) -> TerminalLine:
        line = TerminalLine(
            text=text,
            style=style,
            revealed=revealed,
            kind=kind,
            progress=progress,
            progress_target=progress_target,
            progress_label=progress_label,
        )
        self.lines.append(line)
        return line

    def clear(self) -> None:
        self.lines.clear()
        self.scroll_offset = 0.0

    def total_lines(self) -> int:
        return len(self.lines)
