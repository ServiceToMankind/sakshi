"""Extraction stage: turn already-public source text into structured candidates.

Extraction uses Gemini to SUMMARIZE and CLASSIFY already-public text only --
never to generate factual claims. Its output is constrained by
``schemas/extraction.schema.json``, which is structurally incapable of holding
victim data. Every field must be traceable to a source excerpt, and every
candidate carries a confidence score; anything < 0.8 is quarantined for human
review and never auto-published.
"""
