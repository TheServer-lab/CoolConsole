from __future__ import annotations


def suggested_typing_speed(text: str) -> tuple[int, int]:
    if len(text) < 24:
        return 22, 1
    if len(text) < 64:
        return 14, 2
    return 10, 3
