import pytest

from domain.errors import IntegrityConflict, InvalidFilter, RecordNotFound, RepositoryError


@pytest.mark.parametrize("exc", [RecordNotFound, IntegrityConflict, InvalidFilter])
def test_errors_are_repository_errors(exc):
    with pytest.raises(RepositoryError):
        raise exc("boom")
