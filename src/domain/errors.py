class RepositoryError(Exception):
    """Base for persistence-layer errors surfaced to the domain."""


class RecordNotFound(RepositoryError):
    pass


class IntegrityConflict(RepositoryError):
    pass


class InvalidFilter(RepositoryError):
    pass
