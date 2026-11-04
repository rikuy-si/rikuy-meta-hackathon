// Local static server for dist/ with HTTP Range support (adapted from enpiso/video-review/serve-vision-local.cjs).
// Usage: node serve.cjs [port] [root]          default port 8790, root ./dist, binds 127.0.0.1 only
// /_local-video/<file>.mp4 maps to the local recordings, used by the browser test with ?src=local (the
// published page always streams the public R2 copies).
const http = require('node:http'), fs = require('node:fs'), path = require('node:path');
const videoRoot = path.resolve(__dirname, '../enpiso/video-review/media/full-playlist-v1');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.mp4': 'video/mp4',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.bin': 'application/octet-stream', '.txt': 'text/plain; charset=utf-8', '.css': 'text/css; charset=utf-8' };
function start(port = 8790, rootDir = path.join(__dirname, 'dist')) {
const root = path.resolve(rootDir);
function resolve(rel) {
  if (rel.startsWith('/_local-video/')) { const f = path.join(videoRoot, path.basename(rel)); return /^module-full-\d\d\.mp4$/.test(path.basename(rel)) ? f : null; }
  const f = path.join(root, rel === '/' ? '/index.html' : rel);
  return f.startsWith(root + path.sep) ? f : null;
}
return http.createServer((req, res) => {
  let rel;
  try { rel = decodeURIComponent(new URL(req.url, 'http://x').pathname); } catch { res.writeHead(400).end(); return; }
  const file = resolve(rel);
  if (!file) { res.writeHead(403).end(); return; }
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) { res.writeHead(404, { 'content-type': 'text/plain' }).end('not found'); return; }
    const base = { 'content-type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', 'accept-ranges': 'bytes', 'cache-control': 'no-cache' };
    const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
    if (m) {
      const start = m[1] === '' ? Math.max(0, st.size - Number(m[2])) : Number(m[1]);
      const end = m[1] !== '' && m[2] !== '' ? Math.min(Number(m[2]), st.size - 1) : st.size - 1;
      if (start > end || start >= st.size) { res.writeHead(416, { 'content-range': `bytes */${st.size}` }).end(); return; }
      res.writeHead(206, { ...base, 'content-range': `bytes ${start}-${end}/${st.size}`, 'content-length': end - start + 1 });
      if (req.method === 'HEAD') { res.end(); return; }
      fs.createReadStream(file, { start, end }).on('error', () => res.destroy()).pipe(res);
      return;
    }
    res.writeHead(200, { ...base, 'content-length': st.size });
    if (req.method === 'HEAD') { res.end(); return; }
    fs.createReadStream(file).on('error', () => res.destroy()).pipe(res);
  });
}).listen(port, '127.0.0.1', () => console.log(`serving ${root} on http://127.0.0.1:${port}/`));
}
module.exports = { start };
if (require.main === module) start(Number(process.argv[2] || 8790), process.argv[3] || path.join(__dirname, 'dist'));
