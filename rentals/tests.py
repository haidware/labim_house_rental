from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import InspectionRequest, OwnerProfile, RentalListing


class RentalAdminTests(TestCase):
    password = "Test-password-123!"

    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="manager",
            password=self.password,
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

    def create_owner(self, username="owner", owner_type=OwnerProfile.OwnerType.HOME):
        user = get_user_model().objects.create_user(
            username=username,
            password=self.password,
            is_active=True,
        )
        OwnerProfile.objects.create(
            user=user,
            owner_type=owner_type,
            phone="+2348012345678",
            status=OwnerProfile.AccountStatus.APPROVED,
        )
        return user

    def test_home_page_offers_separate_owner_roles(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "House or home owner")
        self.assertContains(response, "Land or property owner")
        self.assertContains(response, "Haidware team")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('dashboard')}",
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

    def test_owner_account_request_creates_inactive_pending_account(self):
        response = self.client.post(
            reverse("accounts:owner_request"),
            {
                "username": "new-owner",
                "first_name": "New",
                "last_name": "Owner",
                "email": "new-owner@example.com",
                "phone": "+2348012345678",
                "owner_type": OwnerProfile.OwnerType.LAND,
                "password1": self.password,
                "password2": self.password,
            },
        )

        user = get_user_model().objects.get(username="new-owner")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(user.is_active)
        self.assertEqual(user.owner_profile.owner_type, OwnerProfile.OwnerType.LAND)
        self.assertEqual(
            user.owner_profile.status,
            OwnerProfile.AccountStatus.PENDING,
        )

    def test_staff_can_approve_owner_account_request(self):
        user = get_user_model().objects.create_user(
            username="pending-owner",
            password=self.password,
            is_active=False,
        )
        profile = OwnerProfile.objects.create(
            user=user,
            owner_type=OwnerProfile.OwnerType.HOME,
            phone="+2348012345678",
        )
        admin_user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password=self.password,
        )
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("admin:rentals_ownerprofile_changelist"),
            {
                "action": "approve_owner_accounts",
                "_selected_action": [profile.pk],
                "select_across": "0",
            },
        )

        user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(user.is_active)
        self.assertEqual(profile.status, OwnerProfile.AccountStatus.APPROVED)

    def test_owner_listing_is_submitted_for_review_and_scoped_to_owner(self):
        owner = self.create_owner()
        self.client.force_login(owner)

        response = self.client.post(
            reverse("owner_listing_create"),
            {
                "title": "Owner's family home",
                "description": "A home for rent.",
                "city": "Abuja",
                "state": "FCT",
                "property_type": "Detached house",
                "transaction_type": RentalListing.TransactionType.RENT,
                "annual_rent": "2400000",
                "sale_price": "",
                "bedrooms": "3",
                "bathrooms": "2",
                "action": "submit",
                "photos-TOTAL_FORMS": "0",
                "photos-INITIAL_FORMS": "0",
            },
        )

        listing = RentalListing.objects.get(title="Owner's family home")
        self.assertRedirects(response, reverse("home_owner_dashboard"))
        self.assertEqual(listing.owner, owner)
        self.assertEqual(listing.category, RentalListing.Category.HOME)
        self.assertEqual(
            listing.status,
            RentalListing.PublicationStatus.PENDING_REVIEW,
        )
        self.assertNotEqual(listing.status, RentalListing.PublicationStatus.PUBLISHED)

        other_owner = self.create_owner(username="other-owner")
        self.client.force_login(other_owner)
        response = self.client.get(
            reverse("owner_listing_edit", args=(listing.pk,))
        )
        self.assertEqual(response.status_code, 404)

    def test_land_owner_can_submit_sale_price(self):
        owner = self.create_owner(
            owner_type=OwnerProfile.OwnerType.LAND,
        )
        self.client.force_login(owner)

        response = self.client.post(
            reverse("owner_listing_create"),
            {
                "title": "Residential plot",
                "description": "A plot available for sale.",
                "city": "Lagos",
                "state": "Lagos",
                "property_type": "Residential land",
                "transaction_type": RentalListing.TransactionType.SALE,
                "annual_rent": "",
                "sale_price": "15000000",
                "bedrooms": "0",
                "bathrooms": "0",
                "action": "submit",
                "photos-TOTAL_FORMS": "0",
                "photos-INITIAL_FORMS": "0",
            },
        )

        listing = RentalListing.objects.get(title="Residential plot")
        self.assertRedirects(response, reverse("land_owner_dashboard"))
        self.assertEqual(listing.category, RentalListing.Category.LAND)
        self.assertEqual(listing.sale_price, 15_000_000)
        self.assertIsNone(listing.annual_rent)
        self.assertEqual(listing.transaction_type, RentalListing.TransactionType.SALE)
        self.assertEqual(
            listing.status,
            RentalListing.PublicationStatus.PENDING_REVIEW,
        )

    def test_home_owner_cannot_submit_sale_listing(self):
        owner = self.create_owner()
        self.client.force_login(owner)

        response = self.client.post(
            reverse("owner_listing_create"),
            {
                "title": "House for sale",
                "description": "Not accepted for this owner role.",
                "city": "Abuja",
                "state": "FCT",
                "property_type": "House",
                "transaction_type": RentalListing.TransactionType.SALE,
                "annual_rent": "",
                "sale_price": "10000000",
                "bedrooms": "3",
                "bathrooms": "2",
                "action": "submit",
                "photos-TOTAL_FORMS": "0",
                "photos-INITIAL_FORMS": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            RentalListing.objects.filter(title="House for sale").exists()
        )

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
