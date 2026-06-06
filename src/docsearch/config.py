"""
Configuration for DocSearch: bilevel tree search for documentation optimization.
"""

# Search parameters.
DEFAULT_BUDGET = 30  # Total budget B (max LLM-scored search iterations).
W = 5  # Width: max refinement attempts per entity before marking it intractable.
