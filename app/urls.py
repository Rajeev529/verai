from django.urls import path
from . import views
 
urlpatterns = [
    path("v1/context",  views.context),
    path("v1/tick",     views.tick),
    path("v1/reply",    views.reply),
    path("v1/healthz",  views.healthz),
    path("v1/metadata", views.metadata),
]
 