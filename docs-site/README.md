# azlin Documentation Site

This directory contains the source files for the azlin MkDocs Material documentation site.

## Overview

**Site URL:** https://rysweet.github.io/azlin/ (after deployment)

**Status:** ✅ Ready for deployment

**Pages:** 149 markdown files covering all azlin features

## Directory Structure

```
docs-site/
├── index.md                    # Homepage
├── getting-started/            # Installation & quick start
├── authentication/             # Azure authentication
├── vm-lifecycle/               # VM management
├── storage/                    # Azure Files NFS
├── file-transfer/              # File copy & sync
├── environment/                # Environment variables
├── snapshots/                  # Snapshots & backups
├── bastion/                    # Azure Bastion
├── monitoring/                 # Monitoring & metrics
├── batch/                      # Batch operations
├── ai/                         # AI features
├── advanced/                   # Advanced topics
├── commands/                   # Command reference (47 pages)
├── development/                # Contributing & architecture
├── api/                        # Python API reference
├── troubleshooting/            # Common issues
├── stylesheets/                # Custom CSS
├── javascripts/                # Custom JS
└── assets/                     # Images & diagrams
```

## Building Locally

### Prerequisites

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install MkDocs with plugins
uv tool install mkdocs --with mkdocs-material --with mkdocs-git-revision-date-localized-plugin --with mkdocs-minify-plugin --with pymdown-extensions
```

### Build & Serve

```bash
# From project root
cd /Users/ryan/src/azlin

# Build documentation
mkdocs build

# Serve locally (with hot reload)
mkdocs serve

# Open browser to http://127.0.0.1:8000
```

### Generate Command Documentation

```bash
# Generate command reference pages
python scripts/extract_help.py --output docs-site/commands/

# Use --mock flag if azlin not installed
python scripts/extract_help.py --output docs-site/commands/ --mock
```

## Editing Documentation

### Adding New Pages

1. Create markdown file in appropriate directory
2. Add to `nav:` section in `mkdocs.yml`
3. Test locally with `mkdocs serve`
4. Commit and push

### Markdown Features

**Admonitions:**
```markdown
!!! note "Title"
    Content here

!!! tip "Pro Tip"
    Helpful hint

!!! warning "Caution"
    Important warning
```

**Code Blocks:**
```markdown
```bash
azlin new --name myvm
```
```

**Tabs:**
```markdown
=== "Tab 1"
    Content 1

=== "Tab 2"
    Content 2
```

**Links:**
```markdown
[Link text](relative/path.md)
[External](https://example.com)
```

## Deployment

### Automatic (via GitHub Actions)

Merging to `main` automatically triggers deployment:
1. GitHub Actions builds the site
2. Deploys to GitHub Pages
3. Available at https://rysweet.github.io/azlin/

### Manual Deployment

```bash
# Deploy to GitHub Pages
mkdocs gh-deploy --force
```

## GitHub Actions Workflows

### Production Deployment (`.github/workflows/docs.yml`)
- Triggers on push to `main`
- Builds and deploys automatically
- No configuration needed

### PR Preview (`.github/workflows/docs-pr.yml`)
- Triggers on PRs affecting documentation
- Builds preview
- Creates downloadable artifact
- Comments on PR

## Configuration

**Main config:** `mkdocs.yml` (project root)

**Key sections:**
- `site_name`: Site title
- `theme`: Material theme configuration
- `nav`: Navigation structure
- `plugins`: MkDocs plugins
- `markdown_extensions`: Markdown features

## Content Guidelines

### Writing Style
- Clear, concise language
- Use active voice
- Include examples
- Add troubleshooting sections
- Cross-reference related pages

### Structure
- Start with overview
- Provide quick examples
- Explain options/parameters
- Include common scenarios
- Add "See Also" section
- Link to source code

### Code Examples
- Show actual commands
- Include expected output
- Explain what happens
- Provide troubleshooting tips

## Support

- **Issues:** GitHub issues with `docs` label
- **Questions:** GitHub Discussions
- **Build Problems:** Check GitHub Actions logs

## Scripts

### `scripts/extract_help.py`
Extracts Click command help text and generates markdown documentation.

**Usage:**
```bash
python scripts/extract_help.py --output docs-site/commands/
```

### `scripts/generate_docs.py`
Generates structured documentation pages from README and existing docs.

**Usage:**
```bash
python scripts/generate_docs.py
```

### `scripts/generate_all_pages.sh`
Creates complete directory structure and page stubs.

**Usage:**
```bash
./scripts/generate_all_pages.sh
```

### `scripts/migrate_existing_docs.sh`
Migrates existing docs/ files to new structure.

**Usage:**
```bash
./scripts/migrate_existing_docs.sh
```

## Future Enhancements

### Pass 2: Clarity
- Expand examples with detailed explanations
- Add architecture diagrams
- Create workflow guides
- Add more cross-references

### Pass 3: Reality Check
- Test all command examples
- Validate all links
- Check consistency
- Final polish

### Additional Features
- Add search keywords
- Create comparison tables
- Add video tutorials
- Enable version selector
- Add PDF export

## Contributing

See [Contributing Guide](development/contributing.md) for details on:
- Documentation style guide
- Pull request process
- Review criteria
- Testing requirements

---

**Last Updated:** November 24, 2025
**Status:** Production Ready
**Version:** 0.3.2
