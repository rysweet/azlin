---
title: Code Atlas
---

# Code Atlas

<div class="atlas-metadata">Generated: 2026-03-18 23:56 UTC</div>

## Layer Overview

<div class="grid cards atlas-grid" markdown>

-   <span class="atlas-icon--structural">:material-folder-outline:</span> **[Layer 1: Repository Surface](repo-surface/)**

    ---

    Directory tree, file counts, project structure

    <div class="atlas-coverage">
    <div class="atlas-coverage__bar" style="width:100%"></div>
    </div>
    <small>100% coverage</small>

-   <span class="atlas-icon--structural">:material-code-braces:</span> **[Layer 2: AST + LSP Bindings](ast-lsp-bindings/)**

    ---

    Cross-file imports, symbol references, dead code

    <div class="atlas-coverage">
    <div class="atlas-coverage__bar" style="width:100%"></div>
    </div>
    <small>100% coverage</small>

    <div class="atlas-scale">
    **total definitions**: 605 | **total exports**: 27 | **total imports**: 91 | **potentially dead**: 1
    </div>

-   <span class="atlas-icon--structural">:material-package-variant:</span> **[Layer 3: Compile-time Dependencies](compile-deps/)**

    ---

    External deps, internal import graph, circular deps

    <div class="atlas-coverage">
    <div class="atlas-coverage__bar" style="width:100%"></div>
    </div>
    <small>100% coverage</small>

    <div class="atlas-scale">
    **external dep**: 87 | **internal packages**: 18 | **internal edges**: 18 | **circular dependency**: 0
    </div>

-   <span class="atlas-icon--structural">:material-server-network:</span> **[Layer 4: Runtime Topology](runtime-topology/)**

    ---

    Processes, ports, subprocess calls, env vars

    <div class="atlas-coverage">
    <div class="atlas-coverage__bar" style="width:100%"></div>
    </div>
    <small>100% coverage</small>

    <div class="atlas-scale">
    **subprocess call**: 17 | **unique subprocess files**: 4 | **port binding**: 0 | **docker service**: 0
    </div>

-   <span class="atlas-icon--behavioral">:material-api:</span> **[Layer 5: API Contracts](api-contracts/)**

    ---

    CLI commands, HTTP routes, hooks, recipes

    <div class="atlas-coverage">
    <div class="atlas-coverage__bar" style="width:100%"></div>
    </div>
    <small>100% coverage</small>

    <div class="atlas-scale">
    **cli command**: 0 | **cli argument**: 13 | **click typer command**: 1 | **http route**: 0
    </div>

-   <span class="atlas-icon--behavioral">:material-transit-connection-variant:</span> **[Layer 6: Data Flow](data-flow/)**

    ---

    File I/O, database ops, network I/O, data paths

    <div class="atlas-coverage">
    <div class="atlas-coverage__bar" style="width:100%"></div>
    </div>
    <small>100% coverage</small>

    <div class="atlas-scale">
    **file io**: 15 | **database op**: 0 | **network io**: 1 | **transformation point**: 0
    </div>

-   <span class="atlas-icon--structural">:material-view-module:</span> **[Layer 7: Service Components](service-components/)**

    ---

    Package boundaries, coupling metrics, architecture

    <div class="atlas-coverage">
    <div class="atlas-coverage__bar" style="width:100%"></div>
    </div>
    <small>100% coverage</small>

    <div class="atlas-scale">
    **total packages**: 2 | **core packages**: 0 | **leaf packages**: 1
    </div>

-   <span class="atlas-icon--behavioral">:material-routes:</span> **[Layer 8: User Journeys](user-journeys/)**

    ---

    Entry-to-outcome traces for CLI, HTTP, hooks

    <div class="atlas-coverage">
    <div class="atlas-coverage__bar" style="width:100%"></div>
    </div>
    <small>100% coverage</small>

    <div class="atlas-scale">
    **total journeys**: 3 | **cli journeys**: 3 | **http journeys**: 0 | **hook journeys**: 0
    </div>

</div>

## Languages

Primary language: **Rust** | Total code: **77,314** lines | Detected via: *tokei*

| Language | Files | Code Lines | % | Analysis Available |
|----------|------:|-----------:|--:|-------------------|
| Rust | 241 | 47,244 | 61.1% | Dependencies (Cargo.toml) |
| Json | 9 | 12,414 | 16.1% | File-level only |
| Typescript | 69 | 10,604 | 13.7% | Dependencies (package.json) |
| Python | 18 | 3,839 | 5.0% | Full (AST, imports, dead code, journeys) |
| Javascript | 21 | 1,196 | 1.5% | Dependencies (package.json) |
| Bash | 13 | 894 | 1.2% | File-level only |
| Yaml | 5 | 499 | 0.6% | File-level only |
| Toml | 9 | 274 | 0.4% | File-level only |
| Hcl | 3 | 179 | 0.2% | File-level only |
| Html | 2 | 97 | 0.1% | File-level only |
| Css | 2 | 56 | 0.1% | File-level only |
| Svg | 2 | 18 | 0.0% | File-level only |

> **Analysis Coverage**: This codebase is primarily **Rust** (61.1% of code). Full AST analysis is available for Python files. Rust analysis covers dependencies and file structure. See [issue #3310](https://github.com/user/repo/issues/3310) for expanded language support.

## Legend

<div class="atlas-legend" markdown>

| Category | Layers | Color |
|----------|--------|-------|
| Structural | 1, 2, 3, 4, 7 | Blue |
| Behavioral | 5, 6, 8 | Orange |

</div>

## Quick Links

- [Health Dashboard](health.md) -- cross-layer check results
- [Glossary](glossary.md) -- atlas terminology
