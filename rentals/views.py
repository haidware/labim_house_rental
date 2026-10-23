from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .models import InspectionRequest, RentalListing


@staff_member_required
def dashboard(request):
    context = {
        "listing_count": RentalListing.objects.count(),
        "published_count": RentalListing.objects.filter(
            status=RentalListing.PublicationStatus.PUBLISHED
        ).count(),
        "new_inspection_count": InspectionRequest.objects.filter(
            status=InspectionRequest.Status.NEW
        ).count(),
        "recent_inspections": InspectionRequest.objects.select_related(
            "listing"
        )[:8],
    }
    return render(request, "rentals/dashboard.html", context)
