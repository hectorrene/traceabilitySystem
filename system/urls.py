from django.urls import path
from .views import (activeOrdersListView, RegisterWorkOrder, registerPartNumber, closedOrdersListView, closedOrdersDetailView, LoginView, LogoutView,
                    receipts_view, add_scan_view, close_order_view, confirm_close_order_view, partNumbersListView, advance_to_next_stage, errors_view,
                    partNumbersDetailView, noAccess, engineerGuide)

urlpatterns = [
    path("", LoginView.as_view(template_name="system/login.html"), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("ordenes-abiertas/", activeOrdersListView.as_view(), name="activeWorkOrders"), 
    path("ordenes/<int:order_id>/", receipts_view, name="activeWorkOrdersDetail"),
    path("ordenes/<int:order_id>/agregar-escaneo/", add_scan_view, name="add_scan"),
    path("ordenes/<int:order_id>/cerrar/", close_order_view, name="close_order"),
    path("ordenes/<int:order_id>/siguiente-etapa/", advance_to_next_stage, name="advance_to_next_stage"),
    path("ordenes/<int:order_id>/confirmar-cierre/", confirm_close_order_view, name="confirm_close_order"),
    path("registrar-orden/", RegisterWorkOrder.as_view(), name="registerWorkOrder"),
    path("registrar-parte/", registerPartNumber.as_view(), name="registerPartNumber"),
    path("numeros-de-parte/", partNumbersListView.as_view(), name="partNumbers"),
    path("numeros-de-parte/<int:pk>/", partNumbersDetailView.as_view(), name="partNumberDetails"),
    path("ordenes-cerradas/", closedOrdersListView.as_view(), name="closedWorkOrders"),  
    path("ordenes-cerradas/<int:pk>/", closedOrdersDetailView.as_view(), name="closedWorkOrdersDetail"),
    path('errores/', errors_view, name='errors'),
    path('pantalla-restringida/', noAccess, name='noAccess'),
    path('guia-ingenieros/', engineerGuide, name='engineerGuide')
]