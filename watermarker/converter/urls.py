from django.urls import path
from .views import watermark, reveal_watermark

urlpatterns = [
    path('', watermark, name='watermark'),
    path('reveal/', reveal_watermark, name='reveal_watermark'),
]