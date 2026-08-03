// node --test cron/send-digest.test.js
//
// Exercises the real send path against a localhost HTTP stub -- no dependencies,
// no network, no Discord. send-digest.js picks its transport from the webhook
// URL's protocol, which is what makes the stub possible.

const { test } = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');

const SCRIPT = path.join(__dirname, 'send-digest.js');
const { splitByBytes, splitByChars, JOB_SEPARATOR } = require('./send-digest.js');

/** Stub webhook. `responder(n)` returns {status, body} for the nth request. */
function startStub(responder) {
  const requests = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      requests.push({ headers: req.headers, body });
      const { status, body: resBody } = responder(requests.length);
      res.writeHead(status, { 'Content-Type': 'application/json' });
      res.end(resBody === undefined ? '{}' : resBody);
    });
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () =>
      resolve({
        requests,
        url: `http://127.0.0.1:${server.address().port}/api/webhooks/1/token`,
        close: () => new Promise((r) => server.close(r)),
      }),
    );
  });
}

function runScript(env) {
  return new Promise((resolve) => {
    execFile(process.execPath, [SCRIPT], { env: { ...process.env, ...env } }, (err, stdout, stderr) => {
      const line = stdout.split('\n').find((l) => l.startsWith('RESULT '));
      resolve({
        code: err ? err.code : 0,
        stdout,
        stderr,
        result: line ? JSON.parse(line.slice('RESULT '.length)) : null,
      });
    });
  });
}

function writeDigest(content) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'digest-'));
  const file = path.join(dir, 'jobs-2026-07-20.md');
  fs.writeFileSync(file, content);
  return file;
}

// `pad` fattens each job so a test can force a split without an absurd count.
const job = (n, pad = 0) =>
  `## Job ${n}\nCompany ${n} | Jakarta\n\nLink: [link](https://example.com/${n})` +
  (pad ? `\n\n**Kualifikasi**\n• ${'x'.repeat(pad)}` : '');
const digestOf = (count, pad = 0) =>
  ['**Job digest**', ...Array.from({ length: count }, (_, i) => job(i + 1, pad))].join(JOB_SEPARATOR);

test('small digest posts exactly one multipart message', async () => {
  const stub = await startStub(() => ({ status: 200, body: '{"id":"123"}' }));
  try {
    const res = await runScript({
      DISCORD_WEBHOOK_URL: stub.url,
      DIGEST_PATH: writeDigest(digestOf(3)),
      DIGEST_SUMMARY: 'Scraped 3 jobs.',
    });

    assert.equal(res.code, 0);
    assert.deepEqual(res.result, {
      mode: 'attachment',
      messages_sent: 1,
      parts: 1,
      bytes: Buffer.byteLength(digestOf(3), 'utf8'),
      failed: 0,
    });
    assert.equal(stub.requests.length, 1);

    const req = stub.requests[0];
    assert.match(req.headers['content-type'], /^multipart\/form-data; boundary=----jobdigest/);
    assert.match(req.body, /name="payload_json"/);
    assert.match(req.body, /name="files\[0\]"; filename="jobs-2026-07-20\.md"/);
    assert.match(req.body, /Content-Type: text\/markdown/);
    assert.match(req.body, /Scraped 3 jobs\./);
    assert.match(req.body, /## Job 3/);
  } finally {
    await stub.close();
  }
});

test('oversized digest splits into parts, each under budget, jobs intact', async () => {
  // 32 KiB cap minus the 8 KiB multipart reserve -> 24 KiB usable per part.
  // 60 jobs at ~600 bytes each is ~36 KiB, so it must split.
  const maxFileBytes = 32768;
  const digest = digestOf(60, 500);
  const stub = await startStub(() => ({ status: 200 }));
  try {
    const res = await runScript({
      DISCORD_WEBHOOK_URL: stub.url,
      DIGEST_PATH: writeDigest(digest),
      DIGEST_SUMMARY: 'Scraped 60 jobs.',
      MAX_FILE_BYTES: String(maxFileBytes),
    });

    assert.equal(res.code, 0);
    assert.ok(res.result.parts > 1, 'expected a split');
    assert.equal(res.result.messages_sent, res.result.parts);
    assert.equal(res.result.mode, 'attachment');
    assert.equal(stub.requests.length, res.result.parts);

    // Part naming, per-part budget, and no job cut in half.
    const total = res.result.parts;
    stub.requests.forEach((req, i) => {
      assert.match(req.body, new RegExp(`filename="jobs-2026-07-20\\.part${i + 1}of${total}\\.md"`));
      assert.ok(Buffer.byteLength(req.body, 'utf8') <= maxFileBytes, 'part exceeded the cap');
    });
    // Only part 1 carries the summary; every part is labelled.
    assert.match(stub.requests[0].body, /Scraped 60 jobs\./);
    assert.ok(!stub.requests[1].body.includes('Scraped 60 jobs.'));
    assert.match(stub.requests[1].body, /\(part 2\//);

    // Every job survives exactly once across the parts.
    const reassembled = stub.requests.map((r) => r.body).join('');
    for (let n = 1; n <= 60; n++) {
      assert.equal(
        reassembled.split(`## Job ${n}\n`).length - 1,
        1,
        `job ${n} was lost or duplicated`,
      );
    }
  } finally {
    await stub.close();
  }
});

test('429 is retried after retry_after, then succeeds', async () => {
  const stub = await startStub((n) =>
    n === 1 ? { status: 429, body: '{"retry_after":0.1}' } : { status: 200 },
  );
  try {
    const res = await runScript({
      DISCORD_WEBHOOK_URL: stub.url,
      DIGEST_PATH: writeDigest(digestOf(2)),
      DIGEST_SUMMARY: 'Scraped 2 jobs.',
    });

    assert.equal(res.code, 0);
    assert.equal(stub.requests.length, 2);
    assert.equal(res.result.mode, 'attachment');
    assert.equal(res.result.messages_sent, 1);
  } finally {
    await stub.close();
  }
});

test('persistent 500 falls back to inline messages under MAX_CHARS', async () => {
  const maxChars = 400;
  // Uploads are multipart; inline posts are JSON. This stub fails every upload
  // and accepts every inline post -- exactly the degraded path under test. It
  // needs the request headers to tell them apart, which startStub doesn't pass.
  const requests = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      requests.push({ headers: req.headers, body });
      const isUpload = (req.headers['content-type'] || '').startsWith('multipart/');
      res.writeHead(isUpload ? 500 : 200, { 'Content-Type': 'application/json' });
      res.end('{}');
    });
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const url = `http://127.0.0.1:${server.address().port}/api/webhooks/1/token`;

  try {
    const res = await runScript({
      DISCORD_WEBHOOK_URL: url,
      DIGEST_PATH: writeDigest(digestOf(12)),
      DIGEST_SUMMARY: 'Scraped 12 jobs.',
      MAX_CHARS: String(maxChars),
    });

    assert.equal(res.result.mode, 'inline');
    assert.equal(res.result.failed, 0);
    assert.equal(res.code, 0);

    const inline = requests.filter((r) => !(r.headers['content-type'] || '').startsWith('multipart/'));
    assert.ok(inline.length > 1, 'expected the fallback to chunk');
    for (const req of inline) {
      assert.ok(JSON.parse(req.body).content.length <= 2000);
    }
    // Summary rides the first fallback message only.
    assert.match(JSON.parse(inline[0].body).content, /Scraped 12 jobs\./);
  } finally {
    await new Promise((r) => server.close(r));
  }
});

test('split budget counts bytes, not characters', () => {
  // Emoji and accented Indonesian text: 1 char, multiple bytes.
  const block = '## Pengalaman 🚀 kerja — Jakarta';
  assert.ok(Buffer.byteLength(block, 'utf8') > block.length);

  const markdown = Array.from({ length: 10 }, () => block).join(JOB_SEPARATOR);
  const budget = 120;
  for (const chunk of splitByBytes(markdown, budget)) {
    assert.ok(
      Buffer.byteLength(chunk, 'utf8') <= budget,
      `chunk of ${Buffer.byteLength(chunk, 'utf8')} bytes exceeded ${budget}`,
    );
  }
});

test('a single oversized job block is truncated, not dropped', () => {
  const huge = '## Huge\n' + 'x'.repeat(5000);
  const chunks = splitByBytes(huge, 500);
  assert.equal(chunks.length, 1);
  assert.ok(Buffer.byteLength(chunks[0], 'utf8') <= 500);
  assert.match(chunks[0], /…$/);
  assert.match(chunks[0], /^## Huge/);
});

test('splitByChars keeps every chunk under the char cap', () => {
  const chunks = splitByChars(digestOf(30), 300);
  assert.ok(chunks.length > 1);
  for (const chunk of chunks) assert.ok(chunk.length <= 300);
});
