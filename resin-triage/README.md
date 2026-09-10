# RESIN Daily Triage Microservice

A standalone, scheduled Node.js worker that curates personalized daily academic briefings for registered users of **RESIN**.

---

## 🎯 How It Works

1. **User Profile Aggregation**:
   - Connects to Supabase PostgreSQL using connection pooling (`pg`).
   - Retrieves all active users, their custom research topics (`users.topics`), and the list of papers currently saved in their libraries.

2. **OpenAlex Candidate Harvesting**:
   - Queries OpenAlex for high-quality scientific literature published within the last 7 days matching the user's research topics.
   - Filters out non-academic or low-signal publications using citation count thresholds and repository sanity checks.

3. **Gemini LLM Curation**:
   - Sends the retrieved candidate set and user library context to Google Gemini.
   - Formulates a structured JSON selection of the top 3 highest-impact papers with explicit reasoning connecting back to the user's existing saved research.

4. **Database Upsert**:
   - Upserts the curated picks into the `daily_triage` table under `triage_date = CURRENT_DATE`.
   - The frontend's `DailyTriageSection` displays these as the **#1 Pick**, **#2 Pick**, and **#3 Pick** cards.

---

## ⚙️ Setup & Execution

### 1. Installation
```bash
cd resin-triage
npm install
```

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in the credentials:
```bash
GEMINI_API_KEY="your-gemini-api-key"
SUPABASE_DB_URL="postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres"
OPENALEX_EMAIL="your-email@example.com"
```

### 3. Run Manually or via Cron
```bash
node daily-triage.js
```
Can be scheduled as a daily cron job (e.g., at 06:00 UTC) via GitHub Actions, AWS EventBridge, or Linux crontab.
