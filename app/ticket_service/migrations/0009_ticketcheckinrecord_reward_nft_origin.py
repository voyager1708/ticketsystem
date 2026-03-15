from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ticket_service", "0008_ticketcheckinrecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticketcheckinrecord",
            name="reward_nft_origin",
            field=models.CharField(blank=True, default="", max_length=256),
        ),
    ]
