#!/bin/bash
# Generate man pages from clap CLI definitions.
# The completions subcommand handles shell completions; man pages
# require clap_mangen which is not currently a build dependency.
#
# To generate a basic man page from --help output:
#   help2man ./target/release/azlin > man/azlin.1
#
# Or install clap_mangen and add a build.rs to generate proper man pages.
set -euo pipefail

RUST="./target/release/azlin"

if [ ! -x "$RUST" ]; then
    echo "ERROR: $RUST not found. Run 'cargo build --release' first." >&2
    exit 1
fi

mkdir -p man/

if command -v help2man &> /dev/null; then
    help2man --no-info "$RUST" > man/azlin.1
    echo "Man page generated: man/azlin.1"
    echo "Install with: sudo cp man/azlin.1 /usr/local/share/man/man1/"
else
    echo "help2man not found. Generating minimal man page from --help."
    {
        echo ".TH AZLIN 1"
        echo ".SH NAME"
        echo "azlin \\- Azure VM fleet management CLI"
        echo ".SH SYNOPSIS"
        echo ".B azlin"
        echo "[\\fIcommand\\fR] [\\fIoptions\\fR]"
        echo ".SH DESCRIPTION"
        $RUST --help | sed 's/^/.PP\n/'
    } > man/azlin.1
    echo "Basic man page generated: man/azlin.1"
    echo "For better results, install help2man: sudo apt install help2man"
fi
