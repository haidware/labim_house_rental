from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class RentalListing(models.Model):
    class PublicationStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RENTED = "rented", "Rented"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    description = models.TextField()
    address = models.CharField(max_length=240, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    property_type = models.CharField(max_length=60, blank=True)
    bedrooms = models.PositiveSmallIntegerField(default=1)
    bathrooms = models.PositiveSmallIntegerField(default=1)
    annual_rent = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(
        max_length=12,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "rental listing"
        verbose_name_plural = "rental listings"
        db_table = "rental_listings"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "rental"
            candidate = base_slug
            suffix = 2
            while RentalListing.objects.exclude(pk=self.pk).filter(
                slug=candidate
            ).exists():
                candidate = f"{base_slug}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class ListingPhoto(models.Model):
    listing = models.ForeignKey(
        RentalListing,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(upload_to="rental-listings/%Y/%m/")
    caption = models.CharField(max_length=160, blank=True)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "id")
        db_table = "rental_listing_photos"

    def __str__(self):
        return f"Photo for {self.listing}"


class InspectionRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    listing = models.ForeignKey(
        RentalListing,
        on_delete=models.PROTECT,
        related_name="inspection_requests",
    )
    guest_name = models.CharField(max_length=160)
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    preferred_date = models.DateField(null=True, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    staff_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "inspection request"
        verbose_name_plural = "inspection requests"
        db_table = "rental_inspection_requests"

    def __str__(self):
        return f"{self.guest_name} — {self.listing}"


class RentalAdminProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rental_admin_profile",
    )
    phone = models.CharField(max_length=40, blank=True)

    class Meta:
        db_table = "rental_admin_profiles"

    def __str__(self):
        return f"Rental admin profile for {self.user}"
