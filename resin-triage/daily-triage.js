import 'dotenv/config';
import pkg from 'pg';
const { Client } = pkg;

const GEMINI_KEY = process.env.GEMINI_API_KEY;
const DB_URL = process.env.SUPABASE_DB_URL;
const OPENALEX_EMAIL = process.env.OPENALEX_EMAIL || '';

if (!GEMINI_KEY || !DB_URL) {
  console.error('Missing GEMINI_API_KEY or SUPABASE_DB_URL. Copy .env.example to .env and fill it in.');
  process.exit(1);
}

function reconstructAbstract(invertedIndex) {
  if (!invertedIndex) return '';
  const words = [];
  for (const [word, positions] of Object.entries(invertedIndex)) {
    for (const pos of positions) words[pos] = word;
  }
  return words.join(' ');
}

function isLikelySpam(paper) {
  const doi = paper.ids?.doi || '';
  const isZenodoOnly = doi.includes('zenodo');
  const suspiciousCitations = (paper.cited_by_count || 0) > 20;
  return isZenodoOnly && suspiciousCitations;
}

async function fetchOpenAlexCandidates(topics) {
  const url = new URL('https://api.openalex.org/works');
  url.searchParams.set('search', topics.join(' OR '));
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
  url.searchParams.set('filter', `from_publication_date:${weekAgo}`);
  url.searchParams.set('per-page', '10');
  url.searchParams.set('select', 'id,title,abstract_inverted_index,publication_year,cited_by_count,ids,open_access');
  if (OPENALEX_EMAIL) url.searchParams.set('mailto', OPENALEX_EMAIL);

  const res = await fetch(url);
  if (!res.ok) {
    console.warn(`  OpenAlex request failed (${res.status}), continuing with 0 papers`);
    return [];
  }
  const data = await res.json();
  return (data.results || [])
    .filter(p => p.abstract_inverted_index)
    .filter(p => !isLikelySpam(p));
}

async function callGemini(prompt) {
  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { responseMimeType: 'application/json' }
      })
    }
  );
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Gemini API error ${res.status}: ${errText}`);
  }
  const data = await res.json();
  const raw = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!raw) throw new Error(`Gemini returned no text: ${JSON.stringify(data)}`);
  return JSON.parse(raw);
}

async function triageForUser(client, user) {
  console.log(`\nTriaging user ${user.id} (topics: ${user.topics.join(', ')})`);

  const feedRes = await client.query(
    `SELECT id, source, title, url, summary, published_at
     FROM feed_items
     WHERE created_at > now() - interval '1 day'
       AND topics && $1::text[]
     ORDER BY published_at DESC LIMIT 25`,
    [user.topics]
  );
  console.log(`  feed_items candidates: ${feedRes.rows.length}`);

  const oaPapers = await fetchOpenAlexCandidates(user.topics);
  console.log(`  openalex candidates: ${oaPapers.length}`);

  const libRes = await client.query(
    `SELECT p.title, p.year, p.authors, ps.problem, ps.method, ps.findings, ps.significance
     FROM user_papers up
     JOIN papers p ON p.id = up.paper_id
     LEFT JOIN paper_summaries ps ON ps.paper_id = p.id
     WHERE up.user_id = $1
     ORDER BY up.saved_at DESC LIMIT 30`,
    [user.id]
  );
  console.log(`  library context: ${libRes.rows.length} saved papers`);

  const candidates = [
    ...feedRes.rows.map(f => ({
      id: f.id, source: f.source, title: f.title,
      summary: f.summary, url: f.url, type: 'feed_item'
    })),
    ...oaPapers.map(p => ({
      id: p.ids?.doi || p.id, source: 'openalex',
      title: p.title, summary: reconstructAbstract(p.abstract_inverted_index),
      url: p.open_access?.oa_url || p.ids?.doi || p.id, type: 'paper'
    }))
  ];

  if (candidates.length === 0) {
    console.log('  No candidates found today, skipping.');
    return;
  }

  const prompt = `You are a research triage assistant. Given the user's saved paper
library below, and a list of new candidate items, pick the TOP 3 items most worth
reading today. For each, give a one-line reason that references a SPECIFIC saved
paper if relevant (e.g. "This extends the method in [saved paper title]").

Return ONLY valid JSON, no markdown, no preamble, in this exact shape:
{"items": [{"id": "...", "source": "...", "title": "...", "url": "...", "reason": "..."}]}

USER'S LIBRARY (most recent ${libRes.rows.length} saved papers):
${JSON.stringify(libRes.rows)}

CANDIDATE ITEMS (${candidates.length}):
${JSON.stringify(candidates)}`;

  const parsed = await callGemini(prompt);
  if (!parsed.items || parsed.items.length === 0) {
    throw new Error('LLM returned no items');
  }
  console.log(`  LLM picked ${parsed.items.length} items`);

  await client.query(
    `INSERT INTO daily_triage (user_id, triage_date, items)
     VALUES ($1, CURRENT_DATE, $2::jsonb)
     ON CONFLICT (user_id, triage_date)
     DO UPDATE SET items = EXCLUDED.items, created_at = now()`,
    [user.id, JSON.stringify(parsed.items)]
  );
  console.log('  Saved to daily_triage.');
}

async function runDailyTriage() {
  const client = new Client({ connectionString: DB_URL });
  await client.connect();
  console.log('Connected to Supabase.');

  const { rows: users } = await client.query(
    `SELECT id, topics FROM users WHERE array_length(topics, 1) > 0`
  );
  console.log(`Found ${users.length} active user(s) to triage.`);

  for (const user of users) {
    try {
      await triageForUser(client, user);
    } catch (e) {
      console.error(`  FAILED for user ${user.id}:`, e.message);
      // Keep going for other users even if one fails.
    }
  }

  await client.end();
  console.log('\nDone.');
}

runDailyTriage().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
