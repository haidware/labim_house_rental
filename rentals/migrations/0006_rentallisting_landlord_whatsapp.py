import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rentals", "0005_rentallisting_video_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentallisting",
            name="landlord_whatsapp",
            field=models.CharField(
                blank=True,
                default="",
                max_length=40,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Enter an international WhatsApp number with country code.",
                        regex="^\\+[1-9]\\d{7,14}$",
                    )
                ],
            ),
        ),
    ]
