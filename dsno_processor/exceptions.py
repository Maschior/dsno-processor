"""Custom exceptions for the DSNO Processor application."""


class DsnoProcessorError(Exception):
    """Base exception for all DSNO Processor errors."""


class ConfigurationError(DsnoProcessorError):
    """Raised when the configuration file is invalid or missing."""


class SheetNotFoundError(DsnoProcessorError):
    """Raised when a required spreadsheet file is not found."""


class ColumnMissingError(DsnoProcessorError):
    """Raised when a required column is missing from a spreadsheet."""


class DsnoFileError(DsnoProcessorError):
    """Raised when a DSNO file cannot be read or written."""


class InvalidDateRangeError(DsnoProcessorError):
    """Raised when the date range format is invalid."""

class LoginError(DsnoProcessorError):
    """Raised when the login fails."""

class CanceledError(DsnoProcessorError):
    """Raised when the operation is canceled by the user."""
