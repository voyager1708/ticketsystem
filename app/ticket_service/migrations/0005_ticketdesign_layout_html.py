# HTML template layout for TicketDesign (layout_html)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ticket_service', '0004_recreate_account'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticketdesign',
            name='layout_html',
            field=models.TextField(blank=True, help_text='HTML template for ticket layout (placeholders: {{ event_name }}, {{ event_date }}, {{ venue }}, {{ seat }}, {{ qr_data_url }}, {{ background_base64 }})', null=True),
        ),
    ]
