"""Custom exceptions for file transfer."""


class FileTransferError(Exception):
    """Base exception for file transfer errors."""

    pass


class PathTraversalError(FileTransferError):
    """Path attempts to escape allowed directory."""

    pass


class InvalidPathError(FileTransferError):
    """Path is malformed or invalid."""

    pass


class SymlinkSecurityError(FileTransferError):
    """Symlink points to dangerous location."""

    pass


class InvalidSessionNameError(FileTransferError):
    """Session name contains invalid characters."""

    pass


class SessionNotFoundError(FileTransferError):
    """Session doesn't exist or VM not running."""

    pass


class MultipleSessionsError(FileTransferError):
    """Multiple VMs match session name."""

    pass


class TransferError(FileTransferError):
    """Transfer operation failed."""

    pass


class InvalidTransferError(FileTransferError):
    """Invalid transfer configuration."""

    pass
