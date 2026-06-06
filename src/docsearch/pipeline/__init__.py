"""Pipeline: call graph, topo sort, code generator, evaluator."""

from docsearch.pipeline.call_graph import extract_module
from docsearch.pipeline.code_generator import generate_code, render_documentation
from docsearch.pipeline.entities import Entity, EntityKind, Module
from docsearch.pipeline.evaluator import EntityResult, EvaluationResult, evaluate
from docsearch.pipeline.topo_sort import (
    Component,
    condensation_edges,
    flatten_order,
    reverse_topological_order,
    strongly_connected_components,
)

__all__ = [
    "Entity",
    "EntityKind",
    "Module",
    "Component",
    "EntityResult",
    "EvaluationResult",
    "extract_module",
    "strongly_connected_components",
    "condensation_edges",
    "reverse_topological_order",
    "flatten_order",
    "evaluate",
    "generate_code",
    "render_documentation",
]
