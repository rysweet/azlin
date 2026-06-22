---
title: "Layer 8: User Journeys"
---

<nav class="atlas-breadcrumb">
<a href="../">Atlas</a> &raquo; Layer 8: User Journeys
</nav>

# Layer 8: User Journeys

<div class="atlas-metadata">
Category: <strong>Behavioral</strong> | Generated: 2026-03-18T23:55:51.620161+00:00
</div>

## Map

=== "Interactive (Mermaid)"

    ```mermaid
    sequenceDiagram
        participant User
        participant CLI as cli.py
        participant cli
        User->>CLI: cli:cli.py
        CLI->>cli: main()
        cli->>cli: return_value: main
        cli-->>CLI: result
        CLI-->>User: exit code

        User->>CLI: cli:cli.py
        CLI->>cli: main()
        cli->>cli: return_value: main
        cli-->>CLI: result
        CLI-->>User: exit code

        User->>CLI: cli:cli.py
        CLI->>cli: main()
        cli->>cli: return_value: main
        cli-->>CLI: result
        CLI-->>User: exit code
    ```

=== "High-Fidelity (Graphviz)"

    <div class="atlas-diagram-container">
    <img src="user-journeys-dot.svg" alt="User Journeys - Graphviz">
    </div>

=== "Data Table"

    | Entry | Type | Depth | Functions | Outcomes |
    |-------|------|-------|-----------|----------|
    | `cli:cli.py` | cli | 0 | 1 | 1 |
    | `cli:cli.py` | cli | 0 | 1 | 1 |
    | `cli:cli.py` | cli | 0 | 1 | 1 |

## Legend

<div class="atlas-legend" markdown>

| Symbol | Meaning |
|--------|---------|
| Actor | User |
| Participant | Module/component |
| Solid arrow | Synchronous call |
| Dashed arrow | Response/return |

</div>

## Key Findings

- 3 user journeys traced
- 382 functions unreachable from any entry point

## Detail

??? info "Full data (click to expand)"

    **Summary metrics:**

    - **Total Journeys**: 3
    - **Cli Journeys**: 3
    - **Http Journeys**: 0
    - **Hook Journeys**: 0
    - **Out Of Scope Journeys**: 0
    - **Avg Trace Depth**: 0.0
    - **Total Functions In Graph**: 382
    - **Total Functions Reached**: 3
    - **Unreachable Function Count**: 382

## Cross-References

<div class="atlas-crossref" markdown>

- [Layer 2: AST + LSP Bindings](../ast-lsp-bindings/)
- [Layer 4: Runtime Topology](../runtime-topology/)
- [Layer 5: API Contracts](../api-contracts/)
- [Layer 6: Data Flow](../data-flow/)

</div>

<div class="atlas-footer">

Source: `layer8_user_journeys.json` | [Mermaid source](user-journeys.mmd)

</div>
