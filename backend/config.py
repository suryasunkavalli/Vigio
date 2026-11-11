"""Shared non-secret configuration for Vigio services."""

PLATFORM_VERSION = "Vigio MVP 0.2"

# Signal-of-disproportionate-reporting heuristics. These require validation
# before any regulated or production use.
SDR_MIN_CASES = 3
ROR_STRONG = 5.0
ROR_MODERATE = 2.0
