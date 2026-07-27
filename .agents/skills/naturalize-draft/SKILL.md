---
name: naturalize-draft
description: Revise AI Radar drafts into clearer, more natural editorial Chinese while preserving sourced facts and Markdown links. Use when a user asks to reduce formulaic AI-like wording, improve readability, vary rhythm, or prepare a draft for human review.
---

# Naturalize Draft

Improve editorial quality; do not claim to evade, bypass, or guarantee results from AI-detection systems.

1. Read the draft and its linked evidence first. Preserve every Markdown source link and do not add factual claims, numbers, quotations, or attribution not supported by those sources.
2. Replace vague transitions, repeated sentence openings, promotional superlatives, and generic conclusions with specific, sourced wording. Vary sentence length only when it improves clarity.
3. Keep the author's intended platform, audience, and voice. Prefer concise Chinese prose, concrete subjects, and qualified statements where evidence is incomplete.
4. Use the existing safe rewrite modes in `app/services/editorial.py` when they cover the requested change. For broader edits, present or apply a tracked rewrite and retain the original source section unchanged.
5. Run the editorial review after rewriting. Flag unsupported judgments, repeated connectors, generic sentences, and strong conclusions for human review rather than silently inventing support.
6. Describe the result as a naturalized, source-preserving revision. Do not describe it as a way to lower an "AI rate" or to defeat a detector.
