---
name: generate-draft-image
description: Generate and verify artwork for an AI Radar draft using the project's configured OpenAI-compatible image API. Use when a user asks to create, regenerate, adjust, or troubleshoot a draft image in this repository.
---

# Generate Draft Image

Use the existing image-generation workflow. Do not expose, copy, or commit API keys.

1. Inspect `app/services/creator.py` and the affected draft route before changing behavior. The configured image API uses `IMAGE_API_KEY`, `IMAGE_BASE_URL`, `IMAGE_MODEL`, and `IMAGE_SIZE` from the project's `.env` file.
2. Generate through the draft editor or `POST /drafts/{draft_id}/image`. Keep the prompt focused on subject, composition, lighting, style, aspect ratio, and negative constraints. Do not request visible text, logos, or trademarks unless the user explicitly requires them.
3. Verify the response creates a file under `app/static/generated/`, persists its URL in `editor_params_json`, and renders it on the draft page.
4. On failure, report the HTTP or provider error without logging the API key. Check the configured base URL, model name, supported image sizes, and whether the provider returns `b64_json`.
5. Preserve the draft's source links and content. Only send the finalized image prompt and optional image adjustment to the image endpoint.
