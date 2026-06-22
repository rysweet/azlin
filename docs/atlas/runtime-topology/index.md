---
title: "Layer 4: Runtime Topology"
---

<nav class="atlas-breadcrumb">
<a href="../">Atlas</a> &raquo; Layer 4: Runtime Topology
</nav>

# Layer 4: Runtime Topology

<div class="atlas-metadata">
Category: <strong>Structural</strong> | Generated: 2026-03-18T23:55:34.911111+00:00
</div>

## Map

=== "Interactive (Mermaid)"

    ```mermaid
    graph LR
        S0(["subprocess.run"])
        S1(["python3"])
        S2(["&lt;dynamic&gt;"])
        S3(["os.system"])
        S4(["os.execvp"])
        FN0["benchmark_parallel_vm_list"]
        FN0 --> S0
        FN1["benchmark_vm_list"]
        FN1 --> S0
        FN2["test_audit_key_operations"]
        FN2 --> S1
        FN2 --> S1
        FN2 --> S1
        FN2 --> S1
        FN2 --> S1
        FN2 --> S1
        FN2 --> S1
        FN2 --> S1
        FN2 --> S1
        FN3["rust_bridge"]
        FN3 --> S2
        FN3 --> S2
        FN3 --> S3
        FN3 --> S2
        FN3 --> S4
        FN3 --> S3
    ```

=== "High-Fidelity (Graphviz)"

    <div class="atlas-diagram-container">
    <img src="runtime-topology-dot.svg" alt="Runtime Topology - Graphviz">
    </div>

=== "Data Table"

    | Metric | Value |
    |--------|-------|
    | Subprocess calls | 17 |
    | Unique files with subprocesses | 4 |
    | Port bindings | 0 |
    | Docker services | 0 |
    | Environment variables | 0 |

## Legend

<div class="atlas-legend" markdown>

| Symbol | Meaning |
|--------|---------|
| Rounded rect | External process/command |
| Hexagon | Port binding |
| Rectangle | Source module |
| Arrow | Invocation |

</div>

## Key Findings

- 17 subprocess calls across 4 files

## Detail

??? info "Full data (click to expand)"

    **Summary metrics:**

    - **Subprocess Call Count**: 17
    - **Unique Subprocess Files**: 4
    - **Port Binding Count**: 0
    - **Docker Service Count**: 0
    - **Dockerfile Count**: 0
    - **Env Var Count**: 0

## Cross-References

<div class="atlas-crossref" markdown>

- [Layer 6: Data Flow](../data-flow/)
- [Layer 8: User Journeys](../user-journeys/)

</div>

<div class="atlas-footer">

Source: `layer4_runtime_topology.json` | [Mermaid source](runtime-topology.mmd)

</div>
