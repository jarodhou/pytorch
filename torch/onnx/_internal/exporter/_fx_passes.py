# mypy: allow-untyped-defs
from __future__ import annotations

import torch
import torch.export
import torch.fx
from torch.onnx._internal.exporter import _decomp, _registration
from torch.onnx._internal.fx import diagnostics, passes


_ATEN_ASSERTION_TARGETS = frozenset(
    {
        torch.ops.aten.sym_constrain_range_for_size.default,
        torch.ops.aten._assert_async.msg,
    }
)


def decompose_with_registry(
    exported_program: torch.export.ExportedProgram, registry: _registration.ONNXRegistry
) -> torch.export.ExportedProgram:
    """Decompose the exported program with the given registry.

    This function is needed so it shows clearly on the profiler results.
    """
    decomp_table = _decomp.create_onnx_friendly_decomposition_table(registry)
    onnx_registered_ops = set(_decomp.get_onnx_implemented_overloads(registry))
    # Try to preserve some known CompositeImplicitAutograd ops
    aten = torch.ops.aten
    to_preserve = {
        aten._upsample_bilinear2d_aa.default,
        aten._upsample_nearest_exact1d.vec,
        aten._upsample_nearest_exact2d.vec,
        aten._upsample_nearest_exact3d.vec,
        aten.group_norm.default,
        aten.linear.default,
        aten.upsample_bilinear2d.default,
        aten.upsample_bilinear2d.vec,
        aten.upsample_linear1d.default,
        aten.upsample_linear1d.vec,
        aten.upsample_nearest1d.default,
        aten.upsample_nearest1d.vec,
        aten.upsample_nearest2d.default,
        aten.upsample_nearest2d.vec,
        aten.upsample_nearest3d.default,
        aten.upsample_nearest3d.vec,
        aten.upsample_trilinear3d.default,
        aten.upsample_trilinear3d.vec,
    }
    # We can only preserve implemented ops
    can_preserve = tuple(to_preserve.intersection(onnx_registered_ops))
    return exported_program.run_decompositions(decomp_table, _preserve_ops=can_preserve)


def insert_type_promotion_nodes(
    graph_module: torch.fx.GraphModule,
) -> torch.fx.GraphModule:
    """Inplace pass to insert explicit type promotion nodes."""
    diagnostic_context = diagnostics.DiagnosticContext(
        "torch.onnx.export",
        torch.__version__,
    )
    return passes.InsertTypePromotion(diagnostic_context, graph_module).run()


def remove_assertion_nodes(graph_module: torch.fx.GraphModule) -> torch.fx.GraphModule:
    """Remove all assertion and check nodes from the FX graph"""
    for node in graph_module.graph.nodes:
        if node.op == "call_function" and node.target in _ATEN_ASSERTION_TARGETS:
            graph_module.graph.erase_node(node)
    graph_module.recompile()
    return graph_module
