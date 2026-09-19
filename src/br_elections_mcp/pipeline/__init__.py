"""Refresh pipeline, separate from the service.

Five stages, each a function with file input and file output so any stage can
run alone: fetch, build, validate, mirror_photos, publish. This package imports
domain.py, elections.py and index_schema.py only; never the core nor the
adapters, and it never starts a server (docs/codebase-design.md, section 5).
"""
