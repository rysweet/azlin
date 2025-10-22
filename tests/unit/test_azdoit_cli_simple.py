"""TDD Tests for Issue #166: azdoit standalone CLI (Simplified).

These tests follow TDD principles and WILL FAIL until implementation is complete.
This version focuses on testable aspects without full module imports.

Design Requirements:
- Create azdoit_main() entry point in cli.py
- Extract _do_impl() shared implementation
- Add azdoit script to pyproject.toml
- Maintain backward compatibility with azlin do

Test Coverage:
1. azdoit_main() entry point exists
2. _do_impl() shared implementation exists
3. azdoit script defined in pyproject.toml
4. Both entry points have same signature
"""

import ast
import importlib.util
from pathlib import Path

import pytest


class TestAzdoitEntryPointExists:
    """Test that azdoit_main() entry point exists in cli.py (TDD: RED phase)."""

    @pytest.fixture
    def cli_module_path(self):
        """Get path to cli.py module."""
        return Path(__file__).parents[2] / "src" / "azlin" / "cli.py"

    @pytest.fixture
    def cli_ast(self, cli_module_path):
        """Parse cli.py AST for inspection without importing."""
        with open(cli_module_path) as f:
            return ast.parse(f.read())

    @pytest.fixture
    def function_names(self, cli_ast):
        """Extract all function names from cli.py."""
        return {node.name for node in ast.walk(cli_ast) if isinstance(node, ast.FunctionDef)}

    def test_azdoit_main_function_exists(self, function_names):
        """Test that azdoit_main() function exists in cli.py.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        assert (
            "azdoit_main" in function_names
        ), "azdoit_main() entry point function not found in cli.py"

    def test_do_impl_shared_function_exists(self, function_names):
        """Test that _do_impl() shared function exists in cli.py.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        assert (
            "_do_impl" in function_names
        ), "_do_impl() shared implementation function not found in cli.py"

    def test_do_command_still_exists(self, function_names):
        """Test that do() command function still exists (backward compatibility).

        GREEN PHASE: This should pass - do() already exists.
        """
        assert "do" in function_names, "do() command function must remain in cli.py"

    def test_main_function_exists(self, function_names):
        """Test that main() entry point still exists (backward compatibility).

        GREEN PHASE: This should pass - main() already exists.
        """
        assert "main" in function_names, "main() entry point must remain in cli.py"


class TestAzdoitFunctionSignatures:
    """Test that function signatures are correct (TDD: RED phase)."""

    @pytest.fixture
    def cli_module_path(self):
        """Get path to cli.py module."""
        return Path(__file__).parents[2] / "src" / "azlin" / "cli.py"

    @pytest.fixture
    def cli_ast(self, cli_module_path):
        """Parse cli.py AST for inspection."""
        with open(cli_module_path) as f:
            return ast.parse(f.read())

    @pytest.fixture
    def function_definitions(self, cli_ast):
        """Extract function definitions from cli.py."""
        return {
            node.name: node for node in ast.walk(cli_ast) if isinstance(node, ast.FunctionDef)
        }

    def test_azdoit_main_accepts_request_param(self, function_definitions):
        """Test that azdoit_main() accepts 'request' parameter.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        if "azdoit_main" not in function_definitions:
            pytest.skip("azdoit_main() not implemented yet")

        azdoit_func = function_definitions["azdoit_main"]
        param_names = [arg.arg for arg in azdoit_func.args.args]

        assert "request" in param_names, "azdoit_main() should accept 'request' parameter"

    def test_azdoit_main_accepts_common_flags(self, function_definitions):
        """Test that azdoit_main() accepts common CLI flags.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        if "azdoit_main" not in function_definitions:
            pytest.skip("azdoit_main() not implemented yet")

        azdoit_func = function_definitions["azdoit_main"]
        param_names = [arg.arg for arg in azdoit_func.args.args]

        # Should have at least some standard parameters
        expected_params = ["request", "dry_run", "yes"]
        for param in expected_params:
            assert (
                param in param_names
            ), f"azdoit_main() should accept '{param}' parameter like azlin do"

    def test_do_impl_has_required_params(self, function_definitions):
        """Test that _do_impl() has required parameters for shared logic.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        if "_do_impl" not in function_definitions:
            pytest.skip("_do_impl() not implemented yet")

        do_impl_func = function_definitions["_do_impl"]
        param_names = [arg.arg for arg in do_impl_func.args.args]

        # Should have core parameters needed for implementation
        required_params = ["request"]
        for param in required_params:
            assert param in param_names, f"_do_impl() must have '{param}' parameter"


class TestPyprojectConfiguration:
    """Test that pyproject.toml is correctly configured (TDD: RED phase)."""

    @pytest.fixture
    def pyproject_path(self):
        """Get path to pyproject.toml."""
        return Path(__file__).parents[2] / "pyproject.toml"

    def test_pyproject_exists(self, pyproject_path):
        """Test that pyproject.toml exists."""
        assert pyproject_path.exists(), "pyproject.toml not found"

    def test_azdoit_script_entry_defined(self, pyproject_path):
        """Test that azdoit script entry is defined in pyproject.toml.

        RED PHASE: This will fail - azdoit not in pyproject.toml yet.
        """
        # Read as text and search for azdoit entry
        content = pyproject_path.read_text()

        # Should have azdoit in [project.scripts] section
        assert (
            "azdoit = " in content or 'azdoit = "' in content
        ), "azdoit script entry not found in pyproject.toml"

    def test_azdoit_points_to_correct_entry_point(self, pyproject_path):
        """Test that azdoit points to azlin.cli:azdoit_main.

        RED PHASE: This will fail - entry point doesn't exist yet.
        """
        content = pyproject_path.read_text()

        # Should point to azlin.cli:azdoit_main
        assert (
            'azdoit = "azlin.cli:azdoit_main"' in content
            or "azdoit = 'azlin.cli:azdoit_main'" in content
        ), "azdoit should point to azlin.cli:azdoit_main"

    def test_azlin_script_still_exists(self, pyproject_path):
        """Test that azlin script still exists (backward compatibility).

        GREEN PHASE: This should pass - azlin already exists.
        """
        content = pyproject_path.read_text()

        # azlin entry should still exist
        assert "azlin = " in content, "azlin script entry must remain in pyproject.toml"
        assert (
            'azlin = "azlin.cli:main"' in content or "azlin = 'azlin.cli:main'" in content
        ), "azlin should still point to azlin.cli:main"


class TestFunctionDecorators:
    """Test that functions have appropriate Click decorators (TDD: RED phase)."""

    @pytest.fixture
    def cli_source(self):
        """Read cli.py source code."""
        cli_path = Path(__file__).parents[2] / "src" / "azlin" / "cli.py"
        with open(cli_path) as f:
            return f.read()

    def test_azdoit_main_has_click_decorators(self, cli_source):
        """Test that azdoit_main() is decorated as a Click command.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        # Look for function definition and decorators
        if "def azdoit_main(" not in cli_source:
            pytest.fail("azdoit_main() function not found in cli.py")

        # Extract the function and its decorators
        lines = cli_source.split("\n")
        azdoit_idx = None
        for i, line in enumerate(lines):
            if "def azdoit_main(" in line:
                azdoit_idx = i
                break

        assert azdoit_idx is not None, "Could not find azdoit_main() definition"

        # Check for Click decorators above the function
        decorators_section = "\n".join(lines[max(0, azdoit_idx - 20) : azdoit_idx])

        # Should have click.command or @click.command()
        assert (
            "@click.command" in decorators_section or "@main.command" in decorators_section
        ), "azdoit_main() should be a Click command"

        # Should have click.argument for REQUEST
        assert (
            "@click.argument" in decorators_section
        ), "azdoit_main() should have @click.argument decorator for REQUEST"

    def test_azdoit_main_has_same_options_as_do(self, cli_source):
        """Test that azdoit_main() has similar options to do() command.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        if "def azdoit_main(" not in cli_source:
            pytest.skip("azdoit_main() not implemented yet")

        # Extract decorators for both functions
        lines = cli_source.split("\n")

        # Find do() function decorators
        do_idx = None
        for i, line in enumerate(lines):
            if "def do(" in line:
                do_idx = i
                break

        assert do_idx is not None, "Could not find do() function"

        # Find azdoit_main() decorators
        azdoit_idx = None
        for i, line in enumerate(lines):
            if "def azdoit_main(" in line:
                azdoit_idx = i
                break

        do_decorators = "\n".join(lines[max(0, do_idx - 20) : do_idx])
        azdoit_decorators = "\n".join(lines[max(0, azdoit_idx - 20) : azdoit_idx])

        # Both should have --dry-run option
        if "--dry-run" in do_decorators:
            assert (
                "--dry-run" in azdoit_decorators
            ), "azdoit_main() should have --dry-run option like do()"

        # Both should have --yes/-y option
        if "--yes" in do_decorators:
            assert "--yes" in azdoit_decorators, "azdoit_main() should have --yes option like do()"


class TestCodeStructure:
    """Test code structure and refactoring (TDD: RED phase)."""

    @pytest.fixture
    def cli_source(self):
        """Read cli.py source code."""
        cli_path = Path(__file__).parents[2] / "src" / "azlin" / "cli.py"
        with open(cli_path) as f:
            return f.read()

    def test_do_impl_called_from_do_command(self, cli_source):
        """Test that do() command calls _do_impl().

        RED PHASE: This will fail - _do_impl doesn't exist yet.
        """
        if "def _do_impl(" not in cli_source:
            pytest.skip("_do_impl() not implemented yet")

        # Find do() function body
        lines = cli_source.split("\n")
        do_idx = None
        for i, line in enumerate(lines):
            if "def do(" in line:
                do_idx = i
                break

        assert do_idx is not None, "Could not find do() function"

        # Look for _do_impl call in next 200 lines (approximate function body)
        do_body = "\n".join(lines[do_idx : do_idx + 200])

        assert (
            "_do_impl(" in do_body
        ), "do() command should call _do_impl() for shared implementation"

    def test_azdoit_main_called_from_azdoit_main(self, cli_source):
        """Test that azdoit_main() calls _do_impl().

        RED PHASE: This will fail - functions don't exist yet.
        """
        if "def azdoit_main(" not in cli_source:
            pytest.skip("azdoit_main() not implemented yet")

        if "def _do_impl(" not in cli_source:
            pytest.skip("_do_impl() not implemented yet")

        # Find azdoit_main() function body
        lines = cli_source.split("\n")
        azdoit_idx = None
        for i, line in enumerate(lines):
            if "def azdoit_main(" in line:
                azdoit_idx = i
                break

        # Look for _do_impl call in next 200 lines
        azdoit_body = "\n".join(lines[azdoit_idx : azdoit_idx + 200])

        assert (
            "_do_impl(" in azdoit_body
        ), "azdoit_main() should call _do_impl() for shared implementation"

    def test_code_deduplication(self, cli_source):
        """Test that implementation is not duplicated between do() and azdoit_main().

        RED PHASE: This will pass once refactored.
        """
        if "def azdoit_main(" not in cli_source:
            pytest.skip("azdoit_main() not implemented yet")

        if "def _do_impl(" not in cli_source:
            pytest.skip("_do_impl() not implemented yet")

        # Both functions should be small if they delegate to _do_impl
        lines = cli_source.split("\n")

        # Find function lengths
        def get_function_length(func_name):
            start_idx = None
            for i, line in enumerate(lines):
                if f"def {func_name}(" in line:
                    start_idx = i
                    break

            if start_idx is None:
                return 0

            # Count lines until next function or end
            length = 0
            indent_level = len(lines[start_idx]) - len(lines[start_idx].lstrip())
            for line in lines[start_idx + 1 :]:
                if line.strip() and not line.startswith(" " * (indent_level + 1)):
                    break
                length += 1

            return length

        do_length = get_function_length("do")
        azdoit_length = get_function_length("azdoit_main")

        # If properly refactored, both should be relatively small (mostly just parameter handling)
        # This is a soft check - functions delegating to _do_impl should be < 30 lines
        if do_length > 0:
            assert (
                do_length < 50
            ), "do() should be small if it delegates to _do_impl() (found {} lines)".format(
                do_length
            )

        if azdoit_length > 0:
            assert (
                azdoit_length < 50
            ), "azdoit_main() should be small if it delegates to _do_impl() (found {} lines)".format(
                azdoit_length
            )


class TestDocumentation:
    """Test that functions have appropriate documentation (TDD: RED phase)."""

    @pytest.fixture
    def cli_source(self):
        """Read cli.py source code."""
        cli_path = Path(__file__).parents[2] / "src" / "azlin" / "cli.py"
        with open(cli_path) as f:
            return f.read()

    def test_azdoit_main_has_docstring(self, cli_source):
        """Test that azdoit_main() has a docstring.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        if "def azdoit_main(" not in cli_source:
            pytest.fail("azdoit_main() function not found")

        # Look for docstring after function definition
        lines = cli_source.split("\n")
        for i, line in enumerate(lines):
            if "def azdoit_main(" in line:
                # Check next few lines for docstring
                next_lines = "\n".join(lines[i : i + 10])
                assert '"""' in next_lines or "'''" in next_lines, "azdoit_main() should have a docstring"
                return

    def test_do_impl_has_docstring(self, cli_source):
        """Test that _do_impl() has a docstring.

        RED PHASE: This will fail - function doesn't exist yet.
        """
        if "def _do_impl(" not in cli_source:
            pytest.fail("_do_impl() function not found")

        # Look for docstring after function definition
        lines = cli_source.split("\n")
        for i, line in enumerate(lines):
            if "def _do_impl(" in line:
                # Check next few lines for docstring
                next_lines = "\n".join(lines[i : i + 10])
                assert (
                    '"""' in next_lines or "'''" in next_lines
                ), "_do_impl() should have a docstring"
                return
