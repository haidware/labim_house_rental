# Labim House Rental Admin

Standalone Django project for the Rooms house-rental marketplace and its listing
administration. Homeowners submit a property address, property type and phone
number; Rooms contacts them to arrange an in-person verification visit and
handles photos and listing details. Land/property owners can still request
accounts to manage their listings.

## Features

- Public Rooms marketplace showing only Haidware-reviewed homes available for rent.
- Home search by location, city, and maximum monthly rent.
- Public viewing requests saved for staff follow-up.
- Home rental requests require property details and owner agreement to a
  verification visit; Rooms manages the visit, photos and listing setup.
- Staff track new home requests, contact owners, schedule visits and record
  verification status in Django admin.
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

Open http://127.0.0.1:8000/ to browse published homes, request a viewing, or
submit a home for Rooms to verify. Staff follow up on property visit requests,
prepare and publish verified listings, and manage viewing requests in Django
admin. Land/property owners can apply for an account and wait for Haidware
approval; approved owners can manage listings on their role-specific dashboard.

## Supabase setup

Use the dedicated rental Supabase project, separate from the hotel-booking
database. The Supabase project URL (for example,
`https://<project-ref>.supabase.co`) is not the PostgreSQL connection URI Django
needs. In the project's Database settings, copy the PostgreSQL pooler connection
URI into the private `DATABASE_URL` environment variable and append
`sslmode=require` if it is not already present. For example:

```text
postgresql://postgres.<project-ref>:<password>@<pooler-host>:6543/postgres?sslmode=require
```

Never commit `.env` or expose database credentials in public frontend code.
Then run `python manage.py migrate`, apply
`supabase/migrations/0001_public_listing_read.sql` in the Supabase SQL Editor,
and create the first staff account with `python manage.py createsuperuser`.
Django migrations create the listing, photo, inspection-request, property
listing-request, staff-profile, and owner-profile tables in this project's
database. The SQL migration enables
read-only public access to published listings and their photos for a separate
public Supabase client, if one is needed. The current Rooms page reads listings
and submits property and viewing requests through Django; these requests,
staff profiles, and owner profiles are not accessible to public Supabase
clients.

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
