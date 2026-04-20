const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store, no-cache, must-revalidate, max-age=0',
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET,POST,OPTIONS',
  'access-control-allow-headers': 'Content-Type, Authorization, X-QuantGod-Token, X-QuantGod-Source'
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: JSON_HEADERS
  });
}

function getBearerToken(request) {
  const auth = request.headers.get('authorization') || '';
  if (auth.toLowerCase().startsWith('bearer ')) {
    return auth.slice(7).trim();
  }
  return request.headers.get('x-quantgod-token') || '';
}

function isAuthorized(request, env) {
  const expected = env.QG_INGEST_TOKEN;
  if (!expected) return true;
  return getBearerToken(request) === expected;
}

async function handleIngest(request, env) {
  if (!isAuthorized(request, env)) {
    return jsonResponse({ ok: false, error: 'UNAUTHORIZED' }, 401);
  }

  let snapshot;
  try {
    snapshot = await request.json();
  } catch (error) {
    return jsonResponse({ ok: false, error: 'INVALID_JSON', detail: error.message }, 400);
  }

  if (!snapshot || typeof snapshot !== 'object') {
    return jsonResponse({ ok: false, error: 'INVALID_PAYLOAD' }, 400);
  }

  if (!snapshot.runtime || !snapshot.account) {
    return jsonResponse({ ok: false, error: 'MISSING_CORE_FIELDS' }, 400);
  }

  const receivedAt = new Date().toISOString();
  const enriched = {
    ...snapshot,
    cloudTransport: {
      receivedAt,
      source: request.headers.get('x-quantgod-source') || 'unknown',
      colo: request.cf?.colo || 'unknown'
    }
  };

  await env.QG_STATE.put('latest', JSON.stringify(enriched));
  await env.QG_STATE.put(
    'latest_meta',
    JSON.stringify({
      receivedAt,
      tradeStatus: enriched.runtime?.tradeStatus || 'NO_DATA',
      watchlist: enriched.watchlist || '',
      source: request.headers.get('x-quantgod-source') || 'unknown'
    })
  );

  return jsonResponse({
    ok: true,
    receivedAt,
    tradeStatus: enriched.runtime?.tradeStatus || 'NO_DATA'
  });
}

async function handleLatest(env) {
  const latest = await env.QG_STATE.get('latest');
  if (!latest) {
    return jsonResponse(
      {
        ok: false,
        error: 'NO_SNAPSHOT',
        detail: 'No MT4 snapshot has been pushed yet.'
      },
      404
    );
  }

  return new Response(latest, {
    status: 200,
    headers: JSON_HEADERS
  });
}

async function handleHealth(env) {
  const latestMetaRaw = await env.QG_STATE.get('latest_meta');
  const latestMeta = latestMetaRaw ? JSON.parse(latestMetaRaw) : null;

  return jsonResponse({
    ok: true,
    service: 'quantgod-cloudflare',
    hasSnapshot: Boolean(latestMeta),
    latestMeta
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: JSON_HEADERS });
    }

    if (url.pathname === '/api/health') {
      return handleHealth(env);
    }

    if (url.pathname === '/api/latest') {
      if (request.method !== 'GET') {
        return jsonResponse({ ok: false, error: 'METHOD_NOT_ALLOWED' }, 405);
      }
      return handleLatest(env);
    }

    if (url.pathname === '/api/ingest') {
      if (request.method !== 'POST') {
        return jsonResponse({ ok: false, error: 'METHOD_NOT_ALLOWED' }, 405);
      }
      return handleIngest(request, env);
    }

    return env.ASSETS.fetch(request);
  }
};
