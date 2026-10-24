from django.contrib import admin
from django.contrib import messages
from django.db import transaction

from .models import (
    InspectionRequest,
    ListingPhoto,
    PropertyListingRequest,
    RentalAdminProfile,
    RentalListing,
    OwnerProfile,
)


class ListingPhotoInline(admin.TabularInline):
    model = ListingPhoto
    extra = 1


@admin.register(RentalListing)
class RentalListingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "transaction_type",
        "owner",
        "city",
        "state",
        "annual_rent",
        "sale_price",
        "bedrooms",
        "status",
        "updated_at",
    )
    list_filter = ("status", "category", "transaction_type", "state", "city")
    search_fields = (
        "title",
        "description",
        "address",
        "city",
        "state",
        "owner__username",
        "owner__email",
    )
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


@admin.register(PropertyListingRequest)
class PropertyListingRequestAdmin(admin.ModelAdmin):
    list_display = (
        "owner_name",
        "property_type",
        "phone",
        "address",
        "status",
        "terms_accepted",
        "created_at",
    )
    list_filter = ("status", "property_type", "terms_accepted", "created_at")
    search_fields = ("owner_name", "phone", "address", "staff_notes")
    readonly_fields = ("terms_accepted_at", "created_at", "updated_at")
    list_editable = ("status",)
    empty_value_display = "—"

    def has_add_permission(self, request):
        return False

    fieldsets = (
        (
            "Owner and property",
            {"fields": ("owner_name", "phone", "property_type", "address")},
        ),
        (
            "Agreement and follow-up",
            {
                "fields": (
                    "terms_accepted",
                    "terms_accepted_at",
                    "status",
                    "staff_notes",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(RentalAdminProfile)
class RentalAdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "user__email", "phone")


@admin.register(OwnerProfile)
class OwnerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "owner_type", "phone", "status", "created_at")
    list_filter = ("owner_type", "status", "created_at")
    search_fields = ("user__username", "user__email", "phone")
    readonly_fields = ("user", "owner_type", "phone", "status", "created_at")
    actions = ("approve_owner_accounts", "reject_owner_accounts")

    @admin.action(description="Approve selected owner account requests")
    def approve_owner_accounts(self, request, queryset):
        approved = 0
        with transaction.atomic():
            for profile in queryset.select_related("user"):
                profile.status = OwnerProfile.AccountStatus.APPROVED
                profile.save(update_fields=("status",))
                if not profile.user.is_active:
                    profile.user.is_active = True
                    profile.user.save(update_fields=("is_active",))
                approved += 1
        self.message_user(
            request,
            f"Approved {approved} owner account(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Reject selected owner account requests")
    def reject_owner_accounts(self, request, queryset):
        rejected = 0
        with transaction.atomic():
            for profile in queryset.select_related("user"):
                profile.status = OwnerProfile.AccountStatus.REJECTED
                profile.save(update_fields=("status",))
                if profile.user.is_active:
                    profile.user.is_active = False
                    profile.user.save(update_fields=("is_active",))
                rejected += 1
        self.message_user(
            request,
            f"Rejected {rejected} owner account(s).",
            messages.SUCCESS,
        )
