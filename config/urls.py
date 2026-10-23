from django.contrib import admin
from django.urls import path

from rentals.views import dashboard

admin.site.site_header = "Labim House Rentals"
admin.site.site_title = "House Rental Admin"
admin.site.index_title = "Property management"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("admin/", admin.site.urls),
]
