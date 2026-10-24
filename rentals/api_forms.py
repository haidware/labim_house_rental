from django import forms
from PIL import Image, UnidentifiedImageError

from .models import OwnerProfile, RentalListing


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class StaffLoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)


class OwnerAccountRequestForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=40)
    owner_type = forms.ChoiceField(
        choices=((OwnerProfile.OwnerType.LAND, "Land or property owner"),)
    )
    password1 = forms.CharField(
        min_length=10,
        widget=forms.PasswordInput,
        label="Password",
    )
    password2 = forms.CharField(
        min_length=10,
        widget=forms.PasswordInput,
        label="Confirm password",
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password1")
        confirmation = cleaned_data.get("password2")
        if password and confirmation and password != confirmation:
            self.add_error("password2", "The passwords do not match.")
        return cleaned_data


class PropertyListingRequestForm(forms.Form):
    PROPERTY_TYPES = (
        ("house", "House"),
        ("apartment", "Apartment / flat"),
        ("duplex", "Duplex"),
        ("bungalow", "Bungalow"),
        ("room", "Room / self-contained"),
        ("other", "Other"),
    )

    owner_name = forms.CharField(max_length=160, label="Your name")
    phone = forms.CharField(max_length=40, label="Phone number")
    property_type = forms.ChoiceField(
        choices=PROPERTY_TYPES,
        label="Type of property for rent",
    )
    address = forms.CharField(
        max_length=500,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "Street, area, city and state"}
        ),
        label="Full property address",
    )
    terms_accepted = forms.BooleanField(
        label=(
            "I confirm that I own or am authorized to represent this property, "
            "that it is available for rent, and I agree Rooms may contact me "
            "and visit the address to verify it. I understand this request "
            "does not guarantee a listing or publication."
        )
    )


class OwnerListingForm(forms.Form):
    TRANSACTION_TYPES = (
        (RentalListing.TransactionType.RENT, "For rent"),
        (RentalListing.TransactionType.SALE, "For sale"),
    )

    title = forms.CharField(max_length=180)
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}))
    address = forms.CharField(max_length=240, required=False)
    city = forms.CharField(max_length=100)
    state = forms.CharField(max_length=100)
    property_type = forms.CharField(max_length=60, required=False)
    transaction_type = forms.ChoiceField(choices=TRANSACTION_TYPES)
    annual_rent = forms.IntegerField(min_value=1, required=False, label="Annual rent (NGN)")
    sale_price = forms.IntegerField(min_value=1, required=False, label="Sale price (NGN)")
    bedrooms = forms.IntegerField(min_value=0, max_value=99, initial=1)
    bathrooms = forms.IntegerField(min_value=0, max_value=99, initial=1)
    photos = forms.FileField(
        required=False,
        widget=MultipleFileInput(attrs={"accept": "image/*"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get("transaction_type")
        if transaction_type == RentalListing.TransactionType.RENT:
            if not cleaned_data.get("annual_rent"):
                self.add_error("annual_rent", "Enter the annual rent.")
            cleaned_data["sale_price"] = None
        elif transaction_type == RentalListing.TransactionType.SALE:
            if not cleaned_data.get("sale_price"):
                self.add_error("sale_price", "Enter the sale price.")
            cleaned_data["annual_rent"] = None
        return cleaned_data

    def clean_photos(self):
        photos = self.files.getlist("photos")
        if len(photos) > 3:
            raise forms.ValidationError("Upload no more than three photos.")
        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        for photo in photos:
            extension = "." + photo.name.rsplit(".", 1)[-1].lower() if "." in photo.name else ""
            if extension not in allowed_extensions:
                raise forms.ValidationError(
                    "Photos must be JPG, PNG, or WEBP files."
                )
            if photo.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Each photo must be 5 MB or smaller.")
            try:
                image = Image.open(photo)
                image.verify()
            except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as error:
                raise forms.ValidationError(
                    "Each uploaded photo must be a valid image."
                ) from error
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise forms.ValidationError(
                    "Photos must be JPG, PNG, or WEBP files."
                )
            photo.image_format = image.format
            photo.seek(0)
        return photos


class StaffRentalListingForm(OwnerListingForm):
    category = forms.ChoiceField(choices=RentalListing.Category.choices)
    status = forms.ChoiceField(choices=RentalListing.PublicationStatus.choices)
