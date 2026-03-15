# Remove Account model (local api/accounts 廃止、sign-up は ext/v1/auth/sign-up でベースAPIに委譲)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ticket_service', '0002_account'),
    ]

    operations = [
        migrations.DeleteModel(name='Account'),
    ]
