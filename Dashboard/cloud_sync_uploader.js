const fs = require('fs');
const path = require('path');

const rootDir = __dirname;
const configPath = path.join(rootDir, 'quantgod_cloud_sync.enabled.json');
const dataPath = path.join(rootDir, 'QuantGod_Dashboard.json');
const pollIntervalMs = 10000;

let lastSignature = '';
let lastSuccessAt = '';

function log(message) {
  console.log(`[QuantGod Cloud Sync] ${message}`);
}

function readJson(filePath) {
  const raw = fs.readFileSync(filePath);
  let text = raw.toString('utf8').replace(/^\uFEFF/, '');
  if (text.includes('\u0000')) {
    text = raw.toString('utf16le').replace(/^\uFEFF/, '');
  }
  return JSON.parse(text);
}

function buildRequestOptions(config, body) {
  const endpoint = new URL(config.endpoint);
  return {
    protocol: endpoint.protocol,
    hostname: endpoint.hostname,
    port: endpoint.port || (endpoint.protocol === 'https:' ? 443 : 80),
    path: `${endpoint.pathname}${endpoint.search}`,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body),
      'X-QuantGod-Source': 'local-uploader',
      ...(config.token ? { Authorization: `Bearer ${config.token}` } : {})
    }
  };
}

function sendPayload(config, payload) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(payload);
    const options = buildRequestOptions(config, body);
    const transport = options.protocol === 'https:' ? require('https') : require('http');

    const req = transport.request(options, (res) => {
      let responseText = '';
      res.on('data', (chunk) => {
        responseText += chunk.toString('utf8');
      });
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve({ statusCode: res.statusCode, body: responseText });
          return;
        }
        reject(new Error(`HTTP ${res.statusCode}: ${responseText}`));
      });
    });

    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function enrichSnapshot(snapshot, config) {
  const now = new Date();
  const localText = now.toLocaleString('sv-SE').replace('T', ' ');

  return {
    ...snapshot,
    cloudSync: {
      enabled: true,
      configured: true,
      endpoint: config.endpoint,
      intervalSeconds: Math.floor(pollIntervalMs / 1000),
      lastAttemptLocal: localText,
      lastSuccessLocal: lastSuccessAt || '',
      status: 'SYNCED',
      httpCode: 200,
      message: 'Local uploader active'
    }
  };
}

async function tick() {
  if (!fs.existsSync(configPath)) {
    log('Missing quantgod_cloud_sync.enabled.json, uploader idle.');
    return;
  }

  if (!fs.existsSync(dataPath)) {
    log('Waiting for QuantGod_Dashboard.json...');
    return;
  }

  let config;
  let snapshot;
  try {
    config = readJson(configPath);
    snapshot = readJson(dataPath);
  } catch (error) {
    log(`Read failed: ${error.message}`);
    return;
  }

  if (!config.endpoint) {
    log('Config missing endpoint, uploader idle.');
    return;
  }

  const stat = fs.statSync(dataPath);
  const signature = `${stat.mtimeMs}:${stat.size}`;
  if (signature === lastSignature) {
    return;
  }

  const payload = enrichSnapshot(snapshot, config);
  try {
    const result = await sendPayload(config, payload);
    lastSignature = signature;
    lastSuccessAt = new Date().toLocaleString('sv-SE').replace('T', ' ');
    log(`Synced OK -> ${config.endpoint} (${result.statusCode})`);
  } catch (error) {
    log(`Sync failed: ${error.message}`);
  }
}

log('Uploader started.');
tick();
setInterval(tick, pollIntervalMs);
