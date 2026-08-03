#!/usr/bin/env node
// Posts a run's job digest to a Discord webhook as a markdown attachment.
//
// The bot prompt (prompts/scrape-and-post.md) formats jobs into one markdown
// file and hands the path here. This script owns everything after that: byte
// accounting, splitting oversized digests, the multipart upload, rate-limit
// retries, and the inline-message fallback when uploads keep failing.
//
// It lives in code rather than in the prompt because all of it is arithmetic
// the LLM would otherwise have to do by hand -- and because Step 6 writes the
// resulting counts to MongoDB, where a recalled number is a wrong number.
//
// Env:
//   DISCORD_WEBHOOK_URL  required, https://discord.com/api/webhooks/<id>/<token>
//   DIGEST_PATH          required, path to the markdown digest
//   DIGEST_SUMMARY       message body (summary + error diagnostic); may be empty
//   MAX_FILE_BYTES       upload cap, default 10 MiB (Discord non-boosted)
//   MAX_CHARS            per-message cap for the inline fallback, default 1900
//
// Prints one `RESULT {...}` line on stdout. Exits 0 when everything landed.

const fs = require('fs');
const path = require('path');
const { URL } = require('url');

// Discord's upload cap for a non-boosted guild. Boost tiers 2/3 raise it to
// 50/100 MiB, hence the env knob.
const DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024;
// Headroom for the multipart preamble, boundary and payload_json -- Discord
// caps the whole request, not just the file part.
const MULTIPART_OVERHEAD = 8192;
// Floor for the per-part budget, so a bad MAX_FILE_BYTES degrades to many small
// parts instead of to an empty digest.
const MIN_BUDGET_BYTES = 4096;
const DEFAULT_MAX_CHARS = 1900;
// Job blocks are joined with this in the digest; splits only ever happen here.
const JOB_SEPARATOR = '\n\n---\n\n';

const MAX_UPLOAD_ATTEMPTS = 3;
const SERVER_ERROR_BACKOFF_MS = 2000;
const INTER_MESSAGE_PAUSE_MS = 1000;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function intFromEnv(name, fallback) {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

/** Split markdown into chunks of at most `budget` BYTES, never cutting a job.
 *
 * Byte length, not string length: the digest is Indonesian text with emoji, so
 * a char count under-reports what Discord actually weighs.
 */
function splitByBytes(markdown, budget) {
  if (Buffer.byteLength(markdown, 'utf8') <= budget) return [markdown];

  const blocks = markdown.split(JOB_SEPARATOR);
  const sepBytes = Buffer.byteLength(JOB_SEPARATOR, 'utf8');
  const chunks = [];
  let current = [];
  let currentBytes = 0;

  const flush = () => {
    if (current.length) {
      chunks.push(current.join(JOB_SEPARATOR));
      current = [];
      currentBytes = 0;
    }
  };

  for (const block of blocks) {
    const blockBytes = Buffer.byteLength(block, 'utf8');

    // A single block over budget can't be packed with anything -- emit it alone,
    // truncated. Only reachable with a pathological job description.
    if (blockBytes > budget) {
      flush();
      chunks.push(truncateToBytes(block, budget));
      continue;
    }

    const added = current.length ? sepBytes + blockBytes : blockBytes;
    if (currentBytes + added > budget) flush();
    current.push(block);
    currentBytes += current.length === 1 ? blockBytes : sepBytes + blockBytes;
  }

  flush();
  return chunks;
}

/** Cut a string to `budget` bytes without splitting a UTF-8 sequence. */
function truncateToBytes(text, budget) {
  const marker = '\n…';
  const room = budget - Buffer.byteLength(marker, 'utf8');
  const buf = Buffer.from(text, 'utf8');
  if (buf.length <= room) return text;
  // toString on a sliced buffer can leave a partial code point at the tail;
  // the replacement char it produces is stripped below.
  return buf.subarray(0, room).toString('utf8').replace(/�+$/, '') + marker;
}

/** Chunk markdown into at most `maxChars` CHARACTERS for inline `content` posts.
 *
 * Discord measures message content in characters, not bytes -- unlike uploads.
 */
function splitByChars(markdown, maxChars) {
  const blocks = markdown.split(JOB_SEPARATOR);
  const chunks = [];
  let current = [];
  let currentChars = 0;

  const flush = () => {
    if (current.length) {
      chunks.push(current.join(JOB_SEPARATOR));
      current = [];
      currentChars = 0;
    }
  };

  for (const block of blocks) {
    if (block.length > maxChars) {
      flush();
      chunks.push(block.slice(0, maxChars - 1) + '…');
      continue;
    }
    const added = current.length ? JOB_SEPARATOR.length + block.length : block.length;
    if (currentChars + added > maxChars) flush();
    current.push(block);
    currentChars += added;
  }

  flush();
  return chunks;
}

function request(webhookUrl, { headers, body }) {
  const u = new URL(webhookUrl);
  // http:// is only ever a local test stub; production is always https.
  const transport = require(u.protocol === 'http:' ? 'http' : 'https');

  return new Promise((resolve, reject) => {
    const req = transport.request(
      {
        hostname: u.hostname,
        port: u.port || undefined,
        path: u.pathname + u.search,
        method: 'POST',
        headers: { ...headers, 'Content-Length': body.length },
      },
      (res) => {
        let data = '';
        res.on('data', (c) => (data += c));
        res.on('end', () => resolve({ status: res.statusCode, body: data }));
      },
    );
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function multipartBody(filename, content, payload) {
  const boundary = `----jobdigest${Date.now()}${Math.random().toString(16).slice(2)}`;
  const preamble = Buffer.from(
    `--${boundary}\r\n` +
      'Content-Disposition: form-data; name="payload_json"\r\n' +
      'Content-Type: application/json\r\n\r\n' +
      `${JSON.stringify(payload)}\r\n` +
      `--${boundary}\r\n` +
      `Content-Disposition: form-data; name="files[0]"; filename="${filename}"\r\n` +
      'Content-Type: text/markdown\r\n\r\n',
    'utf8',
  );
  const epilogue = Buffer.from(`\r\n--${boundary}--\r\n`, 'utf8');
  return {
    // Buffer.concat so Content-Length matches the bytes on the wire exactly.
    body: Buffer.concat([preamble, Buffer.from(content, 'utf8'), epilogue]),
    headers: { 'Content-Type': `multipart/form-data; boundary=${boundary}` },
  };
}

function retryAfterMs(responseBody) {
  try {
    const parsed = JSON.parse(responseBody);
    if (typeof parsed.retry_after === 'number') {
      return Math.ceil(parsed.retry_after * 1000);
    }
  } catch {
    // Non-JSON 429 body: fall through to the default below.
  }
  return SERVER_ERROR_BACKOFF_MS;
}

/** POST with 429/5xx retries. Resolves {ok, status, body, attempts}. */
async function postWithRetries(webhookUrl, buildRequest) {
  let last = { status: 0, body: '' };

  for (let attempt = 1; attempt <= MAX_UPLOAD_ATTEMPTS; attempt++) {
    try {
      last = await request(webhookUrl, buildRequest());
    } catch (err) {
      last = { status: 0, body: String(err && err.message ? err.message : err) };
      if (attempt < MAX_UPLOAD_ATTEMPTS) await sleep(SERVER_ERROR_BACKOFF_MS);
      continue;
    }

    if (last.status >= 200 && last.status < 300) {
      return { ok: true, ...last, attempts: attempt };
    }
    if (last.status === 429 && attempt < MAX_UPLOAD_ATTEMPTS) {
      await sleep(retryAfterMs(last.body));
      continue;
    }
    if (last.status >= 500 && attempt < MAX_UPLOAD_ATTEMPTS) {
      await sleep(SERVER_ERROR_BACKOFF_MS);
      continue;
    }
    break;
  }

  return { ok: false, ...last, attempts: MAX_UPLOAD_ATTEMPTS };
}

/** Last-resort path: post the markdown as plain messages, old-batching style. */
async function sendInline(webhookUrl, markdown, summary, maxChars) {
  const chunks = splitByChars(markdown, maxChars);
  let sent = 0;
  let failed = 0;

  for (let i = 0; i < chunks.length; i++) {
    // The summary rides on the first message only; a repeat on every chunk is
    // the noise this whole change exists to remove.
    const content = i === 0 && summary ? `${summary}\n\n${chunks[i]}` : chunks[i];
    const body = Buffer.from(JSON.stringify({ content: content.slice(0, 2000) }), 'utf8');
    const result = await postWithRetries(webhookUrl, () => ({
      headers: { 'Content-Type': 'application/json' },
      body,
    }));

    if (result.ok) sent++;
    else {
      failed++;
      console.error(`inline chunk ${i + 1}/${chunks.length} failed: ${result.status} ${result.body}`);
    }
    if (i < chunks.length - 1) await sleep(INTER_MESSAGE_PAUSE_MS);
  }

  return { sent, failed };
}

async function main() {
  const webhookUrl = process.env.DISCORD_WEBHOOK_URL;
  const digestPath = process.env.DIGEST_PATH;
  const summary = process.env.DIGEST_SUMMARY || '';

  if (!webhookUrl) throw new Error('DISCORD_WEBHOOK_URL is not set');
  if (!digestPath) throw new Error('DIGEST_PATH is not set');

  const maxFileBytes = intFromEnv('MAX_FILE_BYTES', DEFAULT_MAX_FILE_BYTES);
  const maxChars = intFromEnv('MAX_CHARS', DEFAULT_MAX_CHARS);
  // Clamp: a MAX_FILE_BYTES smaller than the multipart overhead would yield a
  // negative budget, and every job would be truncated to nothing.
  const budget = Math.max(maxFileBytes - MULTIPART_OVERHEAD, MIN_BUDGET_BYTES);
  if (maxFileBytes - MULTIPART_OVERHEAD < MIN_BUDGET_BYTES) {
    console.error(`MAX_FILE_BYTES=${maxFileBytes} is too small; using a ${MIN_BUDGET_BYTES}-byte budget`);
  }

  const markdown = fs.readFileSync(digestPath, 'utf8');
  const bytes = Buffer.byteLength(markdown, 'utf8');
  const parts = splitByBytes(markdown, budget);

  const baseName = path.basename(digestPath, '.md');
  let sent = 0;
  let failed = 0;
  let attachmentParts = 0;
  let inlineParts = 0;

  for (let i = 0; i < parts.length; i++) {
    const filename =
      parts.length === 1 ? `${baseName}.md` : `${baseName}.part${i + 1}of${parts.length}.md`;
    const suffix = parts.length === 1 ? '' : `(part ${i + 1}/${parts.length})`;
    const content = [i === 0 ? summary : '', suffix].filter(Boolean).join('\n');

    const result = await postWithRetries(webhookUrl, () =>
      multipartBody(filename, parts[i], { content }),
    );

    if (result.ok) {
      sent++;
      attachmentParts++;
    } else {
      console.error(`upload of ${filename} failed: ${result.status} ${result.body}`);
      const fallback = await sendInline(webhookUrl, parts[i], content, maxChars);
      sent += fallback.sent;
      failed += fallback.failed;
      if (fallback.sent > 0) inlineParts++;
    }

    if (i < parts.length - 1) await sleep(INTER_MESSAGE_PAUSE_MS);
  }

  let mode = 'attachment';
  if (attachmentParts === 0) mode = 'inline';
  else if (inlineParts > 0) mode = 'mixed';

  // Step 6 of the prompt lifts these numbers straight into the Mongo patch.
  console.log(
    'RESULT ' +
      JSON.stringify({ mode, messages_sent: sent, parts: parts.length, bytes, failed }),
  );
  process.exitCode = failed > 0 ? 1 : 0;
}

if (require.main === module) {
  main().catch((err) => {
    console.error(`send-digest failed: ${err.message}`);
    console.log('RESULT ' + JSON.stringify({ mode: 'none', messages_sent: 0, parts: 0, bytes: 0, failed: 1 }));
    process.exitCode = 1;
  });
}

module.exports = { splitByBytes, splitByChars, truncateToBytes, JOB_SEPARATOR };
