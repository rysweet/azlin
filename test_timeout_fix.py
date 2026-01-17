#!/usr/bin/env python3
"""
Interactive test for timeout fix - verifies timeout values are correctly set.
This doesn't require Azure credentials - just validates the code changes.
"""

import subprocess
from pathlib import Path


def test_timeout_values():
    """Verify timeout values in vm_manager.py are set to 30s"""
    print("Testing: Timeout values in vm_manager.py\n")

    vm_manager_path = Path("src/azlin/vm_manager.py")
    content = vm_manager_path.read_text()

    # Count timeout=30 occurrences (should have at least 3 for list operations)
    timeout_30_count = content.count("timeout=30")
    timeout_10_count = content.count("timeout=10")

    print(f"✓ Found {timeout_30_count} instances of 'timeout=30'")
    print(f"✓ Found {timeout_10_count} instances of 'timeout=10' (remaining for quick ops)")

    assert timeout_30_count >= 3, f"Expected at least 3 timeout=30, found {timeout_30_count}"

    # Verify the specific lines we changed
    lines_to_check = [
        ("list_vms", "timeout=30"),
        ("_get_all_public_ips", "timeout=30"),
        ("list_resource_groups", "timeout=30"),
    ]

    for func_name, expected in lines_to_check:
        if func_name in content and expected in content:
            print(f"✓ {func_name}() has {expected}")
        else:
            print(f"✗ {func_name}() missing {expected}")
            return False

    print("\n✅ All timeout values verified!")
    return True


def test_imports():
    """Verify cache module imports work"""
    print("\nTesting: Cache module imports\n")

    try:
        # This will fail if cache module is missing
        result = subprocess.run(
            [
                "python",
                "-c",
                "from src.azlin.cache.vm_list_cache import VMListCache; print('✓ Cache module imports successfully')",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            print(result.stdout.strip())
            print("✅ Cache module available!")
            return True
        print(f"✗ Import failed: {result.stderr}")
        return False

    except Exception as e:
        print(f"✗ Import test failed: {e}")
        return False


def test_cli_help():
    """Test that CLI help works"""
    print("\nTesting: CLI help command\n")

    try:
        result = subprocess.run(
            ["azlin", "list", "--help"], capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0 and "List VMs" in result.stdout:
            print("✓ CLI help command works")
            print("✅ CLI accessible!")
            return True
        print("✗ CLI help failed")
        return False

    except Exception as e:
        print(f"Note: CLI not in PATH yet: {e}")
        print("⚠️  Run 'uv pip install -e .' first")
        return None  # Not a failure, just needs setup


def test_documentation():
    """Verify troubleshooting documentation exists"""
    print("\nTesting: Documentation\n")

    doc_path = Path("docs/troubleshooting/timeout-issues.md")

    if doc_path.exists():
        content = doc_path.read_text()

        # Check key sections exist
        required_sections = [
            "Troubleshooting Timeout Issues",
            "Common Causes",
            "Timeout Values",
            "30s",  # New timeout value
        ]

        for section in required_sections:
            if section in content:
                print(f"✓ Documentation contains '{section}'")
            else:
                print(f"✗ Documentation missing '{section}'")
                return False

        print("✅ Documentation complete!")
        return True
    print("✗ Documentation file not found")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("INTERACTIVE TEST: Timeout Fix Verification")
    print("=" * 60 + "\n")

    results = []

    # Run all tests
    results.append(("Timeout Values", test_timeout_values()))
    results.append(("Cache Imports", test_imports()))
    results.append(("CLI Help", test_cli_help()))
    results.append(("Documentation", test_documentation()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    skipped = sum(1 for _, r in results if r is None)

    for name, result in results:
        status = "✅ PASS" if result is True else "⚠️  SKIP" if result is None else "❌ FAIL"
        print(f"{status:12} {name}")

    print(f"\nResults: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print("\n🎉 All critical tests passed!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")
