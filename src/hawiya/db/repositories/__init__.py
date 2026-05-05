"""Data-access repositories. All methods take ``tenant_id`` as first arg.

CLAUDE.md §5 requires every WHERE clause to include ``tenant_id``. RLS at
the session level is the safety net; explicit WHEREs are the contract.
"""

from hawiya.db.repositories.person_identifier_repository import (
    PersonIdentifierRepository,
)
from hawiya.db.repositories.person_repository import PersonRepository

__all__ = ["PersonIdentifierRepository", "PersonRepository"]
