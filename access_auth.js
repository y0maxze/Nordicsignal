import {createRemoteJWKSet, jwtVerify} from 'jose';

// Public Access configuration only. Never derive a key URL from a request or JWT.
let cachedIssuer, cachedKeys;
export async function verifiedAccess(request, env) {
  const issuer = env?.NORDICSIGNAL_ACCESS_ISSUER;
  const audience = env?.NORDICSIGNAL_ACCESS_AUD;
  const token = request.headers.get('cf-access-jwt-assertion');
  if (!/^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/.test(issuer || '') ||
      !/^[a-f0-9]{64}$/.test(audience || '') || !token || token.length > 16384) return false;
  try {
    if (cachedIssuer !== issuer) {
      cachedKeys = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`), {
        timeoutDuration: 5000, cooldownDuration: 30000, cacheMaxAge: 300000,
      });
      cachedIssuer = issuer;
    }
    const {payload} = await jwtVerify(token, cachedKeys, {
      issuer, audience, algorithms: ['RS256'],
      requiredClaims: ['exp', 'iat', 'sub', 'email', 'type'],
    });
    return payload.type === 'app' && typeof payload.sub === 'string' && payload.sub.length > 0 &&
      typeof payload.email === 'string' && payload.email.length > 0 &&
      payload.iat <= Math.floor(Date.now() / 1000) && payload.exp > payload.iat;
  } catch {
    // Invalid tokens, key rotation/fetch failures and missing claims fail closed.
    // Never return/log claims, tokens or raw provider errors.
    return false;
  }
}
