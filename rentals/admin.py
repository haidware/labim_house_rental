from django.contrib import admin

from .models import (
    InspectionRequest,
    ListingPhoto,
    RentalAdminProfile,
    RentalListing,
)


class ListingPhotoInline(admin.TabularInline):
    model = ListingPhoto
    extra = 1


@admin.register(RentalListing)
class RentalListingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "city",
        "state",
        "annual_rent",
        "bedrooms",
        "status",
        "updated_at",
    )
    list_filter = ("status", "state", "city", "property_type")
    search_fields = ("title", "description", "address", "city", "state")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = (ListingPhotoInline,)
    list_per_page = 30


@admin.register(InspectionRequest)
class InspectionRequestAdmin(admin.ModelAdmin):
    list_display = (
        "guest_name",
        "listing",
        "phone",
        "preferred_date",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "guest_name",
        "email",
        "phone",
        "listing__title",
        "staff_notes",
    )
    readonly_fields = ("created_at", "updated_at")
    list_editable = ("status",)


@admin.register(RentalAdminProfile)
class RentalAdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "user__email", "phone")
