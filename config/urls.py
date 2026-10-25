from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.conf import settings

from rentals import views

admin.site.site_header = "Labim House Rentals"
admin.site.site_title = "House Rental Admin"
admin.site.index_title = "Property management"

account_patterns = ([
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="rentals/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("request-owner-account/", views.owner_account_request, name="owner_request"),
], "accounts")

urlpatterns = [
    path("health/", views.health_check, name="health_check"),
]

if settings.SUPABASE_API_ENABLED:
    from rentals.api_urls import urlpatterns as api_urlpatterns

    urlpatterns += api_urlpatterns
else:
    urlpatterns += [
        path("", views.home, name="home"),
        path(
            "homes/<slug:slug>/inspection/",
            views.public_inspection_request,
            name="public_inspection_request",
        ),
        path(
            "list-your-property/",
            views.property_listing_request,
            name="property_listing_request",
        ),
        path(
            "list-your-property/received/",
            views.property_listing_request_submitted,
            name="property_listing_request_submitted",
        ),
        path("accounts/", include(account_patterns, namespace="accounts")),
        path("dashboard/", views.dashboard, name="dashboard"),
        path("owner/house/", views.home_owner_dashboard, name="home_owner_dashboard"),
        path("owner/land/", views.land_owner_dashboard, name="land_owner_dashboard"),
        path("owner/listings/new/", views.owner_listing_create, name="owner_listing_create"),
        path(
            "owner/listings/<int:pk>/edit/",
            views.owner_listing_edit,
            name="owner_listing_edit",
        ),
        path("admin/", admin.site.urls),
    ]
