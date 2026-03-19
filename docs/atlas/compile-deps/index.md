---
title: "Layer 3: Compile-time Dependencies"
---

<nav class="atlas-breadcrumb">
<a href="../">Atlas</a> &raquo; Layer 3: Compile-time Dependencies
</nav>

# Layer 3: Compile-time Dependencies

<div class="atlas-metadata">
Category: <strong>Structural</strong> | Generated: 2026-03-18T23:55:34.998941+00:00
</div>

## Map

=== "Interactive (Mermaid)"

    ```mermaid
    graph LR
        subgraph ext["External Dependencies"]
            E0["tokio<br/>imports: 0"]
            E1["serde<br/>imports: 0"]
            E2["serde_json<br/>imports: 0"]
            E3["serde_yaml<br/>imports: 0"]
            E4["toml<br/>imports: 0"]
            E5["clap<br/>imports: 0"]
            E6["clap_complete<br/>imports: 0"]
            E7["indicatif<br/>imports: 0"]
            E8["dialoguer<br/>imports: 0"]
            E9["console<br/>imports: 0"]
            E10["ratatui<br/>imports: 0"]
            E11["crossterm<br/>imports: 0"]
            E12["azure_identity<br/>imports: 0"]
            E13["azure_core<br/>imports: 0"]
            E14["azure_mgmt_compute<br/>imports: 0"]
            E15["azure_mgmt_network<br/>imports: 0"]
            E16["azure_mgmt_resources<br/>imports: 0"]
            E17["azure_mgmt_storage<br/>imports: 0"]
            E18["azure_security_keyvault_secrets<br/>imports: 0"]
            E19["azure_mgmt_costmanagement<br/>imports: 0"]
        end

        subgraph int["Internal Packages"]
            P0["benchmark_parallel_vm_list"]
            P1["benchmark_vm_list"]
            P2["audit_key_operations"]
            P3["cli_documentation"]
            P4["example_manager"]
            P5["extractor"]
            P6["generator"]
            P7["hasher"]
            P8["models"]
            P9["sync_manager"]
            P10["validator"]
            P11["doc_sync"]
            P12["extract_help"]
            P13["generate_docs"]
            P14["test_audit_key_operations"]
            P15["validate_documentation"]
            P16["azlin"]
            P17["rust_bridge"]
        end

        click P0 "../compile-deps/" "View compile deps"
    ```

=== "High-Fidelity (Graphviz)"

    <div class="atlas-diagram-container">
    <img src="compile-deps-dot.svg" alt="Compile-time Dependencies - Graphviz">
    </div>

=== "Data Table"

    | Package | Version | Group | Import Count |
    |---------|---------|-------|-------------|
    | tokio | 1 | dependencies | 0 |
    | serde | 1 | dependencies | 0 |
    | serde_json | 1 | dependencies | 0 |
    | serde_yaml | 0.9 | dependencies | 0 |
    | toml | 0.8 | dependencies | 0 |
    | clap | 4 | dependencies | 0 |
    | clap_complete | 4 | dependencies | 0 |
    | indicatif | 0.17 | dependencies | 0 |
    | dialoguer | 0.11 | dependencies | 0 |
    | console | 0.15 | dependencies | 0 |
    | ratatui | 0.30 | dependencies | 0 |
    | crossterm | 0.29 | dependencies | 0 |
    | azure_identity | 0.22 | dependencies | 0 |
    | azure_core | 0.22 | dependencies | 0 |
    | azure_mgmt_compute | 0.2 | dependencies | 0 |
    | azure_mgmt_network | 0.2 | dependencies | 0 |
    | azure_mgmt_resources | 0.2 | dependencies | 0 |
    | azure_mgmt_storage | 0.2 | dependencies | 0 |
    | azure_security_keyvault_secrets | 0.2 | dependencies | 0 |
    | azure_mgmt_costmanagement | 0.2 | dependencies | 0 |
    | reqwest | 0.12 | dependencies | 0 |
    | anyhow | 1 | dependencies | 0 |
    | thiserror | 2 | dependencies | 0 |
    | color-eyre | 0.6 | dependencies | 0 |
    | tracing | 0.1 | dependencies | 0 |
    | tracing-subscriber | 0.3 | dependencies | 0 |
    | sha2 | 0.10 | dependencies | 0 |
    | chrono | 0.4 | dependencies | 0 |
    | uuid | 1 | dependencies | 0 |
    | regex | 1 | dependencies | 0 |

## Legend

<div class="atlas-legend" markdown>

| Symbol | Meaning |
|--------|---------|
| `ext` subgraph | External dependencies |
| `int` subgraph | Internal packages |
| Edge label N | Import count between packages |

</div>

## Key Findings

- No circular dependencies detected

## Detail

??? info "Full data (click to expand)"

    **Summary metrics:**

    - **External Dep Count**: 87
    - **Internal Packages**: 18
    - **Internal Edges**: 18
    - **Circular Dependency Count**: 0
    - **Unused Dep Count**: 0
    - **Undeclared Dep Count**: 4

## Cross-References

<div class="atlas-crossref" markdown>

- [Layer 2: AST + LSP Bindings](../ast-lsp-bindings/)
- [Layer 7: Service Components](../service-components/)

</div>

<div class="atlas-footer">

Source: `layer3_compile_deps.json` | [Mermaid source](compile-deps.mmd)

</div>
