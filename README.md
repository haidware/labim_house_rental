# Labim House Rental Admin

Standalone Django project for the Rooms house-rental marketplace and its listing
administration. Homeowners submit a property address, property type and phone
number; Rooms contacts them to arrange an in-person verification visit and
handles photos and listing details. Land/property owners can still request
accounts to manage their listings.

## Features

- Flutter web Rooms marketplace showing only Haidware-reviewed homes available for rent.
- Home search by location, city, and maximum monthly rent.
- Public viewing requests saved for staff follow-up.
- Home rental requests require property details and owner agreement to a
  verification visit; Rooms manages the visit, photos and listing setup.
- Staff track new home requests, contact owners, schedule visits and record
  verification status in the Supabase-backed staff portal.
- Owner account requests remain pending until Haidware approves them in the
  staff portal.
- Owners manage only their own listings and can save drafts or submit listings for review.
- Haidware staff control publication; owners cannot publish listings themselves.
- House-owner listings support rent. Land/property-owner listings support rent or sale.
- Listing creation and editing, review/draft/published/rented/archived status,
  address, location, rent or sale price, and home details.
- Multiple property photos per listing.
- Inspection-request tracking with status, preferred date, contact details, and
  private staff notes.
- Supabase REST API and Storage for rental data, with SQLite retained for local
  development and Django compatibility.

## Run locally

Build the Flutter web app first, then start Django. Django serves the compiled
Flutter client and its public rental API from the same origin; the Django
staff/owner portals remain available.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
Set-Location flutter_app
flutter pub get
flutter build web --base-href=/
Set-Location ..
python manage.py runserver
```

With the rental Supabase REST environment variables set in `.env`, open
http://127.0.0.1:8000/ to browse published homes, request a viewing, or submit
a home for Rooms to verify. Flutter calls Django's same-origin
`/api/public/` endpoints; Django continues to access the rental Supabase
project and handles validation, CSRF protection, and writes. Staff follow up
on property visit requests, prepare and publish verified listings, and manage
viewing requests in the staff portal. Land/property owners can apply for an
account and wait for Haidware approval; approved owners can manage listings on
their role-specific dashboard.
For the local SQLite fallback only, create a Django staff account with
`python manage.py createsuperuser` to use Django admin. REST mode uses the
`RENTAL_STAFF_USERNAME` and `RENTAL_STAFF_PASSWORD` values instead.

## Supabase REST setup

Use the dedicated rental Supabase project, separate from the hotel-booking
database. This app uses Supabase Auth, PostgREST, and Storage APIs; it no longer
uses a Supabase PostgreSQL connection URI or `DATABASE_URL` for application
data. The `SUPABASE_SERVICE_ROLE_KEY` stays on the Django server and is never
rendered into HTML or sent to browser JavaScript.

1. In the rental project's SQL Editor, run
   `supabase/migrations/0002_rest_api_backend.sql`. It creates the API-backed
   listing, photo, viewing-request, owner-request, and owner-profile schema,
   restricts public data access with RLS, configures the public photo bucket,
   and creates owner profiles when Supabase Auth receives an owner sign-up.
2. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY` (or `SUPABASE_PUBLISHABLE_KEY`),
   and `SUPABASE_SERVICE_ROLE_KEY` (or `SUPABASE_SECRET_KEY`) in the server's
   private environment variables. The publishable/anon key supports owner
   sign-in; all database writes are made by the server with the secret/service
   key. Never put that secret key in a template, JavaScript bundle, or public
   repository.
3. Set `RENTAL_STAFF_USERNAME` and `RENTAL_STAFF_PASSWORD` to a unique staff
   login. Use a long, randomly generated password and keep it private. Staff
   use the custom portal at `/staff/records/`; the Django admin login is no
   longer used in REST mode.
4. Owners request an account through the existing form, confirm their account
   according to the Supabase Auth project's email-confirmation settings, and
   wait for staff approval before signing in. Staff can approve owners and
   manage listings and requests in the portal.

Apply the SQL migration before configuring the API variables. In REST mode,
the SQLite database is not the source of rental data. It is retained for local
Django compatibility and deployment migrations only; sessions use signed
cookies. Existing rental listing and request rows in the dedicated Supabase
project are retained by the additive SQL migration. Existing Django owner
passwords cannot be imported into Supabase Auth; owners will need to submit a
new account request. Existing photo records are retained, but image files
stored only on a Django/Render filesystem are not copied to Supabase Storage;
staff must upload available originals again through the listing editor.

For local development, copy `.env.example` to `.env`, set the same Supabase
values and a staff username/password to exercise REST mode. Without all three
Supabase API variables, the legacy local SQLite workflow remains available for
development and tests; in that mode the root page uses the legacy Django
template instead of the Flutter site.

## Production configuration

Deploy this repository as a Docker web service so the Flutter build stage can
compile the public web client and package it with Django. The included
`Dockerfile` uses Flutter 3.35.1 to build the web app; Django serves that build
at `/` and serves the bundle assets. Do not run Flutter's development server
in production. Configure the service's health check at `/` or another
application route.

Set a persistent random `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`,
`SUPABASE_URL`, either `SUPABASE_ANON_KEY` or `SUPABASE_PUBLISHABLE_KEY`,
either `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`,
`RENTAL_STAFF_USERNAME`, and `RENTAL_STAFF_PASSWORD` in Render's private
environment variables. Use a long, unique staff password. The app refuses to
start in Render when any required Supabase or staff variable is missing. Do not
configure `DATABASE_URL` for this app. On Render, the service
automatically adds `RENDER_EXTERNAL_HOSTNAME` to
`ALLOWED_HOSTS` and the matching HTTPS CSRF trusted origin. A custom domain
must also be included in `DJANGO_ALLOWED_HOSTS` and
`DJANGO_CSRF_TRUSTED_ORIGINS`.

The container start command runs `python manage.py migrate --noinput`; those
migrations use local SQLite, not Supabase Postgres. Rental photos are uploaded
to the Supabase Storage bucket created by the SQL migration.
