"""System prompt components (4-layer)."""

from src.prompts.layer1_vygotsky import LAYER1_VYGOTSKY_PRINCIPLES
from src.prompts.layer2_grade import get_grade_layer_prompt

__all__ = ["LAYER1_VYGOTSKY_PRINCIPLES", "get_grade_layer_prompt"]
