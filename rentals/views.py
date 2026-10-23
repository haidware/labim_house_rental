from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ListingPhotoFormSet, OwnerAccountRequestForm, OwnerListingForm
from .models import InspectionRequest, OwnerProfile, RentalListing


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "rentals/home.html")


@login_required
def dashboard(request):
    if request.user.is_staff:
        context = {
            "listing_count": RentalListing.objects.count(),
            "published_count": RentalListing.objects.filter(
                status=RentalListing.PublicationStatus.PUBLISHED
            ).count(),
            "pending_listing_count": RentalListing.objects.filter(
                status=RentalListing.PublicationStatus.PENDING_REVIEW
            ).count(),
            "pending_owner_count": OwnerProfile.objects.filter(
                status=OwnerProfile.AccountStatus.PENDING
            ).count(),
            "new_inspection_count": InspectionRequest.objects.filter(
                status=InspectionRequest.Status.NEW
            ).count(),
            "recent_inspections": InspectionRequest.objects.select_related(
                "listing"
            )[:8],
        }
        return render(request, "rentals/dashboard.html", context)

    profile = get_object_or_404(
        OwnerProfile,
        user=request.user,
        status=OwnerProfile.AccountStatus.APPROVED,
    )
    if profile.owner_type == OwnerProfile.OwnerType.HOME:
        return redirect("home_owner_dashboard")
    return redirect("land_owner_dashboard")


@login_required
def home_owner_dashboard(request):
    return _owner_dashboard(request, OwnerProfile.OwnerType.HOME)


@login_required
def land_owner_dashboard(request):
    return _owner_dashboard(request, OwnerProfile.OwnerType.LAND)


def _owner_dashboard(request, owner_type):
    profile = get_object_or_404(
        OwnerProfile,
        user=request.user,
        owner_type=owner_type,
        status=OwnerProfile.AccountStatus.APPROVED,
    )
    listings = RentalListing.objects.filter(owner=request.user)
    template = (
        "rentals/home_owner_dashboard.html"
        if owner_type == OwnerProfile.OwnerType.HOME
        else "rentals/land_owner_dashboard.html"
    )
    return render(
        request,
        template,
        {
            "profile": profile,
            "listings": listings,
            "listing_count": listings.count(),
            "published_count": listings.filter(
                status=RentalListing.PublicationStatus.PUBLISHED
            ).count(),
            "pending_count": listings.filter(
                status=RentalListing.PublicationStatus.PENDING_REVIEW
            ).count(),
        },
    )


def owner_account_request(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = OwnerAccountRequestForm(
        request.POST or None,
        initial={"owner_type": request.GET.get("owner_type", "")},
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save(commit=False)
            user.is_active = False
            user.email = form.cleaned_data["email"]
            user.first_name = form.cleaned_data["first_name"]
            user.last_name = form.cleaned_data["last_name"]
            user.save()
            OwnerProfile.objects.create(
                user=user,
                owner_type=form.cleaned_data["owner_type"],
                phone=form.cleaned_data["phone"],
            )
        return render(request, "rentals/owner_request_submitted.html")

    return render(request, "rentals/owner_request.html", {"form": form})


def _owner_profile(request):
    if request.user.is_staff:
        raise PermissionDenied
    return get_object_or_404(
        OwnerProfile,
        user=request.user,
        status=OwnerProfile.AccountStatus.APPROVED,
    )


def _owner_listing_form(request, listing=None):
    profile = _owner_profile(request)
    form = OwnerListingForm(
        request.POST or None,
        instance=listing,
        owner_type=profile.owner_type,
    )
    formset = ListingPhotoFormSet(
        request.POST or None,
        request.FILES or None,
        instance=listing,
    )
    if request.method == "POST":
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            action = request.POST.get("action")
            if action not in ("draft", "submit"):
                form.add_error(None, "Choose whether to save a draft or submit for review.")
            else:
                listing = form.save(commit=False)
                listing.owner = request.user
                listing.category = (
                    RentalListing.Category.HOME
                    if profile.owner_type == OwnerProfile.OwnerType.HOME
                    else RentalListing.Category.LAND
                )
                listing.status = (
                    RentalListing.PublicationStatus.PENDING_REVIEW
                    if action == "submit"
                    else RentalListing.PublicationStatus.DRAFT
                )
                listing.save()
                formset.instance = listing
                formset.save()
                if listing.status == RentalListing.PublicationStatus.PENDING_REVIEW:
                    messages.success(
                        request,
                        "Your listing was submitted for Haidware review.",
                    )
                else:
                    messages.success(request, "Your listing draft was saved.")
                return redirect(
                    "home_owner_dashboard"
                    if profile.owner_type == OwnerProfile.OwnerType.HOME
                    else "land_owner_dashboard"
                )

    return render(
        request,
        "rentals/owner_listing_form.html",
        {
            "form": form,
            "formset": formset,
            "listing": listing,
            "profile": profile,
        },
    )


@login_required
def owner_listing_create(request):
    _owner_profile(request)
    return _owner_listing_form(request)


@login_required
def owner_listing_edit(request, pk):
    _owner_profile(request)
    listing = get_object_or_404(
        RentalListing.objects.exclude(
            status__in=(
                RentalListing.PublicationStatus.PUBLISHED,
                RentalListing.PublicationStatus.RENTED,
                RentalListing.PublicationStatus.ARCHIVED,
            )
        ),
        pk=pk,
        owner=request.user,
    )
    return _owner_listing_form(request, listing)
