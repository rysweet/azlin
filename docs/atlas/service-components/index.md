---
title: "Layer 7: Service Components"
---

<nav class="atlas-breadcrumb">
<a href="../">Atlas</a> &raquo; Layer 7: Service Components
</nav>

# Layer 7: Service Components

<div class="atlas-metadata">
Category: <strong>Structural</strong> | Generated: 2026-03-18T23:55:35.270587+00:00
</div>

## Map

=== "Interactive (Mermaid)"

    ```mermaid
    graph TB
        subgraph feature["Feature Packages"]
            P0["azlin<br/>2 files<br/>I=0.00"]
        end

        subgraph leaf["Leaf Packages"]
            P1["cli_documentation<br/>8 files<br/>I=1.00"]
        end


        click P0 "../service-components/" "View details"
    ```

=== "High-Fidelity (Graphviz)"

    <div class="atlas-diagram-container">
    <img src="service-components-dot.svg" alt="Service Components - Graphviz">
    </div>

=== "Data Table"

    | Package | Files | Ca | Ce | Instability | Class |
    |---------|-------|----|----|-------------|-------|
    | `scripts.cli_documentation` | 8 | 0 | 7 | 1.00 | leaf |
    | `src.azlin` | 2 | 0 | 0 | 0.00 | feature |

## Legend

<div class="atlas-legend" markdown>

| Symbol | Meaning |
|--------|---------|
| Subgraph | Package classification |
| Rectangle | Package |
| `I=` | Instability metric (0=stable, 1=unstable) |
| Edge label N | Coupling count |

</div>

## Key Findings

- 2 packages analyzed
- 1 leaf packages (no dependents)

## Detail

??? info "Full data (click to expand)"

    **Summary metrics:**

    - **Total Packages**: 2
    - **By Classification**:
        - `leaf`: 1
        - `feature`: 1
    - **Core Packages**: 0
    - **Leaf Packages**: 1
    - **Utility Packages**: 0
    - **Feature Packages**: 1
    - **Avg Instability**: 1.0
    - **Most Coupled Pair**: 2 items
        - `scripts.cli_documentation`
        - `scripts.cli_documentation.example_manager`
    - **Total Cross Package Edges**: 18

## Cross-References

<div class="atlas-crossref" markdown>

- [Layer 2: AST + LSP Bindings](../ast-lsp-bindings/)
- [Layer 3: Compile-time Dependencies](../compile-deps/)

</div>

<div class="atlas-footer">

Source: `layer7_service_components.json` | [Mermaid source](service-components.mmd)

</div>
