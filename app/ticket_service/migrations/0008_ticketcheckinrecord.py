from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ticket_service", "0007_alter_ticketdesign_layout_html"),
    ]

    operations = [
        migrations.CreateModel(
            name="TicketCheckinRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nft_origin", models.CharField(db_index=True, max_length=256, unique=True)),
                ("used_at", models.DateTimeField()),
                ("checked_in_by", models.CharField(blank=True, default="", max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "ticket_system_ticket_checkin_record",
                "ordering": ["-used_at"],
            },
        ),
    ]
