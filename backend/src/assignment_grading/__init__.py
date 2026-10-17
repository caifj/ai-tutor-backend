"""Independent assignment grading and similarity-review package."""

from .grading import compare_payloads
from .similarity import CodeSimilarityService, SimilarityReview, calculate_code_similarity

__all__ = [
    "CodeSimilarityService",
    "SimilarityReview",
    "calculate_code_similarity",
    "compare_payloads",
]
