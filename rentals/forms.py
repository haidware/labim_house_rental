from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.forms import inlineformset_factory

from .models import InspectionRequest, ListingPhoto, OwnerProfile, RentalListing


class OwnerAccountRequestForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    phone = forms.CharField(max_length=40)
    owner_type = forms.ChoiceField(choices=OwnerProfile.OwnerType.choices)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "owner_type",
        )


class OwnerListingForm(forms.ModelForm):
    def __init__(self, *args, owner_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner_type == OwnerProfile.OwnerType.HOME:
            self.fields["transaction_type"].choices = (
                (RentalListing.TransactionType.RENT, "For rent"),
            )

    class Meta:
        model = RentalListing
        fields = (
            "title",
            "description",
            "address",
            "city",
            "state",
            "property_type",
            "transaction_type",
            "annual_rent",
            "sale_price",
            "bedrooms",
            "bathrooms",
        )
        labels = {
            "annual_rent": "Annual rent (NGN)",
            "sale_price": "Sale price (NGN)",
            "property_type": "Property type/details",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get("transaction_type")
        annual_rent = cleaned_data.get("annual_rent")
        sale_price = cleaned_data.get("sale_price")

        if transaction_type == RentalListing.TransactionType.RENT:
            if not annual_rent:
                self.add_error("annual_rent", "Enter the annual rent.")
            cleaned_data["sale_price"] = None
        elif transaction_type == RentalListing.TransactionType.SALE:
            if not sale_price:
                self.add_error("sale_price", "Enter the sale price.")
            cleaned_data["annual_rent"] = None
        return cleaned_data


class PublicInspectionRequestForm(forms.ModelForm):
    class Meta:
        model = InspectionRequest
        fields = (
            "guest_name",
            "email",
            "phone",
            "preferred_date",
            "message",
        )
        labels = {
            "guest_name": "Full name",
            "email": "Email address",
            "phone": "Phone / WhatsApp",
            "preferred_date": "Preferred viewing date",
            "message": "Message",
        }
        widgets = {
            "preferred_date": forms.DateInput(attrs={"type": "date"}),
            "message": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Anything else Rooms should know?"}
            ),
        }


ListingPhotoFormSet = inlineformset_factory(
    RentalListing,
    ListingPhoto,
    fields=("image", "caption", "position"),
    extra=3,
    can_delete=True,
)
