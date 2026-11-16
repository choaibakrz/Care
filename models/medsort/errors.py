class PipelineError(Exception):
    """Base for every error this package raises on purpose."""


class DataError(PipelineError):
    """Bad dataset or image. The message names the offending file."""


class ConfigError(PipelineError):
    """Bad taxonomy / phase config. Never silently fall back."""


class BackendError(PipelineError):
    """A backend failed or is unknown."""


class CapabilityError(BackendError):
    """The chosen backend does not support the requested operation."""
