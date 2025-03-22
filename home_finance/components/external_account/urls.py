from django.urls import re_path

from home_finance.components.external_account.views import index

urlpatterns = [
    re_path('', index, name='index'),
]