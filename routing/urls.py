from django.urls import path
from .views import calculate_route

urlpatterns = [
    path('route/', calculate_route, name='calculate_route'),
]

