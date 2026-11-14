"""lunarnav: scientific engine for the Lunar Landing Site Navigator.

The engine is framework-free (no web imports) so every calculation can be tested in isolation.
Stage 1 contains only the shared foundations: version/provenance identity and typed errors.
"""

MODEL_VERSION = "0.1.0-stage1"
"""Recorded in every scientific result's provenance. Bump when any calculation changes."""

__all__ = ["MODEL_VERSION"]
