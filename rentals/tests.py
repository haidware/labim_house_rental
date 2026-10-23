from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import InspectionRequest, RentalListing


class RentalAdminTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="manager",
            password="StrongPassword123!",
            is_staff=True,
        )
        self.listing = RentalListing.objects.create(
            title="Bright family home",
            description="A test property.",
            city="Abuja",
            state="FCT",
            annual_rent=2_400_000,
            status=RentalListing.PublicationStatus.PUBLISHED,
        )

    def test_dashboard_requires_staff_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('admin:login')}?next={reverse('dashboard')}",
        )

    def test_staff_dashboard_shows_listing_and_new_inspection_counts(self):
        InspectionRequest.objects.create(
            listing=self.listing,
            guest_name="Guest Example",
            email="guest@example.com",
            phone="+2348012345678",
        )
        self.client.force_login(self.staff)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["listing_count"], 1)
        self.assertEqual(response.context["published_count"], 1)
        self.assertEqual(response.context["new_inspection_count"], 1)

    def test_listing_slug_is_generated_and_unique(self):
        second = RentalListing.objects.create(
            title=self.listing.title,
            description="Another property.",
            city="Lagos",
            state="Lagos",
            annual_rent=3_000_000,
        )
        self.assertEqual(self.listing.slug, "bright-family-home")
        self.assertEqual(second.slug, "bright-family-home-2")
