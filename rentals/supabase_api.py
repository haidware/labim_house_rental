from functools import lru_cache
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from supabase import create_client


@lru_cache(maxsize=1)
def admin_client():
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise ImproperlyConfigured(
            "Configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
        )
    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )


def auth_client():
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise ImproperlyConfigured(
            "Configure SUPABASE_URL and SUPABASE_ANON_KEY."
        )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


def rows(table, *, limit=1000, **filters):
    query = admin_client().table(table).select("*").limit(limit)
    for column, value in filters.items():
        query = query.eq(column, value)
    return query.execute().data or []


def row_by_id(table, row_id):
    result = rows(table, id=row_id)
    return result[0] if result else None


def insert(table, values):
    result = (
        admin_client()
        .table(table)
        .insert(values)
        .select("*")
        .execute()
        .data
    )
    return result[0] if result else None


def update(table, row_id, values):
    result = (
        admin_client()
        .table(table)
        .update(values)
        .eq("id", row_id)
        .select("*")
        .execute()
        .data
    )
    return result[0] if result else None


def owner_profile(owner_id):
    result = rows("rental_api_owner_profiles", user_id=owner_id, limit=1)
    return result[0] if result else None


def owner_listings(owner_id):
    return rows("rental_listings", owner_auth_id=owner_id, limit=500)


def public_listings():
    result = (
        admin_client()
        .table("rental_listings")
        .select("*")
        .eq("status", "published")
        .eq("category", "home")
        .eq("transaction_type", "rent")
        .order("updated_at", desc=True)
        .limit(500)
        .execute()
        .data
    ) or []
    listing_ids = [listing["id"] for listing in result]
    photos_by_listing = {}
    if listing_ids:
        photos = (
            admin_client()
            .table("rental_listing_photos")
            .select("*")
            .in_("listing_id", listing_ids)
            .order("position")
            .execute()
            .data
        ) or []
        for photo in photos:
            image_url = photo.get("image") or ""
            if urlsplit(image_url).scheme == "https":
                photos_by_listing.setdefault(photo["listing_id"], []).append(photo)
    for listing in result:
        listing["photos"] = photos_by_listing.get(listing["id"], [])
        listing["primary_photo"] = (
            listing["photos"][0] if listing["photos"] else None
        )
        annual_rent = listing.get("annual_rent") or 0
        listing["monthly_rent"] = (annual_rent + 11) // 12
    return result


def listing_by_slug(slug, *, published_only=False):
    query = admin_client().table("rental_listings").select("*").eq("slug", slug)
    if published_only:
        query = query.eq("status", "published")
    results = query.limit(1).execute().data or []
    return results[0] if results else None


def upload_listing_photo(file, listing_id, position):
    bucket = settings.SUPABASE_STORAGE_BUCKET
    suffix = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
    }[file.image_format]
    path = f"rental-listings/{listing_id}/{position}-{uuid4().hex}{suffix}"
    storage = admin_client().storage.from_(bucket)
    storage.upload(
        path,
        file.read(),
        {
            "content-type": f"image/{file.image_format.lower()}",
            "upsert": "true",
        },
    )
    return {
        "listing_id": listing_id,
        "image": storage.get_public_url(path),
        "caption": "",
        "position": position,
    }
