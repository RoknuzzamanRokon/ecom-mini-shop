from django.urls import path

from .views import RulesView

app_name = "rules"

urlpatterns = [
    path("", RulesView.as_view(), name="rules"),
]
