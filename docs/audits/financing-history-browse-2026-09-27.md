# Stored financing history access

Canonical Stock now loads older stored documents on demand in pages of 20. The cursor uses publication time plus source URL, so identical timestamps have a deterministic order and a newly inserted newer document does not shift an offset. Identity remains scoped to the current uniquely matched issuer. GET requests read database snapshots only; ticker-specific reads no longer scan other companies' profiles/events.

The UI retains visible results when a page fails, allows retry, ignores duplicate URLs, guards against stale page requests, and explicitly says that data can change between page fetches. Stored publication-date bounds describe the documents held, not contiguous source coverage. Historical archive backfill is explicitly marked not connected.

Source investigation: Euronext's official Oslo page identifies NewsWeb as the company-announcement service (https://www.euronext.com/en/markets/oslo). NewsWeb's public landing page (https://newsweb.oslobors.no/) renders only a JavaScript application to the search reader. No documented machine-readable historical feed has been verified in this work; no guessed endpoint, search snippet import, or claim of complete historical coverage is added.

PWA shell v20. No frozen model, sizing, push-rule or credential changes. Authenticated production UI/PWA/push QA remains blocked by the previously observed Cloudflare robot-verification page.
