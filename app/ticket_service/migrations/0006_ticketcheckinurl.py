# TicketCheckinUrl: nft_origin -> checkin_url をDBに保存

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ticket_service', '0005_ticketdesign_layout_html'),
    ]

    operations = [
        migrations.CreateModel(
            name='TicketCheckinUrl',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nft_origin', models.CharField(db_index=True, max_length=256, unique=True)),
                ('checkin_url', models.URLField(max_length=2048)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'ticket_system_ticket_checkin_url',
                'ordering': ['-created_at'],
            },
        ),
    ]
