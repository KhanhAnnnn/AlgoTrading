// scripts/prod_web_server.mjs
// Production Static Web Server for AlgoTrading v1.0.0
// Features: Static file serving from dist/, SPA routing fallback, /healthz endpoint, security headers.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const REPO_ROOT = path.resolve(__dirname, '..');
const DIST_DIR = path.resolve(REPO_ROOT, 'trading-dashboard', 'frontend', 'dist');

// Parse CLI args or environment variables
const args = process.argv.slice(2);
function getArg(key, defaultVal) {
  const idx = args.indexOf(key);
  if (idx !== -1 && idx + 1 < args.length) return args[idx + 1];
  return defaultVal;
}

const PORT = parseInt(process.env.PROD_PORT || getArg('--port', '3000'), 10);
const HOST = process.env.PROD_HOST || getArg('--host', '0.0.0.0');

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.txt': 'text/plain; charset=utf-8'
};

const startTime = Date.now();

// Check if DIST_DIR exists
if (!fs.existsSync(DIST_DIR)) {
  console.error(`[ERROR] Production dist directory not found at: ${DIST_DIR}`);
  console.error(`Please run 'npm run build' inside trading-dashboard/frontend first.`);
  process.exit(1);
}

const server = http.createServer((req, res) => {
  // Common security headers
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'SAMEORIGIN');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  res.setHeader('Server', 'AlgoTrading-Production-Web/1.0.0');

  const parsedUrl = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = decodeURIComponent(parsedUrl.pathname);

  // 1. Health check endpoint
  if (pathname === '/healthz' || pathname === '/api/prod-server/health') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({
      status: 'HEALTHY',
      server: 'AlgoTrading Production Web Server',
      version: 'v1.0.0',
      mode: 'PRODUCTION',
      port: PORT,
      host: HOST,
      dist_dir: DIST_DIR,
      spa_fallback: true,
      uptime_seconds: Math.floor((Date.now() - startTime) / 1000),
      timestamp: new Date().toISOString()
    }, null, 2));
    return;
  }

  // 2. Prevent path traversal attacks
  const safePath = path.normalize(pathname).replace(/^(\.\.[\/\\])+/, '');
  let filePath = path.join(DIST_DIR, safePath);

  // If path tries to escape DIST_DIR
  if (!filePath.startsWith(DIST_DIR)) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('403 Forbidden: Path traversal prohibited');
    return;
  }

  // Check if requested path is a directory (serve index.html)
  try {
    const stats = fs.statSync(filePath);
    if (stats.isDirectory()) {
      filePath = path.join(filePath, 'index.html');
    }
  } catch {
    // File not found directly - will handle via SPA fallback or 404
  }

  // 3. Static file exists -> serve with appropriate cache control
  if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
    const ext = path.extname(filePath).toLowerCase();
    const mime = MIME_TYPES[ext] || 'application/octet-stream';

    // Cache immutable assets (hashed in assets/)
    if (filePath.includes(path.join(DIST_DIR, 'assets'))) {
      res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
    } else {
      res.setHeader('Cache-Control', 'no-cache, must-revalidate');
    }

    res.writeHead(200, { 'Content-Type': mime });
    const stream = fs.createReadStream(filePath);
    stream.pipe(res);
    return;
  }

  // 4. SPA Fallback: If URL doesn't have a file extension, serve dist/index.html
  const ext = path.extname(pathname);
  const indexPath = path.join(DIST_DIR, 'index.html');

  if (!ext && fs.existsSync(indexPath)) {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.setHeader('Cache-Control', 'no-cache, must-revalidate');
    res.writeHead(200);
    const stream = fs.createReadStream(indexPath);
    stream.pipe(res);
    return;
  }

  // 5. File has an extension but doesn't exist -> 404 Not Found
  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end(`404 Not Found: ${pathname}`);
});

server.listen(PORT, HOST, () => {
  console.log(`[PRODUCTION WEB SERVER] Running at http://${HOST === '0.0.0.0' ? 'localhost' : HOST}:${PORT}`);
  console.log(`[PRODUCTION WEB SERVER] Serving bundle from: ${DIST_DIR}`);
  console.log(`[PRODUCTION WEB SERVER] Health endpoint at: http://${HOST === '0.0.0.0' ? 'localhost' : HOST}:${PORT}/healthz`);
  console.log(`[PRODUCTION WEB SERVER] SPA fallback active.`);
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log('\n[PRODUCTION WEB SERVER] Shutting down gracefully...');
  server.close(() => process.exit(0));
});

process.on('SIGTERM', () => {
  console.log('\n[PRODUCTION WEB SERVER] SIGTERM received. Shutting down gracefully...');
  server.close(() => process.exit(0));
});

