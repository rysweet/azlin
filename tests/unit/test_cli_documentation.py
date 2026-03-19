"""Tests for scripts/cli_documentation — issues #878, #879, #880.

Covers:
- Corrupt-file scenario raises DocumentationError instead of silently returning empty
- UTF-8 round-trip for non-ASCII content in both hasher and example_manager
"""

from pathlib import Path

import pytest
import yaml

from scripts.cli_documentation.example_manager import ExampleManager
from scripts.cli_documentation.hasher import CLIHasher
from scripts.cli_documentation.models import (
    ChangeSet,
    CommandExample,
    DocumentationError,
)
from scripts.cli_documentation.models import (
    CLIMetadata as _CLIMetadata,
)  # used in helpers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_valid_hash_file(path: Path) -> None:
    """Write a minimal valid JSON hash file."""
    path.write_text('{"cmd": "abc123"}', encoding="utf-8")


def make_corrupt_hash_file(path: Path) -> None:
    """Write an invalid JSON hash file."""
    path.write_text("this is not valid JSON }{", encoding="utf-8")


def make_valid_yaml_file(path: Path, title: str = "Example") -> None:
    """Write a minimal valid YAML examples file."""
    data = {
        "command": "test",
        "examples": [
            {
                "title": title,
                "description": "desc",
                "command": "azlin test",
                "output": None,
            }
        ],
    }
    path.write_text(yaml.dump(data), encoding="utf-8")


def make_corrupt_yaml_file(path: Path) -> None:
    """Write an invalid YAML file."""
    path.write_text("key: [unclosed bracket", encoding="utf-8")


# ---------------------------------------------------------------------------
# Issue #878 — error-swallowing: hasher
# ---------------------------------------------------------------------------


class TestHasherCorruptFile:
    """CLIHasher raises DocumentationError on corrupt hash file (issue #878)."""

    def test_load_hashes_raises_on_corrupt_json(self, tmp_path):
        """_load_hashes raises DocumentationError when JSON is invalid."""
        hash_file = tmp_path / ".cli_doc_hashes.json"
        make_corrupt_hash_file(hash_file)

        with pytest.raises(DocumentationError, match="Failed to load hashes"):
            CLIHasher(hash_file=str(hash_file))

    def test_load_hashes_succeeds_when_file_missing(self, tmp_path):
        """_load_hashes returns empty dict silently when file is absent."""
        hash_file = tmp_path / "nonexistent.json"
        hasher = CLIHasher(hash_file=str(hash_file))
        assert hasher._hashes == {}

    def test_save_hashes_raises_on_unwritable_path(self, tmp_path):
        """save_hashes raises DocumentationError when target path is unwritable."""
        hash_file = tmp_path / ".cli_doc_hashes.json"
        hasher = CLIHasher(hash_file=str(hash_file))

        # Make the directory read-only so write fails
        tmp_path.chmod(0o555)
        try:
            with pytest.raises(DocumentationError, match="Failed to save hashes"):
                hasher.save_hashes()
        finally:
            tmp_path.chmod(0o755)  # restore so pytest cleanup works


# ---------------------------------------------------------------------------
# Issue #878 — error-swallowing: example_manager
# ---------------------------------------------------------------------------


class TestExampleManagerCorruptFile:
    """ExampleManager raises DocumentationError on corrupt YAML file (issue #878)."""

    def test_load_from_file_raises_on_corrupt_yaml(self, tmp_path):
        """_load_from_file raises DocumentationError when YAML is invalid."""
        yaml_file = tmp_path / "test.yaml"
        make_corrupt_yaml_file(yaml_file)

        manager = ExampleManager(examples_dir=str(tmp_path))
        with pytest.raises(DocumentationError, match="Failed to load examples"):
            manager._load_from_file(yaml_file)

    def test_load_examples_returns_empty_when_file_missing(self, tmp_path):
        """load_examples returns [] silently when the file does not exist."""
        manager = ExampleManager(examples_dir=str(tmp_path))
        result = manager.load_examples("nofile")
        assert result == []

    def test_save_examples_raises_on_unwritable_dir(self, tmp_path):
        """save_examples raises DocumentationError when dir is unwritable."""
        manager = ExampleManager(examples_dir=str(tmp_path))
        examples = [CommandExample(title="t", description="d", command="azlin x")]

        tmp_path.chmod(0o555)
        try:
            with pytest.raises(DocumentationError, match="Failed to save examples"):
                manager.save_examples("mount", examples)
        finally:
            tmp_path.chmod(0o755)


# ---------------------------------------------------------------------------
# Issue #879 — UTF-8 round-trip: hasher
# ---------------------------------------------------------------------------


class TestHasherUtf8:
    """CLIHasher reads/writes hash files with explicit UTF-8 encoding (issue #879)."""

    def test_save_and_load_ascii(self, tmp_path):
        """Round-trip save/load works for ASCII command names."""
        hash_file = tmp_path / ".cli_doc_hashes.json"
        hasher = CLIHasher(hash_file=str(hash_file))
        hasher._hashes = {"my-cmd": "deadbeef"}
        hasher.save_hashes()

        hasher2 = CLIHasher(hash_file=str(hash_file))
        assert hasher2._hashes == {"my-cmd": "deadbeef"}

    def test_save_and_load_non_ascii_command_name(self, tmp_path):
        """Round-trip save/load preserves non-ASCII characters in hash values.

        json.dump escapes non-ASCII as \\uXXXX by default — this is valid UTF-8
        JSON and the values survive the round-trip intact.
        """
        hash_file = tmp_path / ".cli_doc_hashes.json"
        hasher = CLIHasher(hash_file=str(hash_file))
        # Non-ASCII in the stored hash value (command names are ASCII in practice,
        # but the JSON value field can hold any string)
        hasher._hashes = {"cmd": "café-résumé-hash"}
        hasher.save_hashes()

        # File is valid UTF-8 JSON (non-ASCII may be \uXXXX-escaped — that's fine)
        raw = hash_file.read_text(encoding="utf-8")
        assert "cmd" in raw  # key is present

        # Round-trip: values are preserved exactly
        hasher2 = CLIHasher(hash_file=str(hash_file))
        assert hasher2._hashes["cmd"] == "café-résumé-hash"


# ---------------------------------------------------------------------------
# Issue #879 — UTF-8 round-trip: example_manager
# ---------------------------------------------------------------------------


class TestExampleManagerUtf8:
    """ExampleManager reads/writes YAML files with explicit UTF-8 encoding (issue #879)."""

    def test_save_and_load_ascii_example(self, tmp_path):
        """Round-trip save/load works for ASCII content."""
        manager = ExampleManager(examples_dir=str(tmp_path))
        examples = [
            CommandExample(
                title="Basic mount",
                description="Mounts a storage share",
                command="azlin mount storage",
            )
        ]
        assert manager.save_examples("mount", examples) is True

        loaded = manager.load_examples("mount")
        assert len(loaded) == 1
        assert loaded[0].title == "Basic mount"

    def test_save_and_load_non_ascii_content(self, tmp_path):
        """Round-trip save/load preserves non-ASCII characters in examples."""
        manager = ExampleManager(examples_dir=str(tmp_path))
        examples = [
            CommandExample(
                title="Ünïcödé títlé",
                description="Démonstration avec des caractères spéciaux: 日本語",
                command="azlin mount storage --label résumé",
            )
        ]
        assert manager.save_examples("mount", examples) is True

        yaml_file = tmp_path / "mount.yaml"
        raw = yaml_file.read_text(encoding="utf-8")
        assert "résumé" in raw

        loaded = manager.load_examples("mount")
        assert len(loaded) == 1
        assert loaded[0].title == "Ünïcödé títlé"
        assert "日本語" in loaded[0].description


# ---------------------------------------------------------------------------
# DocumentationError contract
# ---------------------------------------------------------------------------


class TestDocumentationError:
    """DocumentationError is a proper Exception subclass with chaining support."""

    def test_is_exception_subclass(self):
        """DocumentationError inherits from Exception so callers can catch it."""
        err = DocumentationError("something went wrong")
        assert isinstance(err, Exception)

    def test_message_preserved(self):
        """String message is accessible via str() / args."""
        msg = "Failed to load hashes from 'foo.json': [Errno 13] Permission denied"
        err = DocumentationError(msg)
        assert msg in str(err)

    def test_exception_chaining(self):
        """'raise DocumentationError(...) from e' preserves the original cause."""
        original = OSError("disk full")
        try:
            try:
                raise original
            except OSError as e:
                raise DocumentationError("save failed") from e
        except DocumentationError as doc_err:
            assert doc_err.__cause__ is original


# ---------------------------------------------------------------------------
# ChangeSet — has_changes property
# ---------------------------------------------------------------------------


class TestChangeSet:
    """ChangeSet.has_changes reflects any non-empty list."""

    def test_has_changes_false_when_all_empty(self):
        """Empty ChangeSet reports no changes."""
        cs = ChangeSet()
        assert cs.has_changes is False

    def test_has_changes_true_when_changed(self):
        """A changed command triggers has_changes."""
        cs = ChangeSet(changed=["mount"])
        assert cs.has_changes is True

    def test_has_changes_true_when_added(self):
        """A newly added command triggers has_changes."""
        cs = ChangeSet(added=["unmount"])
        assert cs.has_changes is True

    def test_has_changes_true_when_removed(self):
        """A removed command triggers has_changes."""
        cs = ChangeSet(removed=["old-cmd"])
        assert cs.has_changes is True


# ---------------------------------------------------------------------------
# CLIHasher — compute_hash
# ---------------------------------------------------------------------------


def _make_metadata(
    name: str = "mount",
    full_path: str = "azlin mount",
    help_text: str = "Mount a storage share",
    description: str = "Mounts the specified storage share.",
) -> _CLIMetadata:
    """Build a minimal CLIMetadata for hashing tests."""
    return _CLIMetadata(
        name=name,
        full_path=full_path,
        help_text=help_text,
        description=description,
    )


class TestHasherComputeHash:
    """CLIHasher.compute_hash produces correct SHA-256 digests."""

    def test_returns_64_char_hex_string(self, tmp_path):
        """SHA-256 hex digest is always 64 characters."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        result = hasher.compute_hash(_make_metadata())
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_is_deterministic(self, tmp_path):
        """Same metadata always produces the same hash."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        meta = _make_metadata()
        assert hasher.compute_hash(meta) == hasher.compute_hash(meta)

    def test_different_names_produce_different_hashes(self, tmp_path):
        """Two commands with different names have different hashes."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        h1 = hasher.compute_hash(_make_metadata(name="mount"))
        h2 = hasher.compute_hash(_make_metadata(name="unmount"))
        assert h1 != h2

    def test_changes_when_help_text_changes(self, tmp_path):
        """Changing help_text changes the hash."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        h1 = hasher.compute_hash(_make_metadata(help_text="Mount a share"))
        h2 = hasher.compute_hash(_make_metadata(help_text="Unmount a share"))
        assert h1 != h2

    def test_changes_when_description_changes(self, tmp_path):
        """Changing description changes the hash."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        h1 = hasher.compute_hash(_make_metadata(description="Short desc."))
        h2 = hasher.compute_hash(_make_metadata(description="Completely different."))
        assert h1 != h2


# ---------------------------------------------------------------------------
# CLIHasher — has_changed / update_hash
# ---------------------------------------------------------------------------


class TestHasherHasChanged:
    """CLIHasher.has_changed tracks command mutations correctly."""

    def test_new_command_has_changed(self, tmp_path):
        """A command with no stored hash is considered changed (new)."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        assert hasher.has_changed(_make_metadata()) is True

    def test_unchanged_after_update_hash(self, tmp_path):
        """After update_hash, has_changed returns False for the same metadata."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        meta = _make_metadata()
        hasher.update_hash(meta)
        assert hasher.has_changed(meta) is False

    def test_changed_after_metadata_modification(self, tmp_path):
        """has_changed returns True after the command help text is altered."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        original = _make_metadata(help_text="Old help")
        modified = _make_metadata(help_text="New help")
        hasher.update_hash(original)
        assert hasher.has_changed(modified) is True


# ---------------------------------------------------------------------------
# CLIHasher — compare_hashes
# ---------------------------------------------------------------------------


class TestHasherCompareHashes:
    """CLIHasher.compare_hashes detects added, changed, and removed commands."""

    def test_detects_added_command(self, tmp_path):
        """Commands absent from stored hashes appear in ChangeSet.added."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        meta = _make_metadata(name="new-cmd")
        changeset = hasher.compare_hashes({"new-cmd": meta})
        assert "new-cmd" in changeset.added
        assert changeset.changed == []
        assert changeset.removed == []

    def test_detects_removed_command(self, tmp_path):
        """Commands in stored hashes but absent from current appear in removed."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        meta = _make_metadata(name="old-cmd")
        hasher.update_hash(meta)
        changeset = hasher.compare_hashes({})  # command no longer present
        assert "old-cmd" in changeset.removed
        assert changeset.added == []
        assert changeset.changed == []

    def test_detects_changed_command(self, tmp_path):
        """Commands present in stored hashes but with new content appear in changed."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        original = _make_metadata(name="mount", help_text="Old help")
        modified = _make_metadata(name="mount", help_text="New help")
        hasher.update_hash(original)
        changeset = hasher.compare_hashes({"mount": modified})
        assert "mount" in changeset.changed
        assert changeset.added == []
        assert changeset.removed == []

    def test_no_changes_when_up_to_date(self, tmp_path):
        """Commands with matching hashes produce an empty ChangeSet."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        meta = _make_metadata(name="mount")
        hasher.update_hash(meta)
        changeset = hasher.compare_hashes({"mount": meta})
        assert changeset.has_changes is False


# ---------------------------------------------------------------------------
# CLIHasher — clear_hashes
# ---------------------------------------------------------------------------


class TestHasherClearHashes:
    """CLIHasher.clear_hashes wipes in-memory and on-disk state."""

    def test_clear_removes_in_memory_hashes(self, tmp_path):
        """After clear_hashes, _hashes is empty."""
        hasher = CLIHasher(hash_file=str(tmp_path / "h.json"))
        hasher.update_hash(_make_metadata())
        hasher.clear_hashes()
        assert hasher._hashes == {}

    def test_clear_deletes_hash_file(self, tmp_path):
        """After save then clear, the JSON file no longer exists on disk."""
        hash_file = tmp_path / "h.json"
        hasher = CLIHasher(hash_file=str(hash_file))
        hasher.update_hash(_make_metadata())
        hasher.save_hashes()
        assert hash_file.exists()
        hasher.clear_hashes()
        assert not hash_file.exists()


# ---------------------------------------------------------------------------
# ExampleManager — _sanitize_command_name
# ---------------------------------------------------------------------------


class TestExampleManagerSanitize:
    """ExampleManager._sanitize_command_name blocks path-traversal attacks."""

    def test_valid_alphanumeric_name_passes(self, tmp_path):
        """Plain alphanumeric command names are accepted unchanged."""
        mgr = ExampleManager(examples_dir=str(tmp_path))
        assert mgr._sanitize_command_name("mount") == "mount"

    def test_valid_hyphenated_name_passes(self, tmp_path):
        """Names with hyphens and underscores are accepted."""
        mgr = ExampleManager(examples_dir=str(tmp_path))
        assert mgr._sanitize_command_name("storage-mount_v2") == "storage-mount_v2"

    def test_path_traversal_raises_value_error(self, tmp_path):
        """Path-traversal sequences raise ValueError, not NameError."""
        mgr = ExampleManager(examples_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid command name"):
            mgr._sanitize_command_name("../etc/passwd")

    def test_dot_in_name_raises_value_error(self, tmp_path):
        """A dot in the command name is rejected (prevents .yaml extension tricks)."""
        mgr = ExampleManager(examples_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid command name"):
            mgr._sanitize_command_name("cmd.evil")


# ---------------------------------------------------------------------------
# ExampleManager — load_examples with invalid command name
# ---------------------------------------------------------------------------


class TestExampleManagerInvalidCommandName:
    """load_examples with an invalid command name propagates ValueError (#878)."""

    def test_load_examples_path_traversal_raises_value_error(self, tmp_path):
        """load_examples('../etc/passwd') raises ValueError (no error-swallowing)."""
        mgr = ExampleManager(examples_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid command name"):
            mgr.load_examples("../etc/passwd")

    def test_load_examples_space_in_name_raises_value_error(self, tmp_path):
        """load_examples('cmd with spaces') raises ValueError."""
        mgr = ExampleManager(examples_dir=str(tmp_path))
        with pytest.raises(ValueError, match="Invalid command name"):
            mgr.load_examples("cmd with spaces")


# ---------------------------------------------------------------------------
# ExampleManager — load_all_examples
# ---------------------------------------------------------------------------


class TestExampleManagerLoadAll:
    """ExampleManager.load_all_examples scans the examples directory."""

    def test_empty_directory_returns_empty_dict(self, tmp_path):
        """No YAML files → empty result dict."""
        mgr = ExampleManager(examples_dir=str(tmp_path))
        result = mgr.load_all_examples()
        assert result == {}

    def test_nonexistent_directory_returns_empty_dict(self, tmp_path):
        """A non-existent directory returns {} without raising."""
        mgr = ExampleManager(examples_dir=str(tmp_path / "no-such-dir"))
        result = mgr.load_all_examples()
        assert result == {}

    def test_loads_multiple_yaml_files(self, tmp_path):
        """All YAML files in the directory are loaded and keyed by stem."""
        mgr = ExampleManager(examples_dir=str(tmp_path))
        examples_a = [
            CommandExample(title="A", description="desc A", command="azlin a")
        ]
        examples_b = [
            CommandExample(title="B", description="desc B", command="azlin b")
        ]
        mgr.save_examples("cmd-a", examples_a)
        mgr.save_examples("cmd-b", examples_b)

        result = mgr.load_all_examples()
        assert "cmd-a" in result
        assert "cmd-b" in result
        assert result["cmd-a"][0].title == "A"
        assert result["cmd-b"][0].title == "B"

    def test_corrupt_yaml_propagates_documentation_error(self, tmp_path):
        """A corrupt YAML file inside the directory raises DocumentationError."""
        corrupt = tmp_path / "bad.yaml"
        make_corrupt_yaml_file(corrupt)
        mgr = ExampleManager(examples_dir=str(tmp_path))
        with pytest.raises(DocumentationError):
            mgr.load_all_examples()
