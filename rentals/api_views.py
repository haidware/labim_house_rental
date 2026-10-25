import logging
import json
import mimetypes
import os
import secrets
from functools import wraps
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.middleware.csrf import get_token
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthApiError

from .api_forms import (
    OwnerAccountRequestForm,
    OwnerListingForm,
    PropertyListingRequestForm,
    StaffRentalListingForm,
    StaffLoginForm,
)
from .models import OwnerProfile, RentalListing
from .supabase_api import (
    admin_client,
    auth_client,
    insert,
    listing_by_slug,
    owner_listings,
    owner_profile,
    public_listings,
    row_by_id,
    rows,
    update,
    upload_listing_photo,
)
from .forms import PublicInspectionRequestForm


logger = logging.getLogger(__name__)

LISTING_STATUS_LABELS = dict(RentalListing.PublicationStatus.choices)
INSPECTION_STATUS_LABELS = dict((
    ("new", "New"),
    ("contacted", "Contacted"),
    ("scheduled", "Scheduled"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
))
OWNER_STATUS_LABELS = dict(OwnerProfile.AccountStatus.choices)
PROPERTY_REQUEST_STATUS_LABELS = {
    "new": "New request",
    "contacted": "Owner contacted",
    "visit_scheduled": "Visit scheduled",
    "verified": "Property verified",
    "declined": "Not proceeding",
}


def _listing_context(record):
    if not record:
        return None
    from types import SimpleNamespace

    values = dict(record)
    photos = values.pop("photos", [])
    values.pop("primary_photo", None)
    values.pop("monthly_rent", None)
    primary_photo = None
    if photos:
        image_url = photos[0].get("image", "")
        primary_photo = SimpleNamespace(
            image=SimpleNamespace(url=image_url),
            caption=photos[0].get("caption", ""),
        )
    annual_rent = record.get("annual_rent") or 0
    return SimpleNamespace(
        **values,
        primary_photo=primary_photo,
        monthly_rent=(annual_rent + 11) // 12,
    )


def _owner_session_id(request):
    return request.session.get("rental_owner_id")


def _staff_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.session.get("rental_staff_authenticated"):
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        return view(request, *args, **kwargs)

    return wrapped


def _approved_owner(request):
    owner_id = _owner_session_id(request)
    if not owner_id:
        return None
    profile = owner_profile(owner_id)
    if not profile or profile.get("status") != OwnerProfile.AccountStatus.APPROVED:
        request.session.pop("rental_owner_id", None)
        request.session.pop("rental_owner_email", None)
        return None
    return profile


def _owner_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        profile = _approved_owner(request)
        if not profile:
            return redirect(f"{reverse('accounts:login')}?next={request.path}")
        request.rental_owner_profile = profile
        return view(request, *args, **kwargs)

    return wrapped


def home(request):
    flutter_index = settings.FLUTTER_WEB_BUILD_DIRECTORY / "index.html"
    if flutter_index.is_file():
        response = FileResponse(flutter_index.open("rb"), content_type="text/html")
        response["Cache-Control"] = "no-cache"
        return response
    if settings.IS_PRODUCTION:
        logger.error("Flutter web build is missing: %s", flutter_index)
        return JsonResponse(
            {"error": "The rental website is temporarily unavailable."},
            status=503,
        )
    return _render_public_home(request)


def flutter_asset(request, asset):
    build_directory = settings.FLUTTER_WEB_BUILD_DIRECTORY.resolve()
    asset_path = (build_directory / asset).resolve()
    try:
        if os.path.commonpath(
            (str(build_directory), str(asset_path))
        ) != str(build_directory):
            raise Http404
    except ValueError as error:
        raise Http404 from error
    if not asset_path.is_file():
        raise Http404
    content_type = (
        "application/wasm"
        if asset_path.suffix == ".wasm"
        else mimetypes.guess_type(asset_path.name)[0]
    )
    response = FileResponse(
        asset_path.open("rb"),
        content_type=content_type or "application/octet-stream",
    )
    response["Cache-Control"] = (
        "no-cache" if asset_path.suffix == ".js" else "public, max-age=3600"
    )
    return response


@require_GET
@ensure_csrf_cookie
def public_api_csrf_token(request):
    return JsonResponse({"csrf_token": get_token(request)})


@require_GET
@ensure_csrf_cookie
def public_api_listings(request):
    category = request.GET.get("category", RentalListing.Category.HOME)
    transaction_type = request.GET.get("transaction_type", "")
    allowed_categories = {choice for choice, _ in RentalListing.Category.choices}
    allowed_transactions = {
        choice for choice, _ in RentalListing.TransactionType.choices
    }
    if category not in allowed_categories:
        return JsonResponse({"error": "Choose a valid property category."}, status=400)
    if category == RentalListing.Category.HOME:
        transaction_type = RentalListing.TransactionType.RENT
    elif transaction_type not in {"", "all", *allowed_transactions}:
        return JsonResponse({"error": "Choose a valid listing type."}, status=400)

    try:
        listings = public_listings(
            category=category,
            transaction_type=(
                transaction_type
                if transaction_type in allowed_transactions
                else None
            ),
        )
    except APIError:
        logger.exception("Could not load public rental listings.")
        return JsonResponse(
            {"error": "Listings are temporarily unavailable. Please try again."},
            status=503,
        )

    cities = sorted({
        listing.get("city", "")
        for listing in listings
        if listing.get("city")
    })
    location = request.GET.get("location", "").strip().casefold()
    city = request.GET.get("city", "").strip().casefold()
    budget = request.GET.get("budget", "").strip()
    if category == RentalListing.Category.LAND:
        budget_options = {
            "30000",
            "50000",
            "100000",
            "250000",
            "500000",
            "1000000",
            "5000000",
            "10000000",
            "25000000",
            "50000000",
            "100000000",
            "250000000",
            "500000000",
        }
    else:
        budget_options = {"30000", "50000", "100000", "250000", "500000"}
    max_price = int(budget) if budget in budget_options else None
    if location:
        listings = [
            listing for listing in listings
            if location in " ".join(
                str(listing.get(field) or "")
                for field in ("address", "city", "state")
            ).casefold()
        ]
    if city:
        listings = [
            listing for listing in listings
            if str(listing.get("city") or "").casefold() == city
        ]
    if max_price is not None:
        listings = [
            listing for listing in listings
            if (
                (
                    ((listing.get("annual_rent") or 0) + 11) // 12
                    if listing.get("transaction_type")
                    == RentalListing.TransactionType.RENT
                    else listing.get("sale_price") or 0
                )
                <= max_price
            )
        ]

    return JsonResponse({
        "csrf_token": get_token(request),
        "inspection_whatsapp": settings.RENTAL_INSPECTION_WHATSAPP_NUMBER,
        "listings": [
            {
                "id": listing.get("id"),
                "slug": listing.get("slug", ""),
                "title": listing.get("title", ""),
                "description": listing.get("description", ""),
                "address": listing.get("address", ""),
                "city": listing.get("city", ""),
                "state": listing.get("state", ""),
                "property_type": listing.get("property_type", ""),
                "category": listing.get("category", category),
                "transaction_type": listing.get("transaction_type", "rent"),
                "bedrooms": listing.get("bedrooms", 0),
                "bathrooms": listing.get("bathrooms", 0),
                "annual_rent": listing.get("annual_rent") or 0,
                "sale_price": listing.get("sale_price") or 0,
                "monthly_rent": (
                    (listing.get("annual_rent") or 0) + 11
                ) // 12,
                "photos": [
                    {
                        "image": photo.get("image", ""),
                        "caption": photo.get("caption", ""),
                    }
                    for photo in listing.get("photos", [])
                    if photo.get("image")
                ],
            }
            for listing in listings
        ],
        "cities": cities,
        "listing_count": len(listings),
    })


def _json_payload(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _form_errors(form):
    return {
        field: [str(error) for error in errors]
        for field, errors in form.errors.items()
    }


@require_POST
def public_api_property_request(request):
    payload = _json_payload(request)
    if payload is None:
        return JsonResponse({"error": "Send the request as a JSON object."}, status=400)
    form = PropertyListingRequestForm(data=payload)
    if not form.is_valid():
        return JsonResponse(
            {"error": "Check the property details and try again.", "errors": _form_errors(form)},
            status=400,
        )

    values = {
        key: form.cleaned_data[key]
        for key in ("owner_name", "phone", "property_type", "address")
    }
    values.update({
        "terms_accepted": True,
        "terms_accepted_at": timezone.now().isoformat(),
        "status": "new",
        "staff_notes": "",
    })
    try:
        insert("rental_property_listing_requests", values)
    except APIError:
        logger.exception("Could not save home rental request.")
        return JsonResponse(
            {"error": "Your request could not be sent right now. Please try again."},
            status=503,
        )
    return JsonResponse(
        {"message": "Your request was received. Rooms will contact you to arrange verification."},
        status=201,
    )


@require_POST
def public_api_inspection_request(request, slug):
    payload = _json_payload(request)
    if payload is None:
        return JsonResponse({"error": "Send the request as a JSON object."}, status=400)
    listing = listing_by_slug(slug, published_only=True)
    if (
        not listing
        or listing.get("category")
        not in (RentalListing.Category.HOME, RentalListing.Category.LAND)
        or listing.get("transaction_type")
        not in (
            RentalListing.TransactionType.RENT,
            RentalListing.TransactionType.SALE,
        )
    ):
        raise Http404

    form = PublicInspectionRequestForm(data=payload)
    if not form.is_valid():
        return JsonResponse(
            {
                "error": "Check your contact details and inspection date, then try again.",
                "errors": _form_errors(form),
            },
            status=400,
        )
    values = {
        key: form.cleaned_data[key]
        for key in ("guest_name", "email", "phone", "preferred_date", "message")
    }
    if values["preferred_date"]:
        values["preferred_date"] = values["preferred_date"].isoformat()
    values.update({"listing_id": listing["id"], "status": "new", "staff_notes": ""})
    try:
        insert("rental_inspection_requests", values)
    except APIError:
        logger.exception("Could not save public rental inspection request.")
        return JsonResponse(
            {"error": "Your viewing request could not be sent right now. Please try again."},
            status=503,
        )
    return JsonResponse(
        {
            "message": (
                "Your inspection request was saved. Continue in WhatsApp "
                "to send it to Rooms."
            )
        },
        status=201,
    )


def _render_public_home(request, *, inspection_form=None, inspection_listing=None):
    listings = public_listings()
    cities = sorted({listing.get("city", "") for listing in listings if listing.get("city")})
    location = request.GET.get("location", "").strip()
    city = request.GET.get("city", "").strip()
    budget = request.GET.get("budget", "").strip()
    budget_options = {"30000", "50000", "100000", "250000", "500000"}
    if location:
        needle = location.casefold()
        listings = [
            listing for listing in listings
            if needle in " ".join(
                (listing.get("address", ""), listing.get("city", ""), listing.get("state", ""))
            ).casefold()
        ]
    if city:
        listings = [
            listing for listing in listings
            if listing.get("city", "").casefold() == city.casefold()
        ]
    if budget in budget_options:
        max_annual_rent = int(budget) * 12
        listings = [
            listing for listing in listings
            if (listing.get("annual_rent") or 0) <= max_annual_rent
        ]
    else:
        budget = ""

    return render(
        request,
        "rentals/home.html",
        {
            "listings": [_listing_context(item) for item in listings],
            "listing_count": len(listings),
            "cities": cities,
            "location_filter": location,
            "city_filter": city,
            "budget_filter": budget,
            "inspection_form": inspection_form or PublicInspectionRequestForm(),
            "inspection_listing": _listing_context(inspection_listing),
        },
    )


@require_POST
def public_inspection_request(request, slug):
    listing = listing_by_slug(slug, published_only=True)
    if (
        not listing
        or listing.get("category") != RentalListing.Category.HOME
        or listing.get("transaction_type") != RentalListing.TransactionType.RENT
    ):
        raise Http404
    form = PublicInspectionRequestForm(request.POST)
    if form.is_valid():
        values = {
            key: form.cleaned_data[key]
            for key in ("guest_name", "email", "phone", "preferred_date", "message")
        }
        if values["preferred_date"]:
            values["preferred_date"] = values["preferred_date"].isoformat()
        values["listing_id"] = listing["id"]
        values["status"] = "new"
        values["staff_notes"] = ""
        try:
            insert("rental_inspection_requests", values)
        except APIError:
            logger.exception("Could not save public rental inspection request.")
            form.add_error(
                None,
                "Your viewing request could not be sent right now. Please try again.",
            )
            return _render_public_home(
                request,
                inspection_form=form,
                inspection_listing=listing,
            )
        messages.success(
            request,
            "Your viewing request has been sent to Rooms. Our team will contact you.",
        )
        return redirect(f"{reverse('home')}#listings")

    return _render_public_home(
        request,
        inspection_form=form,
        inspection_listing=listing,
    )


def property_listing_request(request):
    form = PropertyListingRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        values = {
            key: form.cleaned_data[key]
            for key in ("owner_name", "phone", "property_type", "address")
        }
        values.update(
            {
                "terms_accepted": True,
                "terms_accepted_at": timezone.now().isoformat(),
                "status": "new",
                "staff_notes": "",
            }
        )
        try:
            insert("rental_property_listing_requests", values)
        except APIError:
            logger.exception("Could not save home rental request.")
            form.add_error(
                None,
                "Your request could not be sent right now. Please try again.",
            )
        else:
            return redirect("property_listing_request_submitted")
    return render(request, "rentals/property_request.html", {"form": form})


def property_listing_request_submitted(request):
    return render(request, "rentals/property_request_submitted.html")


def owner_account_request(request):
    if request.session.get("rental_staff_authenticated") or _owner_session_id(request):
        return redirect("dashboard")
    if request.GET.get("owner_type") == OwnerProfile.OwnerType.HOME:
        return redirect("property_listing_request")
    form = OwnerAccountRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            response = auth_client().auth.sign_up(
                {
                    "email": data["email"],
                    "password": data["password1"],
                    "options": {
                        "data": {
                            "app_role": "rental_owner",
                            "username": data["username"],
                            "first_name": data["first_name"],
                            "last_name": data["last_name"],
                            "owner_type": data["owner_type"],
                            "phone": data["phone"],
                        }
                    },
                }
            )
            if not response.user:
                form.add_error(
                    None,
                    "We could not submit your account request right now. Please try again later.",
                )
                return render(request, "rentals/owner_request.html", {"form": form})
        except (AuthApiError, APIError):
            logger.exception("Could not create rental owner account request.")
            form.add_error(
                None,
                "We could not submit your account request right now. Please try again later.",
            )
        else:
            return render(request, "rentals/owner_request_submitted.html")
    return render(request, "rentals/owner_request.html", {"form": form})


def login(request):
    form = StaffLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password"]
        if (
            secrets.compare_digest(username, settings.RENTAL_STAFF_USERNAME)
            and secrets.compare_digest(password, settings.RENTAL_STAFF_PASSWORD)
        ):
            request.session.flush()
            request.session["rental_staff_authenticated"] = True
            next_url = request.POST.get("next", "")
            if url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect("dashboard")

        try:
            response = auth_client().auth.sign_in_with_password(
                {"email": username, "password": password}
            )
            profile = owner_profile(response.user.id)
        except AuthApiError:
            profile = None
        except APIError:
            logger.exception("Supabase owner sign-in lookup failed.")
            form.add_error(None, "Sign-in is temporarily unavailable. Please try again.")
            return render(
                request,
                "rentals/login.html",
                {"form": form, "next": request.POST.get("next", "")},
            )
        if profile and profile.get("status") == OwnerProfile.AccountStatus.APPROVED:
            request.session.flush()
            request.session["rental_owner_id"] = str(response.user.id)
            request.session["rental_owner_email"] = response.user.email
            return redirect("dashboard")
        form.add_error(
            None,
            "Sign-in failed. Check your details or contact Rooms if your owner account is awaiting approval.",
        )
    return render(
        request,
        "rentals/login.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


@require_POST
def logout(request):
    request.session.flush()
    return redirect("home")


def dashboard(request):
    if request.session.get("rental_staff_authenticated"):
        return staff_dashboard(request)
    profile = _approved_owner(request)
    if profile:
        return owner_dashboard(request, profile)
    return redirect("accounts:login")


@never_cache
@_staff_required
def staff_dashboard(request):
    listings = rows("rental_listings")
    property_requests = rows("rental_property_listing_requests")
    inspections = rows("rental_inspection_requests")
    owners = rows("rental_api_owner_profiles")
    listing_by_id = {item["id"]: item for item in listings}
    for inspection in inspections:
        inspection["listing"] = listing_by_id.get(inspection.get("listing_id"), {})
        inspection["status_display"] = INSPECTION_STATUS_LABELS.get(
            inspection.get("status"), inspection.get("status", "")
        )
    context = {
        "api_backend": True,
        "listing_count": len(listings),
        "published_count": sum(item.get("status") == "published" for item in listings),
        "pending_listing_count": sum(
            item.get("status") == "pending_review" for item in listings
        ),
        "pending_owner_count": sum(
            item.get("status") == "pending" for item in owners
        ),
        "new_property_request_count": sum(
            item.get("status") == "new" for item in property_requests
        ),
        "new_inspection_count": sum(
            item.get("status") == "new" for item in inspections
        ),
        "recent_inspections": sorted(
            inspections,
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )[:8],
    }
    return render(request, "rentals/dashboard.html", context)


@never_cache
@_staff_required
def staff_records(request):
    listings = rows("rental_listings")
    property_requests = rows("rental_property_listing_requests")
    inspections = rows("rental_inspection_requests")
    owners = rows("rental_api_owner_profiles")
    listings_by_id = {item["id"]: item for item in listings}
    for listing in listings:
        listing["pk"] = listing["id"]
        listing["status_display"] = LISTING_STATUS_LABELS.get(
            listing.get("status"), listing.get("status", "")
        )
    for profile in owners:
        profile["status_display"] = OWNER_STATUS_LABELS.get(
            profile.get("status"), profile.get("status", "")
        )
    for inspection in inspections:
        inspection["listing"] = listings_by_id.get(inspection.get("listing_id"), {})
        inspection["status_display"] = INSPECTION_STATUS_LABELS.get(
            inspection.get("status"), inspection.get("status", "")
        )
    for item in property_requests:
        item["status_display"] = PROPERTY_REQUEST_STATUS_LABELS.get(
            item.get("status"), item.get("status", "")
        )
    return render(
        request,
        "rentals/staff_records.html",
        {
            "listings": listings,
            "property_requests": property_requests,
            "inspections": inspections,
            "owners": owners,
            "listing_statuses": RentalListing.PublicationStatus.choices,
            "inspection_statuses": tuple(INSPECTION_STATUS_LABELS.items()),
            "owner_statuses": OwnerProfile.AccountStatus.choices,
            "property_request_statuses": tuple(
                PROPERTY_REQUEST_STATUS_LABELS.items()
            ),
        },
    )


@never_cache
@_staff_required
def staff_listing_create(request):
    return _staff_listing_form(request)


@never_cache
@_staff_required
def staff_listing_edit(request, pk):
    listing = row_by_id("rental_listings", pk)
    if not listing:
        raise Http404
    return _staff_listing_form(request, listing)


def _staff_listing_form(request, listing=None):
    initial = {
        key: listing.get(key)
        for key in (
            "title",
            "description",
            "address",
            "city",
            "state",
            "property_type",
            "transaction_type",
            "annual_rent",
            "sale_price",
            "bedrooms",
            "bathrooms",
            "category",
            "status",
        )
    } if listing else {
        "category": RentalListing.Category.HOME,
        "transaction_type": RentalListing.TransactionType.RENT,
        "status": RentalListing.PublicationStatus.DRAFT,
    }
    form = StaffRentalListingForm(
        request.POST or None,
        request.FILES or None,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        action = request.POST.get("action")
        if action != "save":
            form.add_error(None, "Choose save to update the listing.")
        else:
            values = {
                key: data[key]
                for key in (
                    "title",
                    "description",
                    "address",
                    "city",
                    "state",
                    "property_type",
                    "transaction_type",
                    "annual_rent",
                    "sale_price",
                    "bedrooms",
                    "bathrooms",
                    "category",
                    "status",
                )
            }
            values.update(
                {
                    "owner_auth_id": listing.get("owner_auth_id") if listing else None,
                    "updated_at": timezone.now().isoformat(),
                }
            )
            try:
                if listing:
                    saved_listing = update(
                        "rental_listings",
                        listing["id"],
                        values,
                    )
                else:
                    slug_base = slugify(data["title"]) or "rental"
                    values["slug"] = f"{slug_base}-{uuid4().hex[:8]}"
                    saved_listing = insert("rental_listings", values)
                if not saved_listing:
                    form.add_error(
                        None,
                        "The listing could not be saved. Please try again.",
                    )
                    return render(
                        request,
                        "rentals/staff_listing_form.html",
                        {"form": form, "listing": listing},
                    )
                photos = data.get("photos") or []
                if photos:
                    existing_photos = rows(
                        "rental_listing_photos",
                        listing_id=saved_listing["id"],
                    )
                    next_position = len(existing_photos)
                    for offset, photo in enumerate(photos):
                        photo_data = upload_listing_photo(
                            photo,
                            saved_listing["id"],
                            next_position + offset,
                        )
                        insert("rental_listing_photos", photo_data)
            except APIError:
                logger.exception("Could not save staff rental listing.")
                form.add_error(
                    None,
                    "The listing or its photos could not be saved completely. Review the listing before retrying.",
                )
            else:
                messages.success(request, "The listing was saved.")
                return redirect("staff_records")
    return render(
        request,
        "rentals/staff_listing_form.html",
        {"form": form, "listing": listing},
    )


@require_POST
@_staff_required
def staff_update_record(request, record_type, record_id):
    status = request.POST.get("status", "")
    notes = request.POST.get("staff_notes", "").strip()
    tables = {
        "listing": ("rental_listings", dict(RentalListing.PublicationStatus.choices)),
        "inspection": ("rental_inspection_requests", INSPECTION_STATUS_LABELS),
        "property-request": (
            "rental_property_listing_requests",
            PROPERTY_REQUEST_STATUS_LABELS,
        ),
        "owner": ("rental_api_owner_profiles", OWNER_STATUS_LABELS),
    }
    if record_type not in tables:
        raise Http404
    table, allowed_statuses = tables[record_type]
    if status not in allowed_statuses:
        raise Http404
    values = {"status": status}
    if record_type in {"inspection", "property-request"}:
        values["staff_notes"] = notes
    try:
        if record_type == "owner":
            result = (
                admin_client()
                .table(table)
                .update(values)
                .eq("user_id", record_id)
                .select("user_id")
                .execute()
                .data
            )
        else:
            result = update(table, record_id, values)
    except APIError:
        logger.exception("Could not update rental %s record %s.", record_type, record_id)
        messages.error(request, "The record could not be updated. Please try again.")
    else:
        if not result:
            raise Http404
        messages.success(request, "The record was updated.")
    return redirect("staff_records")


def owner_dashboard(request, profile):
    listings = owner_listings(profile["user_id"])
    for listing in listings:
        listing["pk"] = listing["id"]
        listing["status_display"] = LISTING_STATUS_LABELS.get(
            listing.get("status"), listing.get("status", "")
        )
        listing["transaction_type_display"] = dict(
            RentalListing.TransactionType.choices
        ).get(listing.get("transaction_type"), listing.get("transaction_type", ""))
    template = (
        "rentals/home_owner_dashboard.html"
        if profile["owner_type"] == OwnerProfile.OwnerType.HOME
        else "rentals/land_owner_dashboard.html"
    )
    return render(
        request,
        template,
        {
            "profile": profile,
            "owner_name": " ".join(
                filter(None, (profile.get("first_name"), profile.get("last_name")))
            ) or profile.get("username", profile.get("email", "")),
            "listings": listings,
            "listing_count": len(listings),
            "published_count": sum(
                item.get("status") == "published" for item in listings
            ),
            "pending_count": sum(
                item.get("status") == "pending_review" for item in listings
            ),
        },
    )


@never_cache
@_owner_required
def home_owner_dashboard(request):
    if request.rental_owner_profile["owner_type"] != OwnerProfile.OwnerType.HOME:
        raise Http404
    return owner_dashboard(request, request.rental_owner_profile)


@never_cache
@_owner_required
def land_owner_dashboard(request):
    if request.rental_owner_profile["owner_type"] != OwnerProfile.OwnerType.LAND:
        raise Http404
    return owner_dashboard(request, request.rental_owner_profile)


@never_cache
@_owner_required
def owner_listing_create(request):
    return _owner_listing_form(request)


@never_cache
@_owner_required
def owner_listing_edit(request, pk):
    listing = row_by_id("rental_listings", pk)
    profile = request.rental_owner_profile
    if (
        not listing
        or listing.get("owner_auth_id") != profile["user_id"]
        or listing.get("status")
        in {
            RentalListing.PublicationStatus.PUBLISHED,
            RentalListing.PublicationStatus.RENTED,
            RentalListing.PublicationStatus.ARCHIVED,
        }
    ):
        raise Http404
    return _owner_listing_form(request, listing)


def _owner_listing_form(request, listing=None):
    profile = request.rental_owner_profile
    initial = {
        key: listing.get(key)
        for key in (
            "title",
            "description",
            "address",
            "city",
            "state",
            "property_type",
            "transaction_type",
            "annual_rent",
            "sale_price",
            "bedrooms",
            "bathrooms",
        )
    } if listing else None
    form = OwnerListingForm(request.POST or None, request.FILES or None, initial=initial)
    if profile["owner_type"] == OwnerProfile.OwnerType.HOME:
        form.fields["transaction_type"].choices = (
            (RentalListing.TransactionType.RENT, "For rent"),
        )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        action = request.POST.get("action")
        if action not in {"draft", "submit"}:
            form.add_error(None, "Choose whether to save a draft or submit for review.")
        else:
            values = {
                key: data[key]
                for key in (
                    "title",
                    "description",
                    "address",
                    "city",
                    "state",
                    "property_type",
                    "transaction_type",
                    "annual_rent",
                    "sale_price",
                    "bedrooms",
                    "bathrooms",
                )
            }
            values.update(
                {
                    "owner_auth_id": profile["user_id"],
                    "category": (
                        RentalListing.Category.HOME
                        if profile["owner_type"] == OwnerProfile.OwnerType.HOME
                        else RentalListing.Category.LAND
                    ),
                    "status": (
                        RentalListing.PublicationStatus.PENDING_REVIEW
                        if action == "submit"
                        else RentalListing.PublicationStatus.DRAFT
                    ),
                    "updated_at": timezone.now().isoformat(),
                }
            )
            try:
                if listing:
                    saved_listing = update("rental_listings", listing["id"], values)
                else:
                    slug_base = slugify(data["title"]) or "rental"
                    values["slug"] = f"{slug_base}-{uuid4().hex[:8]}"
                    saved_listing = insert("rental_listings", values)
                if not saved_listing:
                    form.add_error(
                        None,
                        "Your listing could not be saved. Please try again.",
                    )
                    return render(
                        request,
                        "rentals/owner_listing_form.html",
                        {"form": form, "listing": listing, "profile": profile},
                    )
                photos = form.cleaned_data.get("photos") or []
                if photos:
                    existing_photos = rows(
                        "rental_listing_photos",
                        listing_id=saved_listing["id"],
                    )
                    next_position = len(existing_photos)
                    for offset, photo in enumerate(photos):
                        photo_data = upload_listing_photo(
                            photo,
                            saved_listing["id"],
                            next_position + offset,
                        )
                        insert("rental_listing_photos", photo_data)
            except APIError:
                logger.exception("Could not save owner rental listing.")
                form.add_error(
                    None,
                    "Your listing could not be saved completely. Please contact Rooms before retrying.",
                )
                return render(
                    request,
                    "rentals/owner_listing_form.html",
                    {"form": form, "listing": listing, "profile": profile},
                )
            messages.success(
                request,
                "Your listing was submitted for review."
                if action == "submit"
                else "Your listing draft was saved.",
            )
            return redirect(
                "home_owner_dashboard"
                if profile["owner_type"] == OwnerProfile.OwnerType.HOME
                else "land_owner_dashboard"
            )
    return render(
        request,
        "rentals/owner_listing_form.html",
        {"form": form, "listing": listing, "profile": profile},
    )
