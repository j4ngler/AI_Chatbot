# -*- coding: utf-8 -*-
{
    'name': 'Luật Mai Trang — Nền ERP & tích hợp',
    'version': '19.0.1.0.0',
    'category': 'Administration',
    'summary': 'Gói tùy chỉnh quản trị doanh nghiệp trên Odoo, gắn với dự án Chatbot pháp luật',
    'description': """
        Module cơ sở cho các mở rộng nghiệp vụ (kế toán, kho, CRM…) và cấu hình URL API chatbot
        trên từng công ty (luật / tra cứu).
    """,
    'depends': ['base', 'web'],
    'data': [
        'views/res_company_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'author': 'Luật Mai Trang',
}
