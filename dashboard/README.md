# Job Boat dashboard

The dashboard is a static Vite/React app suitable for Vercel Hobby. Supabase supplies email sign-in, Postgres, and row-level access rules. This chat remains the planning and review channel; it is not an API or a background worker. The separate Python collector and Playwright browser need an always-on worker host later.

Modules: overview, fast income, career roles, approvals, CV library, sources, preferences, and activity. Approve records a decision; it does not submit to a job site. Every listing displays freshness. A page returning HTTP 200 alone is not proof that applications remain open.

## Deploy

1. Create a private Supabase project. Run `supabase/schema.sql` once in its SQL editor. Enable email OTP in Auth and restrict permitted redirect URLs to the Vercel domain.
2. Import this repository into Vercel. Set the root directory to `dashboard`; the build command is `npm run build` and output directory is `dist`.
3. Set only `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in Vercel. The anon key is intended for the browser; row-level security protects records. Never set a service role key in Vercel frontend variables.
4. Deploy and sign in with the career email. Find the user UUID in Supabase Authentication > Users.
5. In the private cloud worker environment, set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `JOB_BOAT_OWNER_ID` securely; run `python sync_dashboard.py` from the repository root. This transfers the 241 job records and eight extracted CV texts. The original document bytes stay in the private local database. Do not paste keys or CVs into chat.

The dashboard intentionally has no background job collector. A later worker will sync fresh feeds and browser verification to Supabase on a schedule. Free Vercel hosting can serve the UI, but it is not a 24/7 browser worker.

## Local check

Run `npm ci && npm run build` in this directory. Without Supabase variables, the rendered app shows a connection setup state; it does not expose personal data.
