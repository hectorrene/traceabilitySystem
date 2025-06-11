from django.urls import path
from .views import (activeOrdersListView, registerWorkOrder, registerPartNumber, closedOrdersListView, closedOrdersDetailView, LoginView, LogoutView,
                    receipts_view, add_scan_view, close_order_view, confirm_close_order_view, partNumbersListView)

urlpatterns = [
    path("", LoginView.as_view(template_name="system/login.html"), name="login"),
    path('logout/', LogoutView.as_view(), name='logout'), 
    path("ordenes-abiertas/", activeOrdersListView.as_view(), name="activeWorkOrders"), 
    path("ordenes/<int:order_id>/", receipts_view, name="activeWorkOrdersDetail"),
    path("ordenes/<int:order_id>/agregar-escaneo/", add_scan_view, name="add_scan"),
    path("ordenes/<int:order_id>/cerrar/", close_order_view, name="close_order"),
    path("ordenes/<int:order_id>/confirmar-cierre/", confirm_close_order_view, name="confirm_close_order"),
    path("registrar-orden/", registerWorkOrder.as_view(), name="registerWorkOrder"),
    path("registrar-parte/", registerPartNumber.as_view(), name="registerPartNumber"),
    path("numeros-de-parte/", partNumbersListView.as_view(), name="partNumbers"),
    path("ordenes-cerradas/", closedOrdersListView.as_view(), name="closedWorkOrders"),  
    path("ordenes-cerradas/<int:pk>/", closedOrdersDetailView.as_view(), name="closedWorkOrdersDetail"),
]