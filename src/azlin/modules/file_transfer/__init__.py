"""Secure file transfer module for azlin cp command."""

from .exceptions import (
    FileTransferError,
    PathTraversalError,
    InvalidPathError,
    SymlinkSecurityError,
    InvalidSessionNameError,
    SessionNotFoundError,
    MultipleSessionsError,
    TransferError,
    InvalidTransferError,
)

from .path_parser import PathParser
from .session_manager import SessionManager, VMSession
from .file_transfer import FileTransfer, TransferEndpoint, TransferResult

__all__ = [
    # Exceptions
    'FileTransferError',
    'PathTraversalError',
    'InvalidPathError',
    'SymlinkSecurityError',
    'InvalidSessionNameError',
    'SessionNotFoundError',
    'MultipleSessionsError',
    'TransferError',
    'InvalidTransferError',
    # Classes
    'PathParser',
    'SessionManager',
    'VMSession',
    'FileTransfer',
    'TransferEndpoint',
    'TransferResult',
]
