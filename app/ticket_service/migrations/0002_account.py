# Generated manually for Account model (事前実装: POST /api/accounts)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ticket_service', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Account',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(max_length=150, unique=True)),
                ('password', models.CharField(max_length=128)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'ticket_system_account',
                'ordering': ['-created_at'],
            },
        ),
    ]
