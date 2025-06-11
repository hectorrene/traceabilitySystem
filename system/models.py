from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json

# Cells and their line type are defined here
class Cells(models.Model):
    LINE_TYPE_CHOICES = [
        ('small', 'Small'),
        ('medium', 'Medium'),
        ('large', 'Large'),
        ('varnish', 'Varnish'),
        ('polish', 'Polish'),
        ('paint', 'Paint'),
    ]
    work_cell = models.CharField(max_length=100, unique=True)
    lineType = models.CharField(max_length=10, choices=LINE_TYPE_CHOICES)
    
    # This is how the data is returned in django admin
    def __str__(self):
        return f"{self.work_cell} - ({self.lineType})"
    
    class Meta:
        verbose_name_plural = "Cells"

# Items are the part numbers and their routing
class Items(models.Model):
    part_number = models.CharField(max_length=100, unique=True)
    cells = models.ManyToManyField(Cells, related_name='items')
    
    # This is how the data is returned in django admin
    def __str__(self):
        return self.part_number
    
    # This method returns a JSON representation of the valid cells for this item
    def get_valid_cells_json(self):
        cells_data = []
        for cell in self.cells.all(): 
            cells_data.append({
                'id': cell.id,
                'name': cell.work_cell
            })
        return json.dumps(cells_data)
    
    class Meta:
        verbose_name_plural = "Items"

# Work orders' numbers are declared here. Separated from items to allow for multiple items per work order.
class WorkOrders(models.Model):
    number = models.CharField(max_length=100, db_index=True)  
    status = models.BooleanField(default=True)  # active or closed
    cells = models.ManyToManyField(Cells, related_name='workOrderItems')
    pub_date = models.DateTimeField(default=timezone.now)
    closed_date = models.DateTimeField(null=True, blank=True)  
    closedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # This is how the data is returned in django admin
    def __str__(self):
        return f"WO-{self.number} ({'Active' if self.status else 'Closed'})"
    
    # When work order is closed, set the closed date to now 
    def save(self, *args, **kwargs):
        if not self.status and not self.closed_date:
            self.closed_date = timezone.now()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Work Orders"

# Work order items are the items that belong to a work order and their quantity
class WorkOrderItems(models.Model):
    workorders = models.ForeignKey(WorkOrders, on_delete=models.CASCADE, related_name='work_order_items')
    items = models.ForeignKey(Items, on_delete=models.CASCADE, related_name='work_order_items')
    quantity = models.PositiveIntegerField(default=1)
    
    # This is how the data is returned in django admin
    def __str__(self):
        return f"{self.workorders.number} - {self.items.part_number} (Qty: {self.quantity})"
    
    class Meta:
        verbose_name_plural = "Work Order Items"

# Scans are the records of items scanned in a work order
class Scans(models.Model):
    workOrderItems = models.ForeignKey(WorkOrderItems, on_delete=models.CASCADE, related_name='scans')
    items = models.ForeignKey(Items, on_delete=models.CASCADE, related_name='scans')
    timestamp = models.DateTimeField(default=timezone.now)
    scanned_items = models.PositiveIntegerField(default=1)
    
    # This is how the data is returned in django admin
    def __str__(self):
        return f"Scan - {self.items.part_number} at {self.timestamp}"
    
    class Meta:
        verbose_name_plural = "Scans"

# Any error that may occur while scanning items is recorded here
class Errors(models.Model):
    ERROR_CHOICES = [
        ('exceeded_limit', 'Excedió el límite de piezas en esta celda'),
        ('missing_parts', 'Faltan piezas en esta celda'),
        ('already_entered', 'Esta pieza ya fue ingresada'),
        ('wrong_work_order', 'Esta pieza no pertenece a esta orden de trabajo'),
        ('wrong_cell', 'Esta pieza no debería estar aún en esta celda'),
    ]
    
    workorders = models.ForeignKey(WorkOrders, on_delete=models.CASCADE, related_name='errors')
    items = models.ForeignKey(Items, on_delete=models.CASCADE, related_name='errors')
    error = models.CharField(max_length=20, choices=ERROR_CHOICES)
    pub_date = models.DateTimeField(default=timezone.now)
    description = models.TextField(blank=True)
    
    # This is how the data is returned in django admin
    def __str__(self):
        return f"Error: {self.get_error_display()} - {self.workorders.number}"
    
    class Meta:
        verbose_name_plural = "Errors"