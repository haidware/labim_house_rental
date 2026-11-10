from io import BytesIO
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
from urllib.parse import parse_qs, urlsplit

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.datastructures import MultiValueDict
from PIL import Image

from .models import OwnerProfile
from .supabase_api import public_listings


@override_settings(
    ROOT_URLCONF="rentals.api_urls",
    RENTAL_STAFF_USERNAME="rooms-staff",
    RENTAL_STAFF_PASSWORD="test-only-password-123",
)
class SupabaseApiWorkflowTests(TestCase):
    @patch("rentals.supabase_api.admin_client")
    def test_land_feed_also_includes_published_home_sales(self, get_admin):
        land_listing = {
            "id": 31,
            "title": "Lekki plot",
            "category": "land",
            "transaction_type": "sale",
            "updated_at": "2026-11-02T00:00:00+00:00",
        }
        home_sale = {
            "id": 32,
            "title": "2 3-bedroom flats for sale",
            "category": "home",
            "transaction_type": "sale",
            "updated_at": "2026-11-03T00:00:00+00:00",
        }
        client = MagicMock()
        get_admin.return_value = client
        query = client.table.return_value.select.return_value
        query.eq.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.in_.return_value = query
        query.execute.side_effect = [
            SimpleNamespace(data=[land_listing]),
            SimpleNamespace(data=[home_sale]),
            SimpleNamespace(data=[]),
        ]

        listings = public_listings(category="land", transaction_type=None)

        self.assertEqual(
            [listing["title"] for listing in listings],
            ["2 3-bedroom flats for sale", "Lekki plot"],
        )
        self.assertEqual(listings[0]["category"], "home")
        self.assertEqual(listings[0]["transaction_type"], "sale")
        self.assertIn(
            call("category", "land"),
            query.eq.call_args_list,
        )
        self.assertIn(
            call("category", "home"),
            query.eq.call_args_list,
        )
        self.assertIn(
            call("transaction_type", "sale"),
            query.eq.call_args_list,
        )

    def test_public_listings_api_filters_and_returns_csrf_token(self):
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
                    "video_url": "https://storage.example/house.mp4",
                    "landlord_whatsapp": "+2348099999999",
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
                reverse("public_api_listings"),
                {"location": "Lekki", "budget": "100000"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["listing_count"], 1)
        self.assertEqual(data["listings"][0]["title"], "Lekki family home")
        self.assertEqual(
            data["listings"][0]["photos"][0]["image"],
            "https://storage.example/house.jpg",
        )
        self.assertEqual(
            data["listings"][0]["video_url"],
            "https://storage.example/house.mp4",
        )
        self.assertEqual(data["listings"][0]["monthly_rent"], 100000)
        self.assertNotIn("landlord_whatsapp", data["listings"][0])
        self.assertTrue(data["csrf_token"])
        self.assertIn("csrftoken", response.cookies)

    @patch(
        "rentals.api_views.public_listings",
        return_value=[
            {
                "id": "land-1",
                "slug": "lekki-land",
                "title": "Lekki plot",
                "description": "Verified plot.",
                "address": "Lekki Phase 1",
                "city": "Lagos",
                "state": "Lagos",
                "category": "land",
                "transaction_type": "sale",
                "property_type": "Residential land",
                "sale_price": 9_000_000,
                "photos": [],
            },
            {
                "id": "land-2",
                "slug": "ikeja-land",
                "title": "Ikeja plot",
                "description": "Another verified plot.",
                "address": "Ikeja",
                "city": "Lagos",
                "state": "Lagos",
                "category": "land",
                "transaction_type": "sale",
                "property_type": "Residential land",
                "sale_price": 15_000_000,
                "photos": [],
            },
        ],
    )
    def test_public_listings_api_returns_admin_published_land(self, public_listings):
        response = self.client.get(
            reverse("public_api_listings"),
            {
                "category": "land",
                "transaction_type": "all",
                "budget": "10000000",
            },
        )

        self.assertEqual(response.status_code, 200)
        listing = response.json()["listings"][0]
        self.assertEqual(listing["category"], "land")
        self.assertEqual(listing["transaction_type"], "sale")
        self.assertEqual(listing["sale_price"], 9_000_000)
        public_listings.assert_called_once_with(category="land", transaction_type=None)

    def test_land_path_serves_flutter_entrypoint(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            build_directory = Path(temp_directory)
            (build_directory / "index.html").write_text(
                "<html>Rooms land properties</html>",
                encoding="utf-8",
            )
            with self.settings(FLUTTER_WEB_BUILD_DIRECTORY=build_directory):
                response = self.client.get("/land")

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Rooms land properties")

    @patch("rentals.api_views.public_listings", return_value=[])
    def test_staff_session_keeps_customer_homepage_at_root(self, public_listings):
        session = self.client.session
        session["rental_staff_authenticated"] = True
        session.save()

        with self.settings(
            FLUTTER_WEB_BUILD_DIRECTORY=(
                Path(__file__).resolve().parent / "missing_flutter_build"
            )
        ):
            response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "rentals/home.html")
        self.assertContains(response, "Homes available for rent")
        public_listings.assert_called_once_with()

    def test_root_serves_flutter_entrypoint_and_assets_when_built(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            build_directory = Path(temp_directory)
            (build_directory / "index.html").write_text(
                "<html>Flutter rental app</html>",
                encoding="utf-8",
            )
            (build_directory / "flutter_bootstrap.js").write_text(
                "Flutter bootstrap",
                encoding="utf-8",
            )
            with self.settings(
                FLUTTER_WEB_BUILD_DIRECTORY=build_directory,
            ):
                response = self.client.get(reverse("home"))
                script = self.client.get("/flutter_bootstrap.js")
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "Flutter rental app")
                    self.assertEqual(response["Cache-Control"], "no-cache")
                    self.assertEqual(script.status_code, 200)
                    self.assertContains(script, "Flutter bootstrap")
                finally:
                    response.close()
                    script.close()

    def test_supabase_urlconf_uses_flutter_home_and_keeps_health_check(self):
        from importlib import reload

        from django.urls import clear_url_caches, resolve

        from config import urls as config_urls
        from rentals import api_views, views

        try:
            with self.settings(
                ROOT_URLCONF="config.urls",
                SUPABASE_API_ENABLED=True,
            ):
                reload(config_urls)
                clear_url_caches()
                self.assertIs(resolve("/").func, api_views.home)
                self.assertIs(resolve("/health/").func, views.health_check)
        finally:
            reload(config_urls)
            clear_url_caches()

    @patch("rentals.api_views.insert")
    @patch("rentals.api_views.public_listings", return_value=[])
    def test_flutter_request_uses_csrf_token_from_listing_api(
        self,
        _public_listings,
        insert_record,
    ):
        client = Client(enforce_csrf_checks=True)
        token_response = client.get(reverse("public_api_listings"))
        token = token_response.json()["csrf_token"]

        response = client.post(
            reverse("public_api_property_request"),
            data={
                "owner_name": "Owner Example",
                "phone": "+2348012345678",
                "property_type": "house",
                "address": "12 Test Street, Lagos",
                "terms_accepted": True,
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 201)
        insert_record.assert_called_once()

    @override_settings(RENTAL_ADMIN_WHATSAPP="+2348127499576")
    @patch("rentals.api_views.insert")
    def test_flutter_property_request_is_validated_and_saved(self, insert_record):
        response = self.client.post(
            reverse("public_api_property_request"),
            data={
                "owner_name": "Owner Example",
                "phone": "+2348012345678",
                "property_type": "house",
                "address": "12 Test Street, Lagos",
                "terms_accepted": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("WhatsApp", response.json()["message"])
        self.assertEqual(
            response.json()["whatsapp_url"].split("?", 1)[0],
            "https://wa.me/2348127499576",
        )
        self.assertEqual(
            parse_qs(urlsplit(response.json()["whatsapp_url"]).query)["text"],
            ["Property listing request\nOwner: Owner Example\nPhone: "
             "+2348012345678\nProperty type: House\nAddress: 12 Test Street, Lagos"],
        )
        table, values = insert_record.call_args.args
        self.assertEqual(table, "rental_property_listing_requests")
        self.assertEqual(values["owner_name"], "Owner Example")
        self.assertTrue(values["terms_accepted"])

    @override_settings(RENTAL_ADMIN_WHATSAPP="+2348127499576")
    @patch("rentals.api_views.insert")
    def test_flutter_land_request_is_saved_and_prepares_admin_whatsapp(
        self,
        insert_record,
    ):
        response = self.client.post(
            reverse("public_api_property_request"),
            data={
                "owner_name": "Land Owner",
                "phone": "+2348012345678",
                "property_type": "residential_land",
                "address": "Plot 12, Lekki, Lagos",
                "terms_accepted": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["whatsapp_url"].split("?", 1)[0],
            "https://wa.me/2348127499576",
        )
        message = parse_qs(
            urlsplit(response.json()["whatsapp_url"]).query
        )["text"][0]
        self.assertIn("Residential land", message)
        self.assertIn("Land Owner", message)
        self.assertIn("Plot 12, Lekki, Lagos", message)
        _, values = insert_record.call_args.args
        self.assertEqual(values["property_type"], "residential_land")
        self.assertTrue(values["terms_accepted"])

    @patch("rentals.api_views.insert")
    def test_flutter_property_request_rejects_missing_verification_consent(
        self,
        insert_record,
    ):
        response = self.client.post(
            reverse("public_api_property_request"),
            data={
                "owner_name": "Owner Example",
                "phone": "+2348012345678",
                "property_type": "house",
                "address": "12 Test Street, Lagos",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("terms_accepted", response.json()["errors"])
        insert_record.assert_not_called()

    @patch("rentals.api_views.insert")
    @patch("rentals.api_views.listing_by_slug")
    def test_flutter_inspection_request_is_saved(
        self,
        listing_by_slug,
        insert_record,
    ):
        listing_by_slug.return_value = {
            "id": "listing-1",
            "category": "home",
            "transaction_type": "rent",
            "landlord_whatsapp": "+2348099999999",
        }
        response = self.client.post(
            reverse("public_api_inspection_request", args=("lagos-home",)),
            data={
                "guest_name": "Guest Example",
                "email": "guest@example.com",
                "phone": "+2348012345678",
                "preferred_date": "2026-11-01",
                "message": "Please call before visiting.",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("inspection request was saved", response.json()["message"])
        self.assertEqual(response.json()["whatsapp_number"], "+2348099999999")
        table, values = insert_record.call_args.args
        self.assertEqual(table, "rental_inspection_requests")
        self.assertEqual(values["listing_id"], "listing-1")
        self.assertEqual(values["preferred_date"], "2026-11-01")

    @patch("rentals.api_views.insert")
    @patch("rentals.api_views.listing_by_slug")
    def test_flutter_inspection_request_accepts_published_land_for_sale(
        self,
        listing_by_slug,
        insert_record,
    ):
        listing_by_slug.return_value = {
            "id": "land-1",
            "category": "land",
            "transaction_type": "sale",
            "landlord_whatsapp": "+2348099999999",
        }
        response = self.client.post(
            reverse("public_api_inspection_request", args=("lekki-land",)),
            data={
                "guest_name": "Guest Example",
                "email": "guest@example.com",
                "phone": "+2348012345678",
                "preferred_date": "2026-11-01",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            insert_record.call_args.args[1]["listing_id"],
            "land-1",
        )

    @patch("rentals.api_views.insert")
    @patch("rentals.api_views.listing_by_slug")
    def test_flutter_inspection_requires_landlord_whatsapp_assignment(
        self,
        listing_by_slug,
        insert_record,
    ):
        listing_by_slug.return_value = {
            "id": "listing-1",
            "category": "home",
            "transaction_type": "rent",
            "landlord_whatsapp": "",
        }
        response = self.client.post(
            reverse("public_api_inspection_request", args=("lagos-home",)),
            data={
                "guest_name": "Guest Example",
                "email": "guest@example.com",
                "phone": "+2348012345678",
                "preferred_date": "2026-11-01",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("landlord WhatsApp number", response.json()["error"])
        insert_record.assert_not_called()

    @patch("rentals.api_views.insert")
    @patch("rentals.api_views.listing_by_slug")
    def test_flutter_inspection_request_requires_a_date(
        self,
        listing_by_slug,
        insert_record,
    ):
        listing_by_slug.return_value = {
            "id": "listing-1",
            "category": "home",
            "transaction_type": "rent",
        }
        response = self.client.post(
            reverse("public_api_inspection_request", args=("lagos-home",)),
            data={
                "guest_name": "Guest Example",
                "email": "guest@example.com",
                "phone": "+2348012345678",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("preferred_date", response.json()["errors"])
        insert_record.assert_not_called()

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
    @patch(
        "rentals.api_views.row_by_id",
        return_value={"id": 17, "landlord_whatsapp": "+2348099999999"},
    )
    def test_staff_can_publish_a_listing(self, row_by_id, update_record):
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

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("staff_records"))
        update_record.assert_called_once_with(
            "rental_listings",
            "17",
            {"status": "published"},
        )

    @patch("rentals.api_views.update")
    @patch(
        "rentals.api_views.row_by_id",
        return_value={"id": 17, "landlord_whatsapp": ""},
    )
    def test_staff_cannot_publish_listing_without_landlord_whatsapp(
        self,
        row_by_id,
        update_record,
    ):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )

        response = self.client.post(
            reverse("staff_update_record", args=("listing", "17")),
            {"status": "published"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("staff_records"))
        update_record.assert_not_called()

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
                "landlord_whatsapp": "+2348099999999",
                "status": "draft",
                "action": "save",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("staff_records"))
        table, values = insert_record.call_args.args
        self.assertEqual(table, "rental_listings")
        self.assertEqual(values["category"], "home")
        self.assertEqual(values["annual_rent"], 2_400_000)
        self.assertEqual(values["landlord_whatsapp"], "+2348099999999")
        self.assertEqual(values["status"], "draft")

    @patch(
        "rentals.api_views.insert",
        return_value={"id": 27, "slug": "lekki-land"},
    )
    @patch("rentals.api_views.rows", return_value=[])
    def test_staff_video_flow_saves_new_listing_as_draft_first(
        self,
        rows,
        insert_record,
    ):
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
                "title": "Lekki land",
                "description": "Verified residential land.",
                "city": "Lagos",
                "state": "Lagos",
                "property_type": "Residential land",
                "category": "land",
                "transaction_type": "sale",
                "sale_price": "9000000",
                "bedrooms": "0",
                "bathrooms": "0",
                "landlord_whatsapp": "+2348099999999",
                "status": "published",
                "action": "save",
            },
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["listing_id"], 27)
        self.assertEqual(
            response.json()["edit_url"],
            reverse("staff_listing_edit", args=(27,)),
        )
        self.assertEqual(
            response.json()["upload_url"],
            reverse("staff_listing_video_upload", args=(27,)),
        )
        self.assertEqual(insert_record.call_args.args[1]["status"], "draft")

    def test_staff_listing_form_displays_video_upload_progress(self):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )

        response = self.client.get(reverse("staff_listing_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-rental-video-upload')
        self.assertContains(response, "<progress", html=False)
        self.assertContains(response, "Uploading video...")
        self.assertContains(response, "Property video")
        self.assertContains(response, 'form.getAttribute("action")')
        self.assertContains(response, 'form.setAttribute("action"')
        self.assertNotContains(response, "form.action")

    @patch(
        "rentals.api_views.row_by_id",
        return_value={"id": 27, "title": "Lekki land"},
    )
    @patch("rentals.api_views.admin_client")
    def test_staff_can_prepare_signed_listing_video_upload(
        self,
        get_admin,
        get_listing,
    ):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )
        storage = MagicMock()
        storage.create_signed_upload_url.return_value = {"token": "short-lived-token"}
        get_admin.return_value.storage.from_.return_value = storage

        with self.settings(SUPABASE_URL="https://rental-project.supabase.co"):
            response = self.client.post(
                reverse("staff_listing_video_upload", args=(27,)),
                data=json.dumps(
                    {
                        "filename": "property-tour.mp4",
                        "content_type": "video/mp4",
                        "size": 1_000_000,
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.json()["path"], r"^27/[a-f0-9]{32}\.mp4$")
        self.assertEqual(
            response.json()["resumable_endpoint"],
            "https://rental-project.storage.supabase.co/storage/v1/upload/resumable/sign",
        )
        self.assertEqual(response.json()["token"], "short-lived-token")
        storage.create_signed_upload_url.assert_called_once_with(
            response.json()["path"]
        )

    @patch(
        "rentals.api_views.row_by_id",
        return_value={
            "id": 27,
            "title": "Lekki land",
            "description": "Verified land.",
            "city": "Lagos",
            "state": "Lagos",
            "property_type": "Residential land",
            "category": "land",
            "transaction_type": "sale",
            "sale_price": 9_000_000,
            "annual_rent": None,
            "bedrooms": 0,
            "bathrooms": 0,
            "landlord_whatsapp": "+2348099999999",
            "status": "draft",
            "owner_auth_id": None,
        },
    )
    @patch("rentals.api_views.admin_client")
    @patch("rentals.api_views.update", return_value={"id": 27})
    def test_staff_saves_sale_listing_video_before_publishing(
        self,
        update_listing,
        get_admin,
        get_listing,
    ):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )
        storage = MagicMock()
        storage.info.return_value = {
            "metadata": {"size": "1000000", "mimetype": "video/mp4"}
        }
        storage.get_public_url.return_value = (
            "https://storage.example/27/property.mp4"
        )
        get_admin.return_value.storage.from_.return_value = storage

        response = self.client.post(
            reverse("staff_listing_edit", args=(27,)),
            {
                "title": "Lekki land",
                "description": "Verified land.",
                "city": "Lagos",
                "state": "Lagos",
                "property_type": "Residential land",
                "category": "land",
                "transaction_type": "sale",
                "sale_price": "9000000",
                "bedrooms": "0",
                "bathrooms": "0",
                "landlord_whatsapp": "+2348099999999",
                "status": "published",
                "action": "save",
                "video_path": f"27/{'a' * 32}.mp4",
                "video_duration": "120",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("staff_records"))
        values = update_listing.call_args.args[2]
        self.assertEqual(values["status"], "published")
        self.assertEqual(
            values["video_url"],
            "https://storage.example/27/property.mp4",
        )
        storage.info.assert_called_once_with(f"27/{'a' * 32}.mp4")

    @patch(
        "rentals.api_views.row_by_id",
        return_value={
            "id": 27,
            "title": "Lekki land",
            "description": "Verified land.",
            "city": "Lagos",
            "state": "Lagos",
            "property_type": "Residential land",
            "category": "land",
            "transaction_type": "sale",
            "sale_price": 9_000_000,
            "annual_rent": None,
            "bedrooms": 0,
            "bathrooms": 0,
            "landlord_whatsapp": "+2348099999999",
            "status": "draft",
            "owner_auth_id": None,
        },
    )
    @patch("rentals.api_views.update")
    def test_invalid_video_path_does_not_publish_sale_listing(
        self,
        update_listing,
        get_listing,
    ):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )

        response = self.client.post(
            reverse("staff_listing_edit", args=(27,)),
            {
                "title": "Lekki land",
                "description": "Verified land.",
                "city": "Lagos",
                "state": "Lagos",
                "property_type": "Residential land",
                "category": "land",
                "transaction_type": "sale",
                "sale_price": "9000000",
                "bedrooms": "0",
                "bathrooms": "0",
                "landlord_whatsapp": "+2348099999999",
                "status": "published",
                "action": "save",
                "video_path": "another-listing/untrusted.mp4",
                "video_duration": "120",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "uploaded video must be no longer than 3 minutes")
        update_listing.assert_not_called()

    def test_staff_can_upload_listing_photos(self):
        self.client.post(
            reverse("accounts:login"),
            {
                "username": "rooms-staff",
                "password": "test-only-password-123",
            },
        )
        photos = []
        for index in range(5):
            image_data = BytesIO()
            Image.new("RGB", (1, 1), color="white").save(image_data, format="PNG")
            photos.append(
                SimpleUploadedFile(
                    f"house-{index}.png",
                    image_data.getvalue(),
                    content_type="image/png",
                )
            )

        with (
            patch(
                "rentals.api_views.insert",
                side_effect=[{"id": 17, "slug": "new-home"}]
                + [{"id": 18 + index} for index in range(5)],
            ) as insert_record,
            patch("rentals.api_views.rows", return_value=[]),
            patch(
                "rentals.api_views.upload_listing_photo",
                side_effect=lambda photo, listing_id, position: {
                    "listing_id": listing_id,
                    "image": f"https://storage.example/house-{position}.png",
                    "caption": "",
                    "position": position,
                },
            ) as upload_photo,
            patch(
                "rentals.api_forms.subprocess.run",
                return_value=SimpleNamespace(
                    stdout='{"format":{"duration":"120"},"streams":[{"codec_type":"video"}]}'
                ),
            ),
            patch(
                "rentals.api_views.upload_listing_video",
                return_value="https://storage.example/house.mp4",
            ) as upload_video,
            patch(
                "rentals.api_views.update",
                return_value={"id": 17, "video_url": "https://storage.example/house.mp4"},
            ) as update_listing,
        ):
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
                    "landlord_whatsapp": "+2348099999999",
                    "status": "draft",
                    "action": "save",
                    "photos": photos,
                    "video": SimpleUploadedFile(
                        "house.mp4",
                        b"video",
                        content_type="video/mp4",
                    ),
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("staff_records"))
        self.assertEqual(upload_photo.call_count, 5)
        self.assertEqual(
            [call.args[1:] for call in upload_photo.call_args_list],
            [(17, index) for index in range(5)],
        )
        self.assertEqual(insert_record.call_count, 6)
        upload_video.assert_called_once()
        self.assertEqual(upload_video.call_args.args[1], 17)
        update_listing.assert_called_once_with(
            "rental_listings",
            17,
            {"video_url": "https://storage.example/house.mp4"},
        )

    def test_staff_listing_rejects_more_than_five_photos(self):
        from .api_forms import StaffRentalListingForm

        base_data = {
            "title": "Verified family home",
            "description": "A verified listing.",
            "city": "Abuja",
            "state": "FCT",
            "transaction_type": "rent",
            "annual_rent": "2400000",
            "bedrooms": "3",
            "bathrooms": "2",
            "landlord_whatsapp": "+2348099999999",
            "category": "home",
            "status": "draft",
        }
        photos = [
            SimpleUploadedFile(f"house-{index}.png", b"image", content_type="image/png")
            for index in range(6)
        ]
        form = StaffRentalListingForm(
            data=base_data,
            files=MultiValueDict({"photos": photos}),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("no more than 5 photos", str(form.errors["photos"]))

    def test_staff_listing_requires_an_international_whatsapp_number(self):
        from .api_forms import StaffRentalListingForm

        data = {
            "title": "Verified family home",
            "description": "A verified listing.",
            "city": "Abuja",
            "state": "FCT",
            "transaction_type": "rent",
            "annual_rent": "2400000",
            "bedrooms": "3",
            "bathrooms": "2",
            "category": "home",
            "status": "draft",
            "landlord_whatsapp": "08012345678",
        }
        form = StaffRentalListingForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("international WhatsApp number", str(form.errors["landlord_whatsapp"]))

    def test_staff_listing_video_must_not_exceed_three_minutes(self):
        from .api_forms import StaffRentalListingForm

        base_data = {
            "title": "Verified family home",
            "description": "A verified listing.",
            "city": "Abuja",
            "state": "FCT",
            "transaction_type": "rent",
            "annual_rent": "2400000",
            "bedrooms": "3",
            "bathrooms": "2",
            "landlord_whatsapp": "+2348099999999",
            "category": "home",
            "status": "draft",
        }
        video_metadata = SimpleNamespace(
            stdout='{"format":{"duration":"180"},"streams":[{"codec_type":"video"}]}'
        )
        with patch(
            "rentals.api_forms.subprocess.run",
            return_value=video_metadata,
        ) as probe:
            form = StaffRentalListingForm(
                data=base_data,
                files=MultiValueDict(
                    {
                        "video": [
                            SimpleUploadedFile(
                                "house.mp4",
                                b"video",
                                content_type="video/mp4",
                            )
                        ]
                    }
                ),
            )
            self.assertTrue(form.is_valid(), form.errors)
        probe.assert_called_once()

        video_metadata.stdout = (
            '{"format":{"duration":"180.1"},"streams":[{"codec_type":"video"}]}'
        )
        with patch(
            "rentals.api_forms.subprocess.run",
            return_value=video_metadata,
        ):
            form = StaffRentalListingForm(
                data=base_data,
                files=MultiValueDict(
                    {
                        "video": [
                            SimpleUploadedFile(
                                "house.mp4",
                                b"video",
                                content_type="video/mp4",
                            )
                        ]
                    }
                ),
            )
            self.assertFalse(form.is_valid())
        self.assertIn("3 minutes", str(form.errors["video"]))

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
