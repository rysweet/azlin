---
title: "Layer 6: Data Flow"
---

<nav class="atlas-breadcrumb">
<a href="../">Atlas</a> &raquo; Layer 6: Data Flow
</nav>

# Layer 6: Data Flow

<div class="atlas-metadata">
Category: <strong>Behavioral</strong> | Generated: 2026-03-18T23:55:35.217575+00:00
</div>

## Map

=== "Interactive (Mermaid)"

    ```mermaid
    flowchart TD
        IO0[/"text write<br/>n=4"/]
        IO1[("text read<br/>n=4")]
        IO2[/"json write<br/>n=3"/]
        IO3[("json read<br/>n=2")]
        IO4[("yaml read<br/>n=1")]
        IO5[/"yaml write<br/>n=1"/]
        NET6("Network I/O<br/>n=1")
    ```

=== "High-Fidelity (Graphviz)"

    <div class="atlas-diagram-container">
    <img src="data-flow-dot.svg" alt="Data Flow - Graphviz">
    </div>

=== "Data Table"

    | Metric | Value |
    |--------|-------|
    | File I/O operations | 15 |
    | Database operations | 0 |
    | Network I/O | 1 |
    | Transformation points | 0 |
    | Files with I/O | 6 |

## Legend

<div class="atlas-legend" markdown>

| Symbol | Meaning |
|--------|---------|
| Stadium | Read operation |
| Parallelogram | Write operation |
| Cylinder | Database operation |
| Diamond | Transformation function |

</div>

## Key Findings

- 15 file I/O operations

## Detail

??? info "Full data (click to expand)"

    **Summary metrics:**

    - **File Io Count**: 15
    - **Database Op Count**: 0
    - **Network Io Count**: 1
    - **Transformation Point Count**: 0
    - **Files With Io**: 6

## Cross-References

<div class="atlas-crossref" markdown>

- [Layer 4: Runtime Topology](../runtime-topology/)
- [Layer 8: User Journeys](../user-journeys/)

</div>

<div class="atlas-footer">

Source: `layer6_data_flow.json` | [Mermaid source](data-flow.mmd)

</div>
