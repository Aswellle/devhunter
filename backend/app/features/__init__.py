"""
app/features/__init__.py
"""
from app.features.extractor import ItemFeatureExtractor, ItemFeatures, feature_extractor
from app.features.entities import EntityExtractor, entity_extractor
from app.features.temporal import temporal_score, detect_event_type, get_event_window_hours
from app.features.semantic import (
    SemanticSimilarity,
    CharacterNgramSimilarity,
    EmbeddingSimilarity,
    semantic_similarity,
    get_semantic_similarity,
)

__all__ = [
    "ItemFeatureExtractor",
    "ItemFeatures",
    "feature_extractor",
    "EntityExtractor",
    "entity_extractor",
    "temporal_score",
    "detect_event_type",
    "get_event_window_hours",
    "SemanticSimilarity",
    "CharacterNgramSimilarity",
    "EmbeddingSimilarity",
    "semantic_similarity",
    "get_semantic_similarity",
]
