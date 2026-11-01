"""
app/recommendation/__init__.py

推荐域的共享纯函数模块：解释生成与离线评测指标。
生产推荐引擎位于 app/services/recommendation_service.py。
"""
from app.recommendation.explanations import ExplanationGenerator, explanation_generator

__all__ = [
    "ExplanationGenerator",
    "explanation_generator",
]
