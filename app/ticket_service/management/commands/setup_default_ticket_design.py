"""
デフォルトのTicketDesignを作成するマネジメントコマンド

使用方法:
    python manage.py setup_default_ticket_design

環境変数:
    TICKET_DESIGN_NAME: デザイン名（デフォルト: "Default"）
    TICKET_DESIGN_TEMPLATE_IMAGE: テンプレート画像のパス（オプション）
    TICKET_DESIGN_REWARD_IMAGE: 報酬画像のパス（オプション）
    TICKET_DESIGN_LAYOUT: レイアウトJSON（オプション）
"""
import os
import json
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from ticket_service.models import TicketDesign


class Command(BaseCommand):
    help = 'Setup default TicketDesign from environment variables'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update existing default design',
        )
        parser.add_argument(
            '--name',
            type=str,
            help='Design name (overrides TICKET_DESIGN_NAME env var)',
        )

    def handle(self, *args, **options):
        # 環境変数から設定を取得
        design_name = options.get('name') or os.environ.get('TICKET_DESIGN_NAME', 'Default')
        template_image_path = os.environ.get('TICKET_DESIGN_TEMPLATE_IMAGE', '')
        reward_image_path = os.environ.get('TICKET_DESIGN_REWARD_IMAGE', '')
        layout_json = os.environ.get('TICKET_DESIGN_LAYOUT', '{}')
        
        # レイアウトJSONをパース
        try:
            layout = json.loads(layout_json) if layout_json else {}
        except json.JSONDecodeError:
            self.stderr.write(self.style.WARNING(f'Invalid TICKET_DESIGN_LAYOUT JSON, using empty dict'))
            layout = {}
        
        # 既存のデザインを確認
        existing_design = TicketDesign.objects.filter(name=design_name).first()
        
        if existing_design and not options['force']:
            self.stdout.write(self.style.WARNING(
                f'TicketDesign "{design_name}" already exists (id={existing_design.id}). '
                f'Use --force to update.'
            ))
            return
        
        if existing_design:
            design = existing_design
            self.stdout.write(f'Updating existing TicketDesign "{design_name}"...')
        else:
            design = TicketDesign(name=design_name)
            self.stdout.write(f'Creating new TicketDesign "{design_name}"...')
        
        # レイアウトを設定
        if layout:
            design.layout = layout
            self.stdout.write(f'  Layout: {json.dumps(layout)[:100]}...')
        
        # テンプレート画像を設定
        if template_image_path and os.path.exists(template_image_path):
            with open(template_image_path, 'rb') as f:
                filename = os.path.basename(template_image_path)
                design.template_image.save(filename, File(f), save=False)
                self.stdout.write(f'  Template image: {filename}')
        elif template_image_path:
            self.stderr.write(self.style.WARNING(
                f'  Template image not found: {template_image_path}'
            ))
        
        # 報酬画像を設定
        if reward_image_path and os.path.exists(reward_image_path):
            with open(reward_image_path, 'rb') as f:
                filename = os.path.basename(reward_image_path)
                design.checkin_reward_image.save(filename, File(f), save=False)
                self.stdout.write(f'  Reward image: {filename}')
        elif reward_image_path:
            self.stderr.write(self.style.WARNING(
                f'  Reward image not found: {reward_image_path}'
            ))
        
        # アクティブに設定
        design.is_active = True
        design.save()
        
        self.stdout.write(self.style.SUCCESS(
            f'TicketDesign "{design_name}" (id={design.id}) setup complete!'
        ))
        self.stdout.write(f'  is_active: {design.is_active}')
        self.stdout.write(f'  has_template_image: {bool(design.template_image)}')
        self.stdout.write(f'  has_reward_image: {bool(design.checkin_reward_image)}')

