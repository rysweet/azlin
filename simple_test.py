#!/usr/bin/env python3
"""Simple test to debug error handling."""

import sys
import os

# Add src to path
sys.path.insert(0, 'src')

# Minimal imports
import click
from click.testing import CliRunner

# Try to import and test
try:
    from azlin.cli import main, bastion_group, AzlinGroup

    print(f"main class: {main.__class__.__name__}")
    print(f"bastion_group class: {bastion_group.__class__.__name__}")
    print(f"Is bastion_group an AzlinGroup subclass? {isinstance(bastion_group, AzlinGroup)}")
    print()

    runner = CliRunner()
    result = runner.invoke(main, ['bastion', 'configure', '--bastion-name', 'test'])

    print(f"Exit code: {result.exit_code}")
    print(f"Output length: {len(result.output)}")
    print(f"Has 'Error': {'Error' in result.output}")
    print(f"Has 'Missing': {'Missing' in result.output}")
    print(f"Has 'bastion': {'bastion' in result.output.lower()}")
    print()
    print("First 300 chars of output:")
    print(result.output[:300])

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
