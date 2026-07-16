"""Typed errors raised by deterministic calculator operations."""


class CalculatorError(ValueError):
    """Base class for expected, public calculator failures."""


class InvalidDateRangeError(CalculatorError):
    """Raised when a required end date is absent."""


class EndDateBeforeStartDateError(CalculatorError):
    """Raised when the end date is before the start date."""


class InvalidInputCombinationError(CalculatorError):
    """Raised when closed enum inputs cannot form a supported rule condition."""


class RuleNotFoundError(CalculatorError):
    """Raised when no immutable rule matches otherwise validated input."""
