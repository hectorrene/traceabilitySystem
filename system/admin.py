from django.contrib import admin
from .models import Cells, Items, WorkOrders, WorkOrderItems, Scans, Errors

admin.site.register(Cells)
admin.site.register(Items)
admin.site.register(WorkOrders)
admin.site.register(WorkOrderItems)
admin.site.register(Scans)
admin.site.register(Errors)