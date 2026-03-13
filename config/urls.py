from django.urls import path
from core import views
urlpatterns = [
    path('', views.home, name='home'),
    path('camera/', views.camera, name='camera'),
    path('editor/', views.editor, name='editor'),
    path('ar-preview/', views.ar_preview, name='ar_preview'),
    path('api/detect/', views.detect_flower, name='detect_flower'),
    path('api/save-bouquet/', views.save_bouquet, name='save_bouquet'),
]
