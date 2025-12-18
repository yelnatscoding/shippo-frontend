# Vercel Postgres Setup Guide

## Step 1: Create Postgres Database

Since the CLI is having issues, create via the Vercel Dashboard:

1. Go to https://vercel.com/dashboard
2. Navigate to your `shippo-frontend` project
3. Go to the **Storage** tab
4. Click **Create Database**
5. Select **Postgres**
6. Name it: `shippo-labels`
7. Select region closest to you
8. Click **Create**

## Step 2: Connect Database to Project

After creating the database:

1. In the database settings, click **Connect Project**
2. Select your `shippo-frontend` project
3. This will automatically add environment variables:
   - `POSTGRES_URL`
   - `POSTGRES_PRISMA_URL`
   - `POSTGRES_URL_NON_POOLING`
   - `POSTGRES_USER`
   - `POSTGRES_HOST`
   - `POSTGRES_PASSWORD`
   - `POSTGRES_DATABASE`

## Step 3: Pull Environment Variables Locally

```bash
cd shippo-frontend
vercel env pull .env.local
```

This downloads all environment variables (including the new Postgres ones) to `.env.local`

## Step 4: Test Locally

```bash
vercel dev --listen 3000
```

Visit http://localhost:3000 and purchase a test label. Check the history tab to confirm it's being saved to Postgres.

## Step 5: Deploy

```bash
vercel --prod
```

## Database Schema

The `label_history` table is automatically created on first use with this schema:

```sql
CREATE TABLE label_history (
    id SERIAL PRIMARY KEY,
    tracking_number VARCHAR(255) NOT NULL,
    carrier VARCHAR(100) NOT NULL,
    service VARCHAR(255),
    cost DECIMAL(10, 2),
    currency VARCHAR(10) DEFAULT 'USD',
    provider VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    from_address JSONB,
    to_address JSONB,
    google_drive_link TEXT,
    google_drive_file_id VARCHAR(255),
    signature_confirmation VARCHAR(50)
);
```

## Verify Database is Working

After deployment, check the response from `/api/history`:

```bash
curl https://your-app.vercel.app/api/history
```

Look for `"storage_type": "postgres"` in the response to confirm it's using Postgres.

## Fallback Behavior

If Postgres is not available (missing env vars), the system automatically falls back to JSON file storage (which won't persist in Vercel, but works for local dev).

## Manual Database Access

To connect directly to your database:

1. Get connection string from Vercel dashboard → Storage → shippo-labels → .env.local tab
2. Use psql:
   ```bash
   psql "postgres://user:pass@host/database?sslmode=require"
   ```

3. Query labels:
   ```sql
   SELECT * FROM label_history ORDER BY created_at DESC LIMIT 10;
   ```
