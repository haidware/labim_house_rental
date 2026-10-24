from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import OwnerProfile


@override_settings(
    ROOT_URLCONF="rentals.api_urls",
    RENTAL_STAFF_USERNAME="rooms-staff",
    RENTAL_STAFF_PASSWORD="test-only-password-123",
)
class SupabaseApiWorkflowTests(TestCase):
    def test_home_renders_api_listings_and_search_filters(self):
        with patch(
            "rentals.api_views.public_listings",
            return_value=[
                {
                    "id": 1,
                    "slug": "lekki-home",
                    "title": "Lekki family home",
                    "description": "A test listing.",
                    "address": "Lekki Phase 1",
                    "city": "Lagos",
                    "state": "Lagos",
                    "property_type": "House",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "annual_rent": 1_200_000,
                    "photos": [
                        {"image": "https://storage.example/house.jpg", "caption": ""}
                    ],
                },
                {
                    "id": 2,
                    "slug": "abuja-home",
                    "title": "Abuja family home",
                    "description": "Another listing.",
                    "address": "Maitama",
                    "city": "Abuja",
                    "state": "FCT",
                    "property_type": "House",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "annual_rent": 1_200_000,
                    "photos": [],
                },
            ],
        ):
            response = self.client.get(
                reverse("home"),
                {"location": "Lekki", "budget": "100000"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lekki family home")
        self.assertNotContains(response, "Abuja family home")
        self.assertContains(response, "https://storage.example/house.jpg")
        self.assertEqual(response.context["listing_count"], 1)

    @patch("rentals.api_views.public_listings", return_value=[])
    def test_staff_session_keeps_customer_homepage_at_root(self, public_listings):
        session = self.client.session
        session["rental_staff_authenticated"] = True
        session.save()

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "rentals/home.html")
        self.assertContains(response, "Homes available for rent")
        public_listings.assert_called_once_with()

    @patch("rentals.api_views.insert")
    def test_home_request_is_saved_in_supabase(self, insert_record):
        response = self.client.post(
            reverse("property_listing_request"),
            {
                "owner_name": "Owner Example",
                "phone": "+2348012345678",
                "property_type": "house",
                "address": "12 Test Street, Lagos",
                "terms_accepted": "on",
            },
        )

        self.assertRedirects(response, reverse("property_listing_request_submitted"))
        insert_record.assert_called_once()
        table, values = insert_record.call_args.args
        self.assertEqual(table, "rental_property_listing_requests")
        self.assertEqual(values["owner_name"], "Owner Example")
        self.assertTrue(values["terms_accepted"])
        self.assertEqual(values["status"], "new")

    @patch("rentals.api_views.rows", return_value=[])
    def test_environment_staff_login_uses_custom_supabase_dashboard(self, rows):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )

        self.assertRedirects(response, reverse("dashboard"))
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Manage property requests, owners and listings")
        self.assertGreaterEqual(rows.call_count, 4)

    def test_rental_admin_url_requires_staff_login(self):
        response = self.client.get("/rental.admin")

        self.assertRedirects(
            response,
            "/accounts/login/?next=/rental.admin",
        )

    @patch(
        "rentals.api_views.update",
        return_value={"id": 17, "status": "published"},
    )
    @patch("rentals.api_views.rows", return_value=[])
    def test_staff_can_publish_a_listing(self, rows, update_record):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )

        response = self.client.post(
            reverse(
                "staff_update_record",
                args=("listing", "17"),
            ),
            {"status": "published"},
        )

        self.assertRedirects(response, reverse("staff_records"))
        update_record.assert_called_once_with(
            "rental_listings",
            "17",
            {"status": "published"},
        )

    @patch(
        "rentals.api_views.insert",
        return_value={"id": 17, "slug": "new-home"},
    )
    @patch("rentals.api_views.rows", return_value=[])
    def test_staff_can_create_a_verified_listing(self, rows, insert_record):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )

        response = self.client.post(
            reverse("staff_listing_create"),
            {
                "title": "Verified family home",
                "description": "A verified listing.",
                "address": "1 Test Street",
                "city": "Abuja",
                "state": "FCT",
                "property_type": "House",
                "category": "home",
                "transaction_type": "rent",
                "annual_rent": "2400000",
                "bedrooms": "3",
                "bathrooms": "2",
                "status": "draft",
                "action": "save",
            },
        )

        self.assertRedirects(response, reverse("staff_records"))
        table, values = insert_record.call_args.args
        self.assertEqual(table, "rental_listings")
        self.assertEqual(values["category"], "home")
        self.assertEqual(values["annual_rent"], 2_400_000)
        self.assertEqual(values["status"], "draft")

    @patch("rentals.api_views.auth_client")
    def test_owner_account_request_uses_supabase_auth_metadata(self, auth_client):
        auth_client.return_value.auth.sign_up.return_value = SimpleNamespace(
            user=SimpleNamespace(id="f93a57c8-2764-4f38-a912-fc5b5ec6a3a1")
        )

        response = self.client.post(
            reverse("accounts:owner_request"),
            {
                "username": "land-owner",
                "first_name": "Land",
                "last_name": "Owner",
                "email": "owner@example.com",
                "phone": "+2348012345678",
                "owner_type": OwnerProfile.OwnerType.LAND,
                "password1": "Test-password-123!",
                "password2": "Test-password-123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account request received")
        signup = auth_client.return_value.auth.sign_up.call_args.args[0]
        self.assertEqual(signup["email"], "owner@example.com")
        self.assertEqual(signup["options"]["data"]["app_role"], "rental_owner")
        self.assertEqual(signup["options"]["data"]["phone"], "+2348012345678")
