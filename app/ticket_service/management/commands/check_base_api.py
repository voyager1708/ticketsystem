"""
BASE_API_URL（TICKETSYSTEM/ベースAPI）への疎通確認

使用方法:
    python manage.py check_base_api

コンテナ内で実行する例（WSL で Docker 起動後）:
    docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ticket_web python manage.py check_base_api
    python manage.py check_base_api --insecure   # 自己署名証明書などで SSL エラーになる場合
"""
import urllib3
import requests
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Check connectivity to BASE_API_URL (ベースAPI)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout',
            type=int,
            default=10,
            help='Request timeout in seconds (default: 10)',
        )
        parser.add_argument(
            '--insecure',
            action='store_true',
            help='Skip SSL certificate verification (for internal/self-signed certs)',
        )

    def handle(self, *args, **options):
        timeout = options['timeout']
        verify = not options['insecure']
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        base_url = getattr(settings, 'BASE_API_URL', None) or ''
        base_url = base_url.rstrip('/')

        if not base_url:
            self.stderr.write(self.style.ERROR('BASE_API_URL is not set in settings/.env'))
            return

        self.stdout.write(f'BASE_API_URL = {base_url}')
        if not verify:
            self.stdout.write(self.style.WARNING('SSL verification: OFF (--insecure)'))
        self.stdout.write('')

        try:
            r = requests.get(base_url, timeout=timeout, verify=verify)
            self.stdout.write(self.style.SUCCESS(f'  GET {base_url}  ->  {r.status_code}'))
        except requests.exceptions.SSLError as e:
            self.stdout.write(self.style.WARNING(f'  GET {base_url}  ->  SSL error (try --insecure if using internal CA)'))
            self.stderr.write(str(e)[:200])
        except requests.exceptions.RequestException as e:
            self.stderr.write(self.style.ERROR(f'  GET {base_url}  ->  {e}'))
