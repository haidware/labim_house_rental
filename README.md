# Labim House Rental Admin

Standalone Django project for managing house rental listings, property photos,
and inspection requests. It provides separate house-owner and land/property-owner
dashboards, plus a Haidware staff dashboard for account and listing approval.
The public rental page at
`https://rooms-uamy.onrender.com/rental` remains a separate project and will be
connected to this project's public listing data in a later phase.

## Features

- Public role-selection page for Haidware staff, house owners, and land/property owners.
- Owner account requests remain inactive until Haidware approves them in Django admin.
- Owners manage only their own listings and can save drafts or submit listings for review.
- Haidware staff control publication; owners cannot publish listings themselves.
- House-owner listings support rent. Land/property-owner listings support rent or sale.
- Listing creation and editing, review/draft/published/rented/archived status,
  address, location, rent or sale price, and home details.
- Multiple property photos per listing.
- Inspection-request tracking with status, preferred date, contact details, and
  private staff notes.
- Local SQLite for development and PostgreSQL configuration for a dedicated
  Supabase project.

There is no public listing API in this first phase. Inspection requests are
managed in the admin and are not yet submitted by the public rental page.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ to choose a role. Haidware staff sign in with an
existing staff account; owners can request an account and wait for approval.
Staff manage account requests and publish reviewed listings in Django admin.
Approved owners can manage their own drafts and review submissions on their
role-specific dashboard.

## Supabase setup

Create a separate Supabase project for this rental admin. In its Database
settings, copy the PostgreSQL pooler connection URI into the private
`DATABASE_URL` environment variable and append `sslmode=require` if it is not
already present. For example:

```text
postgresql://postgres.<project-ref>:<password>@<pooler-host>:6543/postgres?sslmode=require
```

Never commit `.env` or expose database credentials in public frontend code.
Then run `python manage.py migrate`, apply
`supabase/migrations/0001_public_listing_read.sql` in the Supabase SQL Editor,
and create the first staff account with `python manage.py createsuperuser`.
Django migrations create the listing, photo, inspection-request, staff-profile,
and owner-profile tables in this project's database. The SQL migration enables
read-only public access to published listings and their photos; inspection
requests, staff profiles, and owner profiles remain private.

The project does not connect to the existing hotel Supabase. Configure a
separate Supabase project and credentials for rental data.

## Production configuration

Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, and
`DJANGO_CSRF_TRUSTED_ORIGINS`, as well as the Supabase Postgres `DATABASE_URL`.
On Render, the service automatically adds `RENDER_EXTERNAL_HOSTNAME` to
`ALLOWED_HOSTS` and the matching HTTPS CSRF trusted origin. A custom domain
must also be included in `DJANGO_ALLOWED_HOSTS` and
`DJANGO_CSRF_TRUSTED_ORIGINS`. Debug mode is always disabled on Render.

Set a persistent, randomly generated `DJANGO_SECRET_KEY` in Render's private
environment variables. If it is missing, the app uses a secure temporary key
and logs a warning; sessions will be invalidated when the service restarts.
Run `python manage.py migrate` during deployment and serve static/media files
using production storage. Local media storage is intended for development;
Supabase Storage integration is a follow-up before hosting property photos.
