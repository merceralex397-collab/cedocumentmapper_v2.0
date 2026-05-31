class ReaderError(Exception):
    """Base exception for all document reader failures."""
    pass


class UnsupportedFormatError(ReaderError):
    """Raised when a file format is not supported or cannot be determined."""
    pass


class DependencyMissingError(ReaderError):
    """Raised when a required external library or binary is missing."""
    pass
