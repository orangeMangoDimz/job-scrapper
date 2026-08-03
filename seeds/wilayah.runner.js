#!/usr/bin/env node
// Run: MONGO_URI="mongodb://admin:<pass>@127.0.0.1:27017/?authSource=admin" node seeds/wilayah.runner.js

const { MongoClient } = require('mongodb');
const fs = require('fs');
const path = require('path');

const MONGO_URI = process.env.MONGO_URI;
if (!MONGO_URI) {
  console.error('MONGO_URI env var required');
  process.exit(1);
}

const DB_NAME = 'job-scraper';
const COLL = 'wilayah';
const EXPECTED = 91599;

async function main() {
  const src = fs.readFileSync(path.join(__dirname, 'wilayah.mongosh.js'), 'utf8');

  const startIdx = src.indexOf('const BATCHES = [') + 'const BATCHES = '.length;
  const endIdx = src.indexOf('];\n\nlet inserted') + 1;
  const BATCHES = JSON.parse(src.slice(startIdx, endIdx));

  const client = new MongoClient(MONGO_URI);
  await client.connect();
  
  console.log(`[wilayah] connected to ${MONGO_URI} with user ${client.options.auth?.username}`);

  const coll = client.db(DB_NAME).collection(COLL);

  console.log(`[wilayah] dropping ${DB_NAME}.${COLL} ...`);
  await coll.drop().catch(() => {});

  let inserted = 0;
  for (let i = 0; i < BATCHES.length; i++) {
    const res = await coll.insertMany(BATCHES[i], { ordered: false });
    inserted += Object.keys(res.insertedIds).length;
    console.log(`[wilayah] batch ${i + 1}/${BATCHES.length} -> ${inserted}/${EXPECTED}`);
  }

  await coll.createIndex({ nama: 1 });

  const total = await coll.countDocuments();
  console.log(`[wilayah] inserted=${inserted} countDocuments=${total} expected=${EXPECTED}`);
  if (total !== EXPECTED) throw new Error(`COUNT MISMATCH: got ${total}, expected ${EXPECTED}`);
  console.log('[wilayah] OK');

  await client.close();
}

main().catch(e => { console.error(e); process.exit(1); });
