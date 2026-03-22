"""Tests for CLI documentation subsystem — Issues #878, #879, #880.

These tests define the contract for the following changes:

    models.py       — adds DocumentationError(Exception)
    hasher.py       — encoding='utf-8' on all open() calls; FileNotFoundError →
                      return {}; JSONDecodeError → raise DocumentationError
    example_manager.py — propagate ValueError from _sanitize_command_name;
                         validate required 'command' field (raises DocumentationError);
                         encoding='utf-8' on all open() calls
    sync_manager.py — narrow except Exception → except DocumentationError;
                      encoding='utf-8' on write_text()
    extractor.py    — raise DocumentationError on parse failure (not return None)
    scripts/__init__.py — package marker (created separately)

All tests in this file will FAIL until DocumentationError exists in models.py
(the module-level import below raises ImportError until then).  Individual
tests will continue to fail for behavioural reasons until the full
implementation is in place.

Design spec refs:
    SEC-R-08  ValueError from _sanitize_command_name propagates (Issue #878)
    SEC-R-10  encoding='utf-8' on every open()/write_text() (Issue #879)
    SEC-R-11  'command' field check: 'command' not in data, not falsy test (Issue #880)
    SEC-R-12  except DocumentationError only — bugs must not be swallowed
    SEC-R-14  JSONDecodeError re-raised as DocumentationError (from e)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# This import will raise ImportError until DocumentationError is added to
# scripts/cli_documentation/models.py.  Every test in the file therefore
# fails during collection until the implementation is complete — that is the
# intended TDD behaviour.
# ---------------------------------------------------------------------------
from scripts.cli_documentation.models import (
    CLIArgument,
    CLIMetadata,
    CLIOption,
    CommandExample,
    DocumentationError,  # NEW — does not exist yet
)
from scripts.cli_documentation.example_manager import ExampleManager
from scripts.cli_documentation.hasher import CLIHasher
from scripts.cli_documentation.sync_manager import DocSyncManager
from scripts.cli_documentation.extractor import CLIExtractor


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_metadata(name: str = "test-cmd", full_path: str = "") -> CLIMetadata:
    """Return a minimal CLIMetadata for use in tests."""
    return CLIMetadata(
        name=name,
        full_path=full_path or name,
        help_text="A test command",
        description="Detailed description of the test command.",
        arguments=[CLIArgument(name="env", type="TEXT", required=True)],
        options=[CLIOption(names=["--verbose", "-v"], type="FLAG", is_flag=True)],
    )


def _write_yaml(path: Path, data: dict) -> None:
    """Write *data* as YAML to *path* using UTF-8."""
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")


# ===========================================================================
# GROUP 1 — DocumentationError (3 tests)
# ===========================================================================


class TestDocumentationError:
    """DocumentationError must be a typed domain exception in models.py."""

    def test_is_exception_subclass(self) -> None:
        """DocumentationError must inherit from Exception so it can be caught
        with 'except DocumentationError' or 'except Exception'."""
        assert issubclass(DocumentationError, Exception), (
            "DocumentationError must be a subclass of Exception"
        )

    def test_can_be_raised_with_message(self) -> None:
        """DocumentationError must accept a message string and expose it via str()."""
        msg = "corrupt JSON in .cli_doc_hashes.json"
        with pytest.raises(DocumentationError) as exc_info:
            raise DocumentationError(msg)
        assert msg in str(exc_info.value)

    def test_exported_in_models_all(self) -> None:
        """DocumentationError must be listed in models.__all__ so callers can
        do 'from scripts.cli_documentation.models import DocumentationError'."""
        import scripts.cli_documentation.models as models_module

        assert hasattr(models_module, "__all__"), "models.py must define __all__"
        assert "DocumentationError" in models_module.__all__, (
            "DocumentationError must be in models.__all__"
        )


# ===========================================================================
# GROUP 2 — CLIHasher JSON error handling (9 tests)
# ===========================================================================


class TestCLIHasherErrorHandling:
    """CLIHasher must distinguish FileNotFoundError from JSONDecodeError and
    must use encoding='utf-8' on every file operation (Issues #879, #880)."""

    def test_corrupt_json_raises_documentation_error(self, tmp_path: Path) -> None:
        """When the hash file contains malformed JSON, _load_hashes() must
        raise DocumentationError (not silently return an empty dict).

        Rationale: corrupt hash files indicate storage problems; swallowing
        the error causes silent full-regeneration on every run.
        """
        hash_file = tmp_path / "hashes.json"
        hash_file.write_text("{ this is not valid json }", encoding="utf-8")

        with pytest.raises(DocumentationError):
            CLIHasher(str(hash_file))

    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """When the hash file does not exist, CLIHasher must initialise with
        an empty hash dict — this is normal first-run behaviour."""
        hash_file = tmp_path / "does_not_exist.json"
        hasher = CLIHasher(str(hash_file))
        assert hasher._hashes == {}, (
            "Missing hash file must yield an empty hash dict, not an exception"
        )

    def test_file_not_found_does_not_raise(self, tmp_path: Path) -> None:
        """FileNotFoundError during load must NOT raise DocumentationError.
        It must be treated as an empty store (normal first-run)."""
        hash_file = tmp_path / "nonexistent.json"
        # Must not raise any exception
        hasher = CLIHasher(str(hash_file))
        assert isinstance(hasher._hashes, dict)

    def test_json_decode_error_chains_to_documentation_error(
        self, tmp_path: Path
    ) -> None:
        """JSONDecodeError must be re-raised as DocumentationError with the
        original exception chained ('raise DocumentationError(...) from e').

        SEC-R-14: chaining preserves the original traceback for debugging.
        """
        hash_file = tmp_path / "bad.json"
        hash_file.write_text("[[[invalid", encoding="utf-8")

        with pytest.raises(DocumentationError) as exc_info:
            CLIHasher(str(hash_file))

        assert exc_info.value.__cause__ is not None, (
            "DocumentationError must chain the original JSONDecodeError via 'from e'"
        )
        assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)

    def test_save_uses_utf8_encoding(self, tmp_path: Path) -> None:
        """save_hashes() must open the output file with encoding='utf-8'.

        SEC-R-10: on systems where the default locale is not UTF-8
        (e.g., Windows cp1252), omitting encoding causes silent data corruption.
        """
        hash_file = tmp_path / "hashes.json"
        hasher = CLIHasher(str(hash_file))
        metadata = _make_metadata()
        hasher.update_hash(metadata)

        # Patch open() and verify encoding='utf-8' is passed
        original_open = open

        calls_seen: list = []

        def capturing_open(file, mode="r", **kwargs):
            calls_seen.append((str(file), mode, kwargs))
            return original_open(file, mode, **kwargs)

        with patch("builtins.open", side_effect=capturing_open):
            hasher.save_hashes()

        write_calls = [c for c in calls_seen if "w" in c[1]]
        assert write_calls, "save_hashes() must call open() in write mode"
        for _, _, kwargs in write_calls:
            assert kwargs.get("encoding") == "utf-8", (
                f"save_hashes() open() call missing encoding='utf-8': {kwargs}"
            )

    def test_load_handles_utf8_content(self, tmp_path: Path) -> None:
        """_load_hashes() must correctly read a UTF-8 encoded hash file."""
        hash_file = tmp_path / "hashes.json"
        content = {"café": "abc123", "naïve": "def456"}
        hash_file.write_text(json.dumps(content), encoding="utf-8")

        hasher = CLIHasher(str(hash_file))
        assert hasher._hashes == content

    def test_unicode_hash_roundtrip(self, tmp_path: Path) -> None:
        """A command with Unicode in its help text must survive a
        save→load round-trip with identical hash values."""
        hash_file = tmp_path / "hashes.json"
        hasher = CLIHasher(str(hash_file))

        meta = CLIMetadata(
            name="café",
            full_path="café",
            help_text="Manages the café ☕ resources",
            description="Détails complets pour café.",
        )
        hasher.update_hash(meta)
        original_hash = hasher._hashes["café"]
        hasher.save_hashes()

        # Reload from disk
        hasher2 = CLIHasher(str(hash_file))
        assert hasher2._hashes.get("café") == original_hash, (
            "Hash must survive UTF-8 save/load round-trip"
        )

    def test_os_error_on_save_raises_documentation_error(self, tmp_path: Path) -> None:
        """If open() raises OSError during save_hashes(), the error must
        be re-raised as DocumentationError (not silently return False).

        Rationale: a failure to persist hashes means the next run will do
        a full regeneration — this should be surfaced, not swallowed.
        """
        hash_file = tmp_path / "hashes.json"
        hasher = CLIHasher(str(hash_file))
        hasher.update_hash(_make_metadata())

        with patch("builtins.open", side_effect=OSError("disk full")):
            with pytest.raises(DocumentationError):
                hasher.save_hashes()

    def test_valid_json_loads_correctly(self, tmp_path: Path) -> None:
        """A well-formed hash file must be loaded into _hashes without error."""
        data = {"mount": "a" * 64, "list": "b" * 64}
        hash_file = tmp_path / "hashes.json"
        hash_file.write_text(json.dumps(data), encoding="utf-8")

        hasher = CLIHasher(str(hash_file))
        assert hasher._hashes == data


# ===========================================================================
# GROUP 3 — ExampleManager encoding and validation (16 tests)
# ===========================================================================


class TestExampleManagerValidation:
    """ExampleManager must validate the 'command' field, propagate ValueError,
    and use encoding='utf-8' on all file operations (Issues #878, #879, #880)."""

    # ------------------------------------------------------------------ #
    # 'command' field validation — SEC-R-11                               #
    # ------------------------------------------------------------------ #

    def test_missing_command_field_raises_documentation_error(
        self, tmp_path: Path
    ) -> None:
        """_load_from_file() must raise DocumentationError when an example
        entry is missing the required 'command' field.

        SEC-R-11: each CommandExample in the examples list must have a
        non-empty 'command' string; absent key must raise DocumentationError.
        """
        yaml_file = tmp_path / "mount.yaml"
        _write_yaml(
            yaml_file,
            {
                "command": "mount",  # top-level command key is present and valid
                "examples": [
                    # 'command' key intentionally absent from this example entry
                    {"title": "Basic", "description": "test"}
                ],
            },
        )

        manager = ExampleManager(str(tmp_path))
        with pytest.raises(DocumentationError, match="command"):
            manager._load_from_file(yaml_file)

    def test_empty_command_field_raises_documentation_error(
        self, tmp_path: Path
    ) -> None:
        """_load_from_file() must raise DocumentationError when an example's
        'command' field is an empty string.

        SEC-R-11: empty string '' is a distinct invalid state that must be
        caught (not just missing keys).
        """
        yaml_file = tmp_path / "mount.yaml"
        _write_yaml(
            yaml_file,
            {
                "command": "mount",
                "examples": [
                    # 'command' present but empty string — invalid
                    {"title": "Basic", "description": "test", "command": ""}
                ],
            },
        )

        manager = ExampleManager(str(tmp_path))
        with pytest.raises(DocumentationError):
            manager._load_from_file(yaml_file)

    def test_none_command_field_raises_documentation_error(
        self, tmp_path: Path
    ) -> None:
        """_load_from_file() must raise DocumentationError when an example's
        'command' field is explicitly None."""
        yaml_file = tmp_path / "mount.yaml"
        _write_yaml(
            yaml_file,
            {
                "command": "mount",
                "examples": [
                    # 'command' present but None — invalid
                    {"title": "Basic", "description": "test", "command": None}
                ],
            },
        )

        manager = ExampleManager(str(tmp_path))
        with pytest.raises(DocumentationError):
            manager._load_from_file(yaml_file)

    def test_present_command_field_succeeds(self, tmp_path: Path) -> None:
        """When 'command' is present and non-empty, _load_from_file() must
        return a list of CommandExample objects without raising."""
        yaml_file = tmp_path / "mount.yaml"
        _write_yaml(
            yaml_file,
            {
                "command": "mount",
                "examples": [
                    {
                        "title": "Basic mount",
                        "description": "Mount a storage volume",
                        "command": "azlin mount my-storage",
                        "output": "Mounted successfully",
                    }
                ],
            },
        )

        manager = ExampleManager(str(tmp_path))
        examples = manager._load_from_file(yaml_file)

        assert len(examples) == 1
        assert examples[0].title == "Basic mount"
        assert examples[0].command == "azlin mount my-storage"

    # ------------------------------------------------------------------ #
    # Encoding — SEC-R-10                                                 #
    # ------------------------------------------------------------------ #

    def test_load_uses_utf8_encoding(self, tmp_path: Path) -> None:
        """_load_from_file() must open YAML files with encoding='utf-8'.

        SEC-R-10: on Windows with a non-UTF-8 locale, omitting encoding
        causes silent data corruption that invalidates SHA-256 hashes.
        """
        yaml_file = tmp_path / "mount.yaml"
        _write_yaml(yaml_file, {"command": "mount", "examples": []})

        manager = ExampleManager(str(tmp_path))
        original_open = open
        calls_seen: list = []

        def capturing_open(file, mode="r", **kwargs):
            calls_seen.append((str(file), mode, kwargs))
            return original_open(file, mode, **kwargs)

        with patch("builtins.open", side_effect=capturing_open):
            manager._load_from_file(yaml_file)

        read_calls = [c for c in calls_seen if "r" in c[1] or ("w" not in c[1])]
        assert read_calls, "_load_from_file must call open()"
        for _, _, kwargs in read_calls:
            assert kwargs.get("encoding") == "utf-8", (
                f"_load_from_file open() call missing encoding='utf-8': {kwargs}"
            )

    def test_save_uses_utf8_encoding(self, tmp_path: Path) -> None:
        """save_examples() must open the output YAML file with encoding='utf-8'."""
        manager = ExampleManager(str(tmp_path))
        examples = [
            CommandExample(
                title="Basic",
                description="A test example",
                command="azlin mount x",
            )
        ]

        original_open = open
        calls_seen: list = []

        def capturing_open(file, mode="r", **kwargs):
            calls_seen.append((str(file), mode, kwargs))
            return original_open(file, mode, **kwargs)

        with patch("builtins.open", side_effect=capturing_open):
            manager.save_examples("mount", examples)

        write_calls = [c for c in calls_seen if "w" in c[1]]
        assert write_calls, "save_examples must call open() in write mode"
        for _, _, kwargs in write_calls:
            assert kwargs.get("encoding") == "utf-8", (
                f"save_examples open() call missing encoding='utf-8': {kwargs}"
            )

    def test_unicode_roundtrip(self, tmp_path: Path) -> None:
        """A command example with Unicode characters in its fields must survive
        a save_examples → load_examples round-trip unchanged.

        SEC-R-10: encoding='utf-8' is required so multi-byte Unicode code
        points are not corrupted on systems with non-UTF-8 default encodings.

        Note: command *names* must be ASCII (alphanumeric/dash/underscore per
        _sanitize_command_name). Only the example *content* can be Unicode.
        """
        manager = ExampleManager(str(tmp_path))
        examples = [
            CommandExample(
                title="Créer un café ☕",
                description="Démonstration de l'encodage UTF-8",
                command="azlin utf8-cmd --option valeur",  # command string (Unicode OK)
                output="Résultat: ✓",
            )
        ]
        # Command name must be ASCII-safe; use a plain ASCII name
        assert manager.save_examples("utf8-cmd", examples), (
            "save_examples must return True"
        )

        loaded = manager.load_examples("utf8-cmd")
        assert len(loaded) == 1
        assert loaded[0].title == "Créer un café ☕"
        assert loaded[0].output == "Résultat: ✓"

    # ------------------------------------------------------------------ #
    # ValueError propagation — SEC-R-08 / Issue #878                     #
    # ------------------------------------------------------------------ #

    def test_load_examples_propagates_value_error(self, tmp_path: Path) -> None:
        """load_examples() must NOT catch ValueError from _sanitize_command_name.

        SEC-R-08: the current code silently returns [] when the command name is
        invalid; after the fix, ValueError propagates to the caller so the
        invalid name is surfaced immediately.
        """
        manager = ExampleManager(str(tmp_path))
        # '../etc/passwd' contains '/' which is not in [a-zA-Z0-9_-]
        with pytest.raises(ValueError):
            manager.load_examples("../etc/passwd")

    def test_sanitize_traversal_raises_value_error(self) -> None:
        """_sanitize_command_name must raise ValueError for names with path
        separator characters or other invalid characters."""
        manager = ExampleManager("/tmp")
        invalid_names = [
            "../etc/passwd",
            "foo/bar",
            "cmd; rm -rf /",
            "name with spaces",
            "name\x00null",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError, match="Invalid command name"):
                manager._sanitize_command_name(name)

    def test_sanitize_valid_name_passes(self) -> None:
        """_sanitize_command_name must return valid names unchanged."""
        manager = ExampleManager("/tmp")
        valid_names = ["mount", "list-vms", "create_vm", "VM123", "a-b-c_1"]
        for name in valid_names:
            result = manager._sanitize_command_name(name)
            assert result == name, f"Sanitize should pass through valid name '{name}'"

    # ------------------------------------------------------------------ #
    # YAML safety                                                         #
    # ------------------------------------------------------------------ #

    def test_yaml_safe_load_rejects_python_objects(self, tmp_path: Path) -> None:
        """yaml.safe_load() must reject !!python/object tags.

        This confirms yaml.safe_load() is used (not yaml.load()) so that
        YAML deserialization cannot execute arbitrary Python code.
        """
        malicious_yaml = """
command: mount
examples:
  - !!python/object/apply:os.system ["echo pwned"]
"""
        yaml_file = tmp_path / "mount.yaml"
        yaml_file.write_text(malicious_yaml, encoding="utf-8")

        manager = ExampleManager(str(tmp_path))
        # safe_load raises yaml.constructor.ConstructorError or DocumentationError
        with pytest.raises((yaml.constructor.ConstructorError, DocumentationError)):
            manager._load_from_file(yaml_file)

    def test_corrupt_yaml_raises_documentation_error(self, tmp_path: Path) -> None:
        """_load_from_file() must raise DocumentationError when the YAML
        cannot be parsed (malformed syntax), rather than silently returning [].

        This surfaces storage corruption or incomplete writes early.
        """
        yaml_file = tmp_path / "mount.yaml"
        yaml_file.write_text(": broken: yaml: content: [", encoding="utf-8")

        manager = ExampleManager(str(tmp_path))
        with pytest.raises(DocumentationError):
            manager._load_from_file(yaml_file)

    # ------------------------------------------------------------------ #
    # Graceful handling for missing / empty files                         #
    # ------------------------------------------------------------------ #

    def test_nonexistent_file_returns_empty_list(self, tmp_path: Path) -> None:
        """_load_from_file() with a non-existent path must return []
        (FileNotFoundError is treated as 'no examples')."""
        yaml_file = tmp_path / "does_not_exist.yaml"
        manager = ExampleManager(str(tmp_path))
        # Should not raise; returns empty list
        result = manager._load_from_file(yaml_file)
        assert result == []

    def test_no_examples_key_returns_empty_list(self, tmp_path: Path) -> None:
        """A valid YAML file with a 'command' key but no 'examples' key
        must return an empty list without raising."""
        yaml_file = tmp_path / "mount.yaml"
        _write_yaml(yaml_file, {"command": "mount", "metadata": {"version": 1}})

        manager = ExampleManager(str(tmp_path))
        result = manager._load_from_file(yaml_file)
        assert result == []

    def test_save_invalid_command_name_raises_value_error(self, tmp_path: Path) -> None:
        """save_examples() must raise ValueError when the command name
        fails _sanitize_command_name validation."""
        manager = ExampleManager(str(tmp_path))
        examples = [CommandExample(title="t", description="d", command="azlin x")]
        with pytest.raises(ValueError):
            manager.save_examples("../bad", examples)

    def test_load_all_from_empty_dir_returns_empty_dict(self, tmp_path: Path) -> None:
        """load_all_examples() on an empty directory must return {}."""
        empty_dir = tmp_path / "examples"
        empty_dir.mkdir()
        manager = ExampleManager(str(empty_dir))
        result = manager.load_all_examples()
        assert result == {}


# ===========================================================================
# GROUP 4 — DocSyncManager exception narrowing and encoding (8 tests)
# ===========================================================================


class TestDocSyncManagerExceptionNarrowing:
    """DocSyncManager.sync_command() must catch DocumentationError only;
    unexpected exceptions (AttributeError, TypeError, etc.) must propagate.
    write_text() must use encoding='utf-8'. (Issue #879, SEC-R-12)"""

    def test_documentation_error_caught_in_sync_command(self, tmp_path: Path) -> None:
        """When example_manager.load_examples() raises DocumentationError,
        sync_command() must catch it and return a SyncResult with error set."""
        manager = DocSyncManager(output_dir=str(tmp_path))
        metadata = _make_metadata()

        with patch.object(
            manager.example_manager,
            "load_examples",
            side_effect=DocumentationError("corrupt YAML"),
        ):
            result = manager.sync_command(metadata, validate=False)

        assert not result.success, (
            "SyncResult.success must be False on DocumentationError"
        )
        assert result.error is not None
        assert "corrupt YAML" in result.error

    def test_attribute_error_propagates(self, tmp_path: Path) -> None:
        """AttributeError inside sync_command() must NOT be caught.

        SEC-R-12: AttributeError indicates a programming bug; swallowing it
        hides defects and makes debugging impossible.
        """
        manager = DocSyncManager(output_dir=str(tmp_path))
        metadata = _make_metadata()

        with patch.object(
            manager.example_manager,
            "load_examples",
            side_effect=AttributeError("unexpected bug"),
        ):
            with pytest.raises(AttributeError):
                manager.sync_command(metadata, validate=False)

    def test_type_error_propagates(self, tmp_path: Path) -> None:
        """TypeError inside sync_command() must NOT be caught.

        SEC-R-12: unexpected exception types must propagate to expose bugs.
        """
        manager = DocSyncManager(output_dir=str(tmp_path))
        metadata = _make_metadata()

        with patch.object(
            manager.generator,
            "generate",
            side_effect=TypeError("wrong type"),
        ):
            with patch.object(
                manager.example_manager, "load_examples", return_value=[]
            ):
                with pytest.raises(TypeError):
                    manager.sync_command(metadata, validate=False)

    def test_write_text_uses_utf8(self, tmp_path: Path) -> None:
        """The output markdown file must be written with encoding='utf-8'.

        SEC-R-10: write_text() without encoding uses the system default,
        which on Windows is cp1252, silently corrupting non-ASCII content.
        """
        manager = DocSyncManager(output_dir=str(tmp_path))
        metadata = _make_metadata()

        write_text_calls: list = []
        original_write_text = Path.write_text

        def capturing_write_text(self_path, data, **kwargs):
            write_text_calls.append((str(self_path), kwargs))
            return original_write_text(self_path, data, **kwargs)

        with patch.object(manager.example_manager, "load_examples", return_value=[]):
            with patch.object(
                manager.generator, "generate", return_value="# test\n## Usage\n"
            ):
                with patch.object(Path, "write_text", capturing_write_text):
                    manager.sync_command(metadata, validate=False)

        assert write_text_calls, "sync_command must call write_text()"
        for path_str, kwargs in write_text_calls:
            assert kwargs.get("encoding") == "utf-8", (
                f"write_text() for '{path_str}' missing encoding='utf-8': {kwargs}"
            )

    def test_get_output_path_simple_command(self, tmp_path: Path) -> None:
        """Simple (non-nested) command names yield output_dir/<name>.md."""
        manager = DocSyncManager(output_dir=str(tmp_path))
        metadata = _make_metadata(name="list", full_path="list")
        output_path = manager._get_output_path(metadata)
        assert output_path == tmp_path / "list.md"

    def test_get_output_path_traversal_rejected(self, tmp_path: Path) -> None:
        """Path components with non-alnum/dash/underscore chars must raise ValueError."""
        manager = DocSyncManager(output_dir=str(tmp_path))
        metadata = _make_metadata(name="../evil", full_path="../evil")
        with pytest.raises(ValueError):
            manager._get_output_path(metadata)

    def test_get_output_path_nested_command(self, tmp_path: Path) -> None:
        """Nested commands (space-separated full_path) yield a subdirectory."""
        manager = DocSyncManager(output_dir=str(tmp_path))
        metadata = _make_metadata(name="mount", full_path="storage mount")
        output_path = manager._get_output_path(metadata)
        assert output_path == tmp_path / "storage" / "mount.md"

    def test_sync_result_has_error_on_documentation_error(self, tmp_path: Path) -> None:
        """SyncResult.error must contain the DocumentationError message and
        SyncResult.success must be False when a DocumentationError is raised."""
        manager = DocSyncManager(output_dir=str(tmp_path))
        metadata = _make_metadata()

        error_msg = "hash file is corrupt"
        with patch.object(
            manager.example_manager,
            "load_examples",
            side_effect=DocumentationError(error_msg),
        ):
            result = manager.sync_command(metadata, validate=False)

        assert result.success is False
        assert error_msg in (result.error or ""), (
            "SyncResult.error must contain the DocumentationError message"
        )


# ===========================================================================
# GROUP 5 — CLIExtractor whitelist and DocumentationError (5 tests)
# ===========================================================================


class TestCLIExtractorSecurity:
    """CLIExtractor must keep ALLOWED_MODULES unchanged and raise
    DocumentationError on parse failure instead of silently returning None."""

    def test_allowed_modules_unchanged(self) -> None:
        """The ALLOWED_MODULES whitelist must contain exactly the three entries
        defined in the original security review.

        SEC-R-13: new modules must be explicitly reviewed before addition.
        """
        expected = {"azlin.cli", "azlin.storage", "azlin.context"}
        actual = set(CLIExtractor.ALLOWED_MODULES)
        assert actual == expected, (
            f"ALLOWED_MODULES changed unexpectedly.\n"
            f"  Expected: {sorted(expected)}\n"
            f"  Actual:   {sorted(actual)}"
        )

    def test_unlisted_module_rejected(self) -> None:
        """extract_command() must return None (with a warning) when the module
        path is not in ALLOWED_MODULES — this prevents arbitrary code execution."""
        extractor = CLIExtractor()
        result = extractor.extract_command("os.path", "join")
        assert result is None, (
            "Modules not in ALLOWED_MODULES must be rejected (return None)"
        )

    def test_raises_documentation_error_on_parse_failure(self) -> None:
        """When _extract_from_click_command fails with a runtime error,
        CLIExtractor must raise DocumentationError (not silently return None).

        This change makes parse failures visible so they can be fixed,
        rather than generating missing documentation silently.

        The mock triggers the failure via command.params (accessed inside the
        try block by _extract_arguments/_extract_options), so the error is
        caught by the except clause and re-raised as DocumentationError.
        The mock uses a plain name attribute so getattr(..., "name", "unknown")
        in the except handler does not also raise.
        """
        import click

        extractor = CLIExtractor()

        # Mock a Click command where .params raises RuntimeError inside the try
        # block (accessed by _extract_arguments / _extract_options), while
        # .name is a plain string so the except handler can log the command name.
        mock_cmd = MagicMock(spec=click.Command)
        mock_cmd.name = "broken-cmd"
        mock_cmd.help = "help text"
        mock_cmd.callback = None
        type(mock_cmd).params = PropertyMock(side_effect=RuntimeError("corrupt params"))

        with pytest.raises(DocumentationError):
            extractor._extract_from_click_command(mock_cmd)

    def test_missing_command_returns_none_gracefully(self) -> None:
        """extract_command() must return None (not raise) when the named
        attribute exists in the module but is not a Click.Command instance.

        'Not found' is normal (returns None); parse / import failure is an
        error (raises DocumentationError) — these two cases are distinct.
        """

        extractor = CLIExtractor()

        # Mock the module so importlib.import_module succeeds, but the attribute
        # is not a Click.Command instance (simulating a missing command).
        mock_module = MagicMock()
        mock_module.nonexistent_cmd = "not_a_click_command"  # wrong type

        with patch("importlib.import_module", return_value=mock_module):
            result = extractor.extract_command("azlin.cli", "nonexistent_cmd")

        assert result is None, (
            "extract_command must return None when the attribute exists "
            "but is not a Click.Command (command not found — not an error)"
        )

    def test_yaml_load_not_used_in_source(self) -> None:
        """extractor.py must not call yaml.load() (only yaml.safe_load() is
        allowed).  This is enforced by inspecting the source file at test time.

        SEC-R-09: a CI grep check prevents regression; this test provides
        the same guarantee within the pytest suite.
        """
        import inspect
        import scripts.cli_documentation.extractor as extractor_module

        try:
            source = inspect.getsource(extractor_module)
        except OSError:
            pytest.skip("Source not available for inspection")

        # Bare yaml.load( calls (not yaml.safe_load) are forbidden
        import re

        # Match 'yaml.load(' but not 'yaml.safe_load('
        forbidden = re.findall(r"\byaml\.load\s*\(", source)
        assert not forbidden, (
            "extractor.py must not call yaml.load() — use yaml.safe_load() only. "
            f"Found: {forbidden}"
        )
