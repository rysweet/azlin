"""Secure file transfer module for azlin cp command."""

from .exceptions import (
    FileTransferError,
    InvalidPathError,
    InvalidSessionNameError,
    InvalidTransferError,
    MultipleSessionsError,
    PathTraversalError,
    SessionNotFoundError,
    SymlinkSecurityError,
    TransferError,
)
from .file_transfer import FileTransfer, TransferEndpoint, TransferResult
from .path_parser import PathParser
from .session_manager import SessionManager, VMSession

__all__ = [
    # Exceptions
    "FileTransferError",
    "PathTraversalError",
    "InvalidPathError",
    "SymlinkSecurityError",
    "InvalidSessionNameError",
    "SessionNotFoundError",
    "MultipleSessionsError",
    "TransferError",
    "InvalidTransferError",
    # Classes
    "PathParser",
    "SessionManager",
    "VMSession",
    "FileTransfer",
    "TransferEndpoint",
    "TransferResult",
]
