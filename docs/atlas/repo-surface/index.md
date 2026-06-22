---
title: "Layer 1: Repository Surface"
---

<nav class="atlas-breadcrumb">
<a href="../">Atlas</a> &raquo; Layer 1: Repository Surface
</nav>

# Layer 1: Repository Surface

<div class="atlas-metadata">
Category: <strong>Structural</strong> | Generated: 2026-03-18T23:55:29.924964+00:00
</div>

## Map

=== "Interactive (Mermaid)"

    ```mermaid
    graph TD
        D0["azlin&lt;br/&gt;0 py / 14 total"]
        D1["context&lt;br/&gt;0 py / 1 total"]
        D2[".github&lt;br/&gt;0 py / 3 total"]
        D3["agents&lt;br/&gt;0 py / 36 total"]
        D4["aw&lt;br/&gt;0 py / 1 total"]
        D5["workflows&lt;br/&gt;0 py / 25 total"]
        D6["benchmarks&lt;br/&gt;2 py / 3 total"]
        D7["docs&lt;br/&gt;0 py / 55 total"]
        D8["docs-site&lt;br/&gt;0 py / 3 total"]
        D9["advanced&lt;br/&gt;0 py / 5 total"]
        D10["ai&lt;br/&gt;0 py / 3 total"]
        D11["authentication&lt;br/&gt;0 py / 2 total"]
        D12["bastion&lt;br/&gt;0 py / 2 total"]
        D13["batch&lt;br/&gt;0 py / 5 total"]
        D14["commands&lt;br/&gt;0 py / 1 total"]
        D15["development&lt;br/&gt;0 py / 3 total"]
        D16["getting-started&lt;br/&gt;0 py / 6 total"]
        D17["javascripts&lt;br/&gt;0 py / 1 total"]
        D18["monitoring&lt;br/&gt;0 py / 2 total"]
        D19["storage&lt;br/&gt;0 py / 3 total"]
        D20["stylesheets&lt;br/&gt;0 py / 1 total"]
        D21["troubleshooting&lt;br/&gt;0 py / 1 total"]
        D22["vm-lifecycle&lt;br/&gt;0 py / 7 total"]
        D23["contributing&lt;br/&gt;0 py / 1 total"]
        D24["examples&lt;br/&gt;0 py / 1 total"]
        D25["features&lt;br/&gt;0 py / 9 total"]
        D26["how-to&lt;br/&gt;0 py / 5 total"]
        D27["pwa&lt;br/&gt;0 py / 5 total"]
        D28["reference&lt;br/&gt;0 py / 5 total"]
        D29["specs&lt;br/&gt;0 py / 4 total"]
        D30["technical&lt;br/&gt;0 py / 2 total"]
        D31["testing&lt;br/&gt;0 py / 4 total"]
        D32["troubleshooting&lt;br/&gt;0 py / 3 total"]
        D33["tutorials&lt;br/&gt;0 py / 3 total"]
        D34["vscode&lt;br/&gt;0 py / 4 total"]
        D35["pwa&lt;br/&gt;0 py / 45 total"]
        D36["design-specs&lt;br/&gt;0 py / 1 total"]
        D37["docs&lt;br/&gt;0 py / 7 total"]
        D38["public&lt;br/&gt;0 py / 13 total"]
        D39["src&lt;br/&gt;0 py / 4 total"]
        D0 --> D2
        D2 --> D3
        D2 --> D4
        D2 --> D5
        D0 --> D6
        D0 --> D7
        D0 --> D8
        D8 --> D9
        D8 --> D10
        D8 --> D11
        D8 --> D12
        D8 --> D13
        D8 --> D14
        D8 --> D15
        D8 --> D16
        D8 --> D17
        D8 --> D18
        D8 --> D19
        D8 --> D20
        D8 --> D21
        D8 --> D22
        D7 --> D23
        D7 --> D24
        D7 --> D25
        D7 --> D26
        D7 --> D27
        D7 --> D28
        D7 --> D29
        D7 --> D30
        D7 --> D31
        D7 --> D32
        D7 --> D33
        D0 --> D35
        D35 --> D36
        D35 --> D37
        D35 --> D38
        D35 --> D39

        click D0 "../" "Back to Atlas index"
    ```

=== "High-Fidelity (Graphviz)"

    <div class="atlas-diagram-container">
    <img src="repo-surface-dot.svg" alt="Repository Surface - Graphviz">
    </div>

=== "Data Table"

    | Directory | Role | Python | Total |
    |-----------|------|--------|-------|
    | `/home/azureuser/src/azlin` | config | 0 | 14 |
    | `/home/azureuser/src/azlin/.claude/context` | docs | 0 | 1 |
    | `/home/azureuser/src/azlin/.github` | config | 0 | 3 |
    | `/home/azureuser/src/azlin/.github/agents` | docs | 0 | 36 |
    | `/home/azureuser/src/azlin/.github/aw` | other | 0 | 1 |
    | `/home/azureuser/src/azlin/.github/workflows` | config | 0 | 25 |
    | `/home/azureuser/src/azlin/benchmarks` | other | 2 | 3 |
    | `/home/azureuser/src/azlin/docs` | docs | 0 | 55 |
    | `/home/azureuser/src/azlin/docs-site` | docs | 0 | 3 |
    | `/home/azureuser/src/azlin/docs-site/advanced` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs-site/ai` | docs | 0 | 3 |
    | `/home/azureuser/src/azlin/docs-site/authentication` | docs | 0 | 2 |
    | `/home/azureuser/src/azlin/docs-site/bastion` | docs | 0 | 2 |
    | `/home/azureuser/src/azlin/docs-site/batch` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs-site/commands` | docs | 0 | 1 |
    | `/home/azureuser/src/azlin/docs-site/commands/advanced` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs-site/commands/ai` | docs | 0 | 2 |
    | `/home/azureuser/src/azlin/docs-site/commands/auth` | docs | 0 | 6 |
    | `/home/azureuser/src/azlin/docs-site/commands/autopilot` | docs | 0 | 6 |
    | `/home/azureuser/src/azlin/docs-site/commands/bastion` | docs | 0 | 6 |
    | `/home/azureuser/src/azlin/docs-site/commands/batch` | docs | 0 | 6 |
    | `/home/azureuser/src/azlin/docs-site/commands/compose` | docs | 0 | 4 |
    | `/home/azureuser/src/azlin/docs-site/commands/context` | docs | 0 | 8 |
    | `/home/azureuser/src/azlin/docs-site/commands/doit` | docs | 0 | 7 |
    | `/home/azureuser/src/azlin/docs-site/commands/env` | docs | 0 | 7 |
    | `/home/azureuser/src/azlin/docs-site/commands/fleet` | docs | 0 | 2 |
    | `/home/azureuser/src/azlin/docs-site/commands/github-runner` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs-site/commands/ip` | docs | 0 | 2 |
    | `/home/azureuser/src/azlin/docs-site/commands/keys` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs-site/commands/snapshot` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs-site/commands/storage` | docs | 0 | 7 |
    | `/home/azureuser/src/azlin/docs-site/commands/template` | docs | 0 | 6 |
    | `/home/azureuser/src/azlin/docs-site/commands/util` | docs | 0 | 13 |
    | `/home/azureuser/src/azlin/docs-site/commands/vm` | docs | 0 | 14 |
    | `/home/azureuser/src/azlin/docs-site/development` | docs | 0 | 3 |
    | `/home/azureuser/src/azlin/docs-site/getting-started` | docs | 0 | 6 |
    | `/home/azureuser/src/azlin/docs-site/javascripts` | other | 0 | 1 |
    | `/home/azureuser/src/azlin/docs-site/monitoring` | docs | 0 | 2 |
    | `/home/azureuser/src/azlin/docs-site/storage` | docs | 0 | 3 |
    | `/home/azureuser/src/azlin/docs-site/stylesheets` | other | 0 | 1 |
    | `/home/azureuser/src/azlin/docs-site/troubleshooting` | docs | 0 | 1 |
    | `/home/azureuser/src/azlin/docs-site/vm-lifecycle` | docs | 0 | 7 |
    | `/home/azureuser/src/azlin/docs/contributing` | docs | 0 | 1 |
    | `/home/azureuser/src/azlin/docs/examples` | docs | 0 | 1 |
    | `/home/azureuser/src/azlin/docs/features` | docs | 0 | 9 |
    | `/home/azureuser/src/azlin/docs/how-to` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs/pwa` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs/pwa/testing` | docs | 0 | 2 |
    | `/home/azureuser/src/azlin/docs/reference` | docs | 0 | 5 |
    | `/home/azureuser/src/azlin/docs/specs` | docs | 0 | 4 |

## Legend

<div class="atlas-legend" markdown>

| Symbol | Meaning |
|--------|---------|
| Rectangle | Directory |
| Arrow | Parent-child relationship |
| Label | `name` / `py count` / `total count` |

</div>

## Key Findings

- 117 directories discovered
- 1 entry points identified

## Detail

??? info "Full data (click to expand)"

    *No detailed data available.*

## Cross-References

<div class="atlas-crossref" markdown>

- [Layer 2: AST + LSP Bindings](../ast-lsp-bindings/)
- [Layer 7: Service Components](../service-components/)

</div>

<div class="atlas-footer">

Source: `layer1_repo_surface.json` | [Mermaid source](repo-surface.mmd)

</div>
