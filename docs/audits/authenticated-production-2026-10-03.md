# Authenticated production review — 2026-10-03

Interactive review of the production Cloudflare Worker in an authenticated desktop cloud browser. The owner configured email OTP and completed the secure sign-in flow. No credentials or Access policy changes are included in this repository.

Baseline main and Render deploy: `871b4e52a54c09ef8bb52b5639c84c979240d220`.

## Findings

- **Issuer collision:** Techstep's canonical page displayed Bio-Techne articles and earnings reports, including in the reasons-to-follow panel. PR #139 requires the Oslo-qualified Yahoo symbol or an untagged full registry-name match. Bare ticker and partial-name matches are rejected. Main advanced to `877c28bbecc0fbc2a0e4cd2540af3f490245a6c9` after all five head checks passed. Local backend suite: 752 passed; existing deprecation warnings and a restricted-network benchmark thread warning were observed.
- **Market labels:** Raw English trend codes were visible in ranking rows. Use Norwegian descriptions with explicit unknown/missing states; preserve ranking, scores and action labels.
- **Theme transition:** Immediately after light-to-dark switching, alert buttons briefly had pale text on a white background. Computed styles after settling were correct. Disable the background-only button transition so foreground and background change together.
- **Search coverage:** `TECH` returned CMB.TECH and Xplora, while `Techstep` returned Techstep ASA (`TECH.OL`). Exact company-name search worked; ticker coverage remains provider-dependent outside the tracked universe. Do not describe this as complete search coverage.

## Observed working

- Market loaded 26 ranked stocks and disclosed stored observations and score timestamps.
- Header navigation reached Morning Brief, alerts and Market; the menu opened and its IPO link selected the correct view.
- Morning Brief finished loading with dated source links and explicit observation timestamps.
- Alerts loaded 30 historical events. This browser reported blocked notification permission, no local subscription, and ready server configuration, explicitly without claiming receipt.
- Techstep loaded identity, quote, historical chart, conservative financing document status, historical-status caveats, missing dilution inputs and partial source coverage. An old completed placement was not presented as an active transaction.
- IPO period controls showed empty upcoming coverage and three recent listings with official source links, missing-data disclosures and no score effect.
- Dark theme persisted between pages. Light and dark controls both operated.

## Not certified

This is desktop interaction, not an iPhone simulator or physical iPhone test. Safe areas, installation/update, offline operation and actual notification delivery/tap/deduplication still require device-level validation. No browser viewport-emulation or offline-control API was available in this review. Local tests do not substitute for these checks.

The Worker still denies mutating API relay requests, including push subscription and testpush. OTP sign-in does not remove that separate application boundary. A verified authenticated write path is a separate security change; no broad bypass was introduced. The exposed write token still requires coordinated Cloudflare/Render rotation; no one-sided rotation was attempted.

Company context for Techstep still lacks description, ISIN and validated financial snapshots. Its separate fundamentals panel discloses missing reporting period/currency compatibility. Some historical financing documents have unsupported formats. These gaps remain visible; no values or statuses were fabricated.
