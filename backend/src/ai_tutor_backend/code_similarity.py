from __future__ import annotations

import io
import keyword
import os
import token
import tokenize
from dataclasses import dataclass

from .repository import SQLiteResultRepository

DEFAULT_SIMILARITY_THRESHOLD = 0.85
DEFAULT_MAX_PENALTY = 30.0
MINIMUM_TOKEN_COUNT = 40


@dataclass(frozen=True, slots=True)
class SimilarityReview:
    similarity: float
    checked_submissions: int
    threshold: float
    penalty: float

    @property
    def is_high(self) -> bool:
        return self.checked_submissions > 0 and self.similarity >= self.threshold


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def _source_tokens(source: str, *, normalize_identifiers: bool) -> list[str]:
    result: list[str] = []
    ignored = {
        token.ENCODING,
        token.ENDMARKER,
        token.NEWLINE,
        token.NL,
        token.INDENT,
        token.DEDENT,
        token.COMMENT,
    }
    try:
        stream = io.BytesIO(source.encode("utf-8")).readline
        generated = tokenize.tokenize(stream)
        for item in generated:
            if item.type in ignored:
                continue
            value = item.string
            if item.type == token.NAME:
                value = value if keyword.iskeyword(value) else ("IDENT" if normalize_identifiers else value)
            elif item.type == token.STRING:
                value = "STRING"
            elif item.type == token.NUMBER:
                value = "NUMBER"
            result.append(value)
    except (IndentationError, SyntaxError, tokenize.TokenError, UnicodeError):
        return []
    return result


def _ngram_jaccard(left: list[str], right: list[str], width: int) -> float:
    if len(left) < width or len(right) < width:
        return 0.0
    left_grams = {tuple(left[index : index + width]) for index in range(len(left) - width + 1)}
    right_grams = {
        tuple(right[index : index + width]) for index in range(len(right) - width + 1)
    }
    union = left_grams | right_grams
    return len(left_grams & right_grams) / len(union) if union else 0.0


def calculate_code_similarity(left: str, right: str) -> float:
    """Return a stable 0..1 score while ignoring layout, comments and literal values."""

    left_raw = _source_tokens(left, normalize_identifiers=False)
    right_raw = _source_tokens(right, normalize_identifiers=False)
    if min(len(left_raw), len(right_raw)) < MINIMUM_TOKEN_COUNT:
        return 0.0

    left_normalized = _source_tokens(left, normalize_identifiers=True)
    right_normalized = _source_tokens(right, normalize_identifiers=True)
    raw_score = _ngram_jaccard(left_raw, right_raw, 5)
    normalized_score = _ngram_jaccard(left_normalized, right_normalized, 7)
    return min(1.0, max(raw_score, raw_score * 0.35 + normalized_score * 0.65))


class CodeSimilarityService:
    def __init__(
        self,
        repository: SQLiteResultRepository,
        *,
        threshold: float | None = None,
        max_penalty: float | None = None,
    ) -> None:
        self.repository = repository
        self.threshold = threshold or _env_float(
            "AI_TUTOR_SIMILARITY_THRESHOLD",
            DEFAULT_SIMILARITY_THRESHOLD,
            0.5,
            0.99,
        )
        self.max_penalty = max_penalty or _env_float(
            "AI_TUTOR_SIMILARITY_MAX_PENALTY",
            DEFAULT_MAX_PENALTY,
            1.0,
            100.0,
        )

    def review(self, case_id: str, student_id: str | None, source_code: str) -> SimilarityReview:
        candidates = self.repository.list_code_submissions(
            case_id,
            excluding_student_id=student_id,
        )
        highest = max(
            (calculate_code_similarity(source_code, candidate.source_code) for candidate in candidates),
            default=0.0,
        )
        penalty = 0.0
        if highest >= self.threshold:
            progress = (highest - self.threshold) / (1.0 - self.threshold)
            penalty = 10.0 + progress * max(0.0, self.max_penalty - 10.0)
            penalty = min(self.max_penalty, penalty)
        return SimilarityReview(
            similarity=round(highest, 4),
            checked_submissions=len(candidates),
            threshold=self.threshold,
            penalty=round(penalty, 1),
        )
