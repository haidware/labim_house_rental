from django.urls import include, path, re_path

from . import api_views


account_patterns = ([
    path("login/", api_views.login, name="login"),
    path("logout/", api_views.logout, name="logout"),
    path(
        "request-owner-account/",
        api_views.owner_account_request,
        name="owner_request",
    ),
], "accounts")

urlpatterns = [
    re_path(
        r"^(?P<asset>(?:[^/]+\.(?:js|json|png|ico|wasm)|(?:assets|canvaskit|icons)/.+))$",
        api_views.flutter_asset,
        name="flutter_asset",
    ),
    path("api/public/csrf/", api_views.public_api_csrf_token, name="public_api_csrf"),
    path("api/public/listings/", api_views.public_api_listings, name="public_api_listings"),
    path(
        "api/public/property-requests/",
        api_views.public_api_property_request,
        name="public_api_property_request",
    ),
    path(
        "api/public/listings/<slug:slug>/inspection-requests/",
        api_views.public_api_inspection_request,
        name="public_api_inspection_request",
    ),
    path("", api_views.home, name="home"),
    re_path(r"^land/?$", api_views.home, name="land_properties"),
    path(
        "homes/<slug:slug>/inspection/",
        api_views.public_inspection_request,
        name="public_inspection_request",
    ),
    path(
        "list-your-property/",
        api_views.property_listing_request,
        name="property_listing_request",
    ),
    path(
        "list-your-property/received/",
        api_views.property_listing_request_submitted,
        name="property_listing_request_submitted",
    ),
    path("accounts/", include(account_patterns, namespace="accounts")),
    path("dashboard/", api_views.dashboard, name="dashboard"),
    path("owner/house/", api_views.home_owner_dashboard, name="home_owner_dashboard"),
    path("owner/land/", api_views.land_owner_dashboard, name="land_owner_dashboard"),
    path("owner/listings/new/", api_views.owner_listing_create, name="owner_listing_create"),
    path(
        "owner/listings/<int:pk>/edit/",
        api_views.owner_listing_edit,
        name="owner_listing_edit",
    ),
    path("staff/records/", api_views.staff_records, name="staff_records"),
    re_path(r"^rental\.admin/?$", api_views.staff_records, name="staff_admin_alias"),
    path(
        "staff/listings/new/",
        api_views.staff_listing_create,
        name="staff_listing_create",
    ),
    path(
        "staff/listings/<int:pk>/edit/",
        api_views.staff_listing_edit,
        name="staff_listing_edit",
    ),
    path(
        "staff/<str:record_type>/<str:record_id>/",
        api_views.staff_update_record,
        name="staff_update_record",
    ),
    path("admin/", api_views.staff_records),
]
