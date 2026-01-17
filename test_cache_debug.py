#!/usr/bin/env python3
"""Test script to debug cache not working issue."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from azlin.cache.vm_list_cache import VMListCache


def test_cache_persistence():
    """Test if cache actually persists to disk."""
    print("Testing VMListCache persistence...")

    cache_file = Path.home() / ".azlin" / "vm_list_cache.json"
    print(f"Cache file location: {cache_file}")

    # Clear cache to start fresh
    if cache_file.exists():
        cache_file.unlink()
        print("✓ Cleared existing cache")

    # Create cache instance and save some data
    cache1 = VMListCache()

    test_immutable = {
        "name": "test-vm",
        "location": "westus2",
        "vm_size": "Standard_D2s_v3",
        "os_type": "Linux",
    }

    test_mutable = {
        "power_state": "VM running",
        "public_ip": "1.2.3.4",
        "private_ip": "10.0.0.4",
    }

    print("\n1. Setting cache entry...")
    cache1.set_full("test-vm", "test-rg", test_immutable, test_mutable)
    print("✓ Cache entry set")

    # Check if file was created
    if cache_file.exists():
        print(f"✓ Cache file created: {cache_file}")
        print(f"  File size: {cache_file.stat().st_size} bytes")
    else:
        print("✗ ERROR: Cache file NOT created!")
        return False

    # Create NEW cache instance (simulates new CLI run)
    print("\n2. Creating new cache instance (simulates new CLI run)...")
    cache2 = VMListCache()

    # Try to get the entry
    print("3. Getting cache entry...")
    entry = cache2.get("test-vm", "test-rg")

    if entry:
        print("✓ Cache hit! Entry found")
        print(f"  VM name: {entry.vm_name}")
        print(f"  Resource group: {entry.resource_group}")
        print(f"  Power state: {entry.mutable_data.get('power_state')}")
        print(f"  Immutable expired: {entry.is_immutable_expired(cache2.immutable_ttl)}")
        print(f"  Mutable expired: {entry.is_mutable_expired(cache2.mutable_ttl)}")
        return True
    print("✗ ERROR: Cache miss! Entry not found")
    print(f"  Cache file exists: {cache_file.exists()}")
    if cache_file.exists():
        import json

        with open(cache_file) as f:
            data = json.load(f)
        print(f"  Cache file contents: {json.dumps(data, indent=2)}")
    return False


if __name__ == "__main__":
    success = test_cache_persistence()
    sys.exit(0 if success else 1)
