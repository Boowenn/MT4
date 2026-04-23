const http = require('http');
const fs = require('fs');
const path = require('path');

const host = '127.0.0.1';
const port = 8080;
const rootDir = __dirname;

const contentTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

const runtimeTextExtensions = new Set(['.json', '.csv', '.txt']);
const shiftJisDecoder = new TextDecoder('shift_jis');

function send(res, statusCode, headers, body) {
  res.writeHead(statusCode, headers);
  res.end(body);
}

function maybeTranscodeRuntimeText(target, ext, data) {
  const base = path.basename(target);
  if (!runtimeTextExtensions.has(ext) || !base.startsWith('QuantGod_')) {
    return data;
  }

  try {
    const utf8Text = shiftJisDecoder.decode(data);
    return Buffer.from(utf8Text, 'utf8');
  } catch (err) {
    console.warn(`QuantGod dashboard server transcode fallback for ${base}: ${err.message}`);
    return data;
  }
}

function safeResolve(urlPath) {
  const pathname = decodeURIComponent(urlPath.split('?')[0] || '/');
  const normalized = pathname === '/' ? '/QuantGod_Dashboard.html' : pathname;
  const target = path.resolve(rootDir, '.' + normalized);
  if (!target.startsWith(rootDir)) {
    return null;
  }
  return target;
}

const server = http.createServer((req, res) => {
  const target = safeResolve(req.url || '/');
  if (!target) {
    send(res, 403, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Forbidden');
    return;
  }

  fs.stat(target, (statErr, stats) => {
    if (statErr || !stats.isFile()) {
      send(res, 404, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Not Found');
      return;
    }

    const ext = path.extname(target).toLowerCase();
    const contentType = contentTypes[ext] || 'application/octet-stream';

    fs.readFile(target, (readErr, data) => {
      if (readErr) {
        send(res, 500, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Read Failed');
        return;
      }

      const body = maybeTranscodeRuntimeText(target, ext, data);

      send(res, 200, {
        'Content-Type': contentType,
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        Pragma: 'no-cache',
        Expires: '0',
        'Access-Control-Allow-Origin': '*'
      }, body);
    });
  });
});

server.listen(port, host, () => {
  console.log(`QuantGod dashboard server running at http://${host}:${port}/QuantGod_Dashboard.html`);
});

server.on('error', (err) => {
  console.error('QuantGod dashboard server failed:', err.message);
  process.exit(1);
});
