"""Document extraction pipeline.

Deterministic-first per CLAUDE.md §2: rules + ICAO checksums first, then
visual OCR (Phase 2), then LLM tiebreaker (Phase 2). Every step has a
confidence score; everything below threshold escalates.
"""
