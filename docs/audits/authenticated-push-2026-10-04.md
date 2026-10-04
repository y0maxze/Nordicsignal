# Authenticated push boundary — 2026-10-04

The public Worker previously denied every write, including registration and test
push even after successful Cloudflare Access login. This change permits only exact
POST paths `/api/push/subscribe`, `/api/push/unsubscribe` and `/api/push/test`.

Before relaying a push write, the Worker requires a Cloudflare application JWT
verified with jose against the configured team's public JWKS: RS256 signature,
issuer, application audience, expiry, issuance, subject, email and application
token type. JWKS fetches have a five-second timeout and bounded cache; failures
close access. Request headers cannot choose the key URL. Missing configuration
also closes access. The configured issuer and audience are public identifiers.

The existing Access application policy remains the authorization authority for
this private single-user app. This is not a multi-user subscription ownership
model. Expanding the app's authorized users requires a separate ownership design.

Writes additionally require HTTPS, exact same-origin Origin, compatible Fetch
Metadata, JSON content type, no query parameters and an actual body no larger than
16 KiB. Other writes, refresh triggers and personal-data routes remain blocked.
Access JWTs/cookies and client authorization headers are removed before proxying
to Render. The existing internal secret is injected only server-side and has not
been rotated. Backend validation and write rate limits still apply.

A read-only `/api/push/access` check reveals only whether push writes are permitted.
The activation button stays hidden/disabled until that check succeeds. Activation
still requires browser permission and acknowledged server registration; a browser
subscription alone is not reported as success. Test-push acceptance is explicitly
not proof of device delivery. Signal selection, thresholds, sizing and automatic
push rules are unchanged. PWA cache version is v28.

## Validation and limits

Tests exercise real signed JWTs and the actual Worker with mocked JWKS/backend
HTTP, including signature/algorithm/audience/issuer/expiry/claim failures,
provider failure, cross-origin writes, oversized/malformed bodies, forbidden
routes, credential stripping, accepted push paths and read-only capability checks.
DOM tests verify the activation control stays unavailable on denied/failed access.

Production delivery, iPhone installation, background receipt and tapping a
notification require actual-device verification. Neither a green test suite nor
an HTTP acceptance response certifies these behaviors.

References:
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/
- https://developers.cloudflare.com/workers/configuration/cloudflare-access/

Workers with Static Assets do not receive the trusted `ctx.access` context from
the internal router, so this implementation performs JWT validation explicitly.
