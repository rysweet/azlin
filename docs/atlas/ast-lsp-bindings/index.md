---
title: "Layer 2: AST + LSP Bindings"
---

<nav class="atlas-breadcrumb">
<a href="../">Atlas</a> &raquo; Layer 2: AST + LSP Bindings
</nav>

# Layer 2: AST + LSP Bindings

<div class="atlas-metadata">
Category: <strong>Structural</strong> | Generated: 2026-03-18T23:55:34.523187+00:00
</div>

## Map

=== "Interactive (Mermaid)"

    ```mermaid
    graph LR
        F0["models<br/>refs: 20"]
        F1["example_manager<br/>refs: 2"]
        F2["extractor<br/>refs: 2"]
        F3["generator<br/>refs: 2"]
        F4["hasher<br/>refs: 2"]
        F5["validator<br/>refs: 2"]
        F6["sync_manager<br/>refs: 1"]
        F7["benchmark_parallel_vm_list<br/>refs: 0"]
        F8["benchmark_vm_list<br/>refs: 0"]
        F9["audit_key_operations<br/>refs: 0"]
        F10["__init__<br/>refs: 0"]
        F11["doc_sync<br/>refs: 0"]
        F12["extract_help<br/>refs: 0"]
        F13["generate_docs<br/>refs: 0"]
        F14["test_audit_key_operations<br/>refs: 0"]
        F15["validate_documentation<br/>refs: 0"]
        F16["__init__<br/>refs: 0"]
        F17["rust_bridge<br/>refs: 0"]
        F18["health-calculator<br/>refs: 0"]
        F19["VmWizardTypes<br/>refs: 0"]
        F20["vm-name-validator<br/>refs: 0"]
        F21["azure-client<br/>refs: 0"]
        F22["logger<br/>refs: 0"]
        F23["monitor-client<br/>refs: 0"]
        F24["ssh-key-validator<br/>refs: 0"]
        F25["vm-name-validator<br/>refs: 0"]
        F26["env-validation<br/>refs: 0"]
        F27["logger<br/>refs: 0"]
        F28["token-storage<br/>refs: 0"]
        F29["WatchSettingsPanel<br/>refs: 0"]
        F10 --> F1
        F10 --> F2
        F10 --> F3
        F10 --> F4
        F10 --> F0
        F10 --> F6
        F10 --> F5
        F1 --> F0
        F2 --> F0
        F3 --> F0
        F4 --> F0
        F6 --> F1
        F6 --> F2
        F6 --> F3
        F6 --> F4
        F6 --> F0
        F6 --> F5
        F5 --> F0

        click F0 "../ast-lsp-bindings/" "View AST bindings"
    ```

=== "High-Fidelity (Graphviz)"

    <div class="atlas-diagram-container">
    <img src="ast-lsp-bindings-dot.svg" alt="AST + LSP Bindings - Graphviz">
    </div>

=== "Data Table"

    | Metric | Value |
    |--------|-------|
    | Total definitions | 605 |
    | Total exports | 27 |
    | Total imports | 91 |
    | Potentially dead | 1 |
    | Files with `__all__` | 9 |

## Legend

<div class="atlas-legend" markdown>

| Symbol | Meaning |
|--------|---------|
| Rectangle | Source file |
| Arrow | Import dependency |
| `refs: N` | Total reference count |

</div>

## Key Findings

- 605 total definitions across all files
- 1 potentially dead definitions (0.2% of total)
- 9 files without `__all__` exports

## Detail

??? info "Full data (click to expand)"

    **Summary metrics:**

    - **Total Definitions**: 605
    - **Total Exports**: 27
    - **Total Imports**: 91
    - **Potentially Dead Count**: 1
    - **Files With All**: 9
    - **Files Without All**: 9
    - **Importlib Dynamic Imports**: 2
    - **Language Counts**:
        - `python`: 63
        - `typescript`: 500
        - `csharp`: 20
        - `javascript`: 22
    - **Blarify Relationships**:
        - `CONTAINS`: 3109
        - `CLASS_DEFINITION`: 647
        - `FUNCTION_DEFINITION`: 3771
        - `total`: 7527

## Cross-References

<div class="atlas-crossref" markdown>

- [Layer 1: Repository Surface](../repo-surface/)
- [Layer 3: Compile-time Dependencies](../compile-deps/)
- [Layer 7: Service Components](../service-components/)
- [Layer 8: User Journeys](../user-journeys/)

</div>

<div class="atlas-footer">

Source: `layer2_ast_bindings.json` | [Mermaid source](ast-lsp-bindings.mmd)

</div>
