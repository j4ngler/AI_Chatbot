# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    legal_chatbot_api_url = fields.Char(
        string='URL API chatbot pháp luật',
        help='Ví dụ: http://127.0.0.1:8000 — dùng cho tích hợp với dịch vụ FastAPI trong cùng dự án.',
    )
