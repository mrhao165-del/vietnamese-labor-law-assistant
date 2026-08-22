"""Closed vocabulary for Week-2 case-intake facts."""

from enum import StrEnum


class AssertionMode(StrEnum):
    """How a fact entered intake, independently from whether it is verified."""

    EXPLICIT = "EXPLICIT"
    INFERRED = "INFERRED"


class VerificationStatus(StrEnum):
    """Week 2 accepts user-supplied facts but does not verify them."""

    UNVERIFIED = "UNVERIFIED"


class SourceType(StrEnum):
    """The only intake source supported before document analysis exists."""

    USER_MESSAGE = "USER_MESSAGE"
