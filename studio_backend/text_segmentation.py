from __future__ import annotations

SYNTHESIS_CHUNK_MAX_CHARACTERS = 64

_STRONG_BOUNDARIES = frozenset("。！？!?\n")
_SECONDARY_BOUNDARIES = frozenset("、，,；;：:")
_CLOSING_MARKS = frozenset("」』】）》”’\"'")
_JOINING_MARKS = frozenset(("\u200d", "\ufe0e", "\ufe0f"))


def _boundary_positions(text: str) -> tuple[list[int], list[int], list[int]]:
    strong: list[int] = []
    secondary: list[int] = []
    whitespace: list[int] = []
    index = 0
    while index < len(text):
        character = text[index]
        end = index + 1
        if character in _STRONG_BOUNDARIES:
            while end < len(text) and text[end] in _CLOSING_MARKS:
                end += 1
            strong.append(end)
            index = end
            continue
        if character in _SECONDARY_BOUNDARIES:
            secondary.append(end)
        elif character.isspace():
            whitespace.append(end)
        index += 1
    return strong, secondary, whitespace


def _latest_boundary(
    positions: list[int], *, start: int, minimum: int, maximum: int, target: int | None = None
) -> int | None:
    candidates = [position for position in positions if minimum <= position <= maximum]
    if candidates:
        if target is not None:
            return min(candidates, key=lambda position: (abs(position - target), -position))
        return candidates[-1]
    fallback = [position for position in positions if start < position <= maximum]
    return fallback[-1] if fallback else None


def _safe_hard_cut(text: str, *, start: int, maximum: int) -> int:
    cut = maximum
    while cut > start + 1 and cut < len(text):
        if text[cut] in _JOINING_MARKS or text[cut - 1] == "\u200d":
            cut -= 1
            continue
        break
    return cut


def split_synthesis_text(
    text: str, *, max_characters: int = SYNTHESIS_CHUNK_MAX_CHARACTERS
) -> list[str]:
    """Split long speech at natural Japanese boundaries without changing short input."""

    normalized = str(text).strip()
    if not normalized:
        return []
    if max_characters < 8:
        raise ValueError("max_characters must be at least 8")
    if len(normalized) <= max_characters:
        return [normalized]

    strong, secondary, whitespace = _boundary_positions(normalized)
    minimum_width = max(8, int(max_characters * 0.45))
    chunks: list[str] = []
    start = 0
    while len(normalized) - start > max_characters:
        remaining = len(normalized) - start
        maximum = start + max_characters
        if remaining <= max_characters * 2:
            minimum = start + 8
            target = start + round(remaining / 2)
            cut = (
                _latest_boundary(
                    strong,
                    start=start,
                    minimum=minimum,
                    maximum=maximum,
                    target=target,
                )
                or _latest_boundary(
                    secondary,
                    start=start,
                    minimum=minimum,
                    maximum=maximum,
                    target=target,
                )
                or _latest_boundary(
                    whitespace,
                    start=start,
                    minimum=minimum,
                    maximum=maximum,
                    target=target,
                )
                or _safe_hard_cut(normalized, start=start, maximum=target)
            )
        else:
            minimum = start + minimum_width
            cut = (
                _latest_boundary(strong, start=start, minimum=minimum, maximum=maximum)
                or _latest_boundary(secondary, start=start, minimum=minimum, maximum=maximum)
                or _latest_boundary(whitespace, start=start, minimum=minimum, maximum=maximum)
                or _safe_hard_cut(normalized, start=start, maximum=maximum)
            )
        chunk = normalized[start:cut].strip()
        if chunk:
            chunks.append(chunk)
        start = cut

    final = normalized[start:].strip()
    if final:
        chunks.append(final)
    return chunks
