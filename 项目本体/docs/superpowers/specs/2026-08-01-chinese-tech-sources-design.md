# Chinese Tech Sources Design

## Scope

Add IT Home and Juejin as independently reported public sources for the AI Radar collector.

## Approach

Each site will use an official RSS feed when a stable, parseable feed is available. If not, the application will use a narrow public-page or API adapter for that site. Both adapters emit the existing `SourceItemPayload` contract and therefore inherit the current relevance filter, seven-day collection window, de-duplication, and persistence behavior.

## Failure Handling

Each adapter is registered separately, so a failure is recorded against that source only and collection continues with all other sources.

## Configuration and Testing

Source endpoints are configurable through settings and documented in `.env.example`. Tests cover response parsing, adapter enablement, and the existing failure-isolation behavior.
