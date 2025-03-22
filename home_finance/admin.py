# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.admin import AdminSite
from home_finance.components.external_account.models import ExternalAccount
from home_finance.components.category.models import Category
from home_finance.components.transaction.models import Transaction
from django.contrib import admin


class MyAdminSite(AdminSite):
    site_header = 'Home Finance Project'

class ExternalAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'interest_rate', 'notes')

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'parent')

class TransactionAdmin(admin.ModelAdmin):
    list_display = ('description', 'account', 'amount', 'date', 'notes', 'transfer_account', 'reconciled')

admin_site = MyAdminSite(name='myadmin')
admin_site.register(ExternalAccount, ExternalAccountAdmin)
admin_site.register(Category, CategoryAdmin)
admin_site.register(Transaction, TransactionAdmin)
