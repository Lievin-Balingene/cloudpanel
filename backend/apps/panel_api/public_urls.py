from django.urls import path

from apps.panel_api.views import UapiExecuteView, WhmJsonApiView

urlpatterns = [
    path("json-api/<str:function>", WhmJsonApiView.as_view(), name="whm-json-api"),
    path("json-api/<str:function>/", WhmJsonApiView.as_view(), name="whm-json-api-slash"),
    path("execute/<str:module>/<str:function>", UapiExecuteView.as_view(), name="uapi-execute"),
    path("execute/<str:module>/<str:function>/", UapiExecuteView.as_view(), name="uapi-execute-slash"),
]
