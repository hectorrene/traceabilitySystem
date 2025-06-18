from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json

# Aquí se definen las celdas y el tipo de celda
class Cells(models.Model):
    LINE_TYPE_CHOICES = [
        ('ensamble', 'Ensamble'),
        ('pintura', 'Pintura'),
        ('empaque', 'Empaque')
    ]
    work_cell = models.CharField(max_length=100, unique=True)
    lineType = models.CharField(max_length=10, choices=LINE_TYPE_CHOICES)
    
    # Así se ve en el django admin 
    def __str__(self):
        return f"{self.work_cell} - ({self.lineType})"
    
    class Meta:
        verbose_name_plural = "Cells"

# Aquí se definen los numeros de parte y su routeo
class Items(models.Model):
    part_number = models.CharField(max_length=100, unique=True)
    cells = models.ManyToManyField(Cells, related_name='items')
    
    # Así se ve en el django admin
    def __str__(self):
        return self.part_number
    
    # Devuelve las celdas de un numero de parte en especifico
    def get_valid_cells_json(self):
        cells_data = []
        for cell in self.cells.all(): 
            cells_data.append({
                'id': cell.id,
                'name': cell.work_cell,
                'lineType': cell.lineType
            })
        return json.dumps(cells_data)
    
    class Meta:
        verbose_name_plural = "Items"

# Aquí se declara el nombre de la orden de trabajo, los numeros de parte van aparte
class WorkOrders(models.Model):
    number = models.CharField(max_length=100, db_index=True)  
    status = models.BooleanField(default=True)  # active or closed
    cells = models.ManyToManyField(Cells, related_name='workOrderItems')
    pub_date = models.DateTimeField(default=timezone.now)
    closed_date = models.DateTimeField(null=True, blank=True)  
    closedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Así se ve en el django admin
    def __str__(self):
        return f"WO-{self.number} ({'Active' if self.status else 'Closed'})"
    
    # Pone la fecha en la que se cierra la orden de trabajo
    def save(self, *args, **kwargs):
        if not self.status and not self.closed_date:
            self.closed_date = timezone.now()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Work Orders"

# Los números de parte pertenecientes a la orden de trabajo
class WorkOrderItems(models.Model):
    workorders = models.ForeignKey(WorkOrders, on_delete=models.CASCADE, related_name='work_order_items')
    items = models.ForeignKey(Items, on_delete=models.CASCADE, related_name='work_order_items')
    quantity = models.PositiveIntegerField(default=1)
    serialized_part_number = models.CharField(max_length=100, blank=True, null=True)
    
    # Así se ve en el django admin
    def __str__(self):
        if self.serialized_part_number:
            return f"{self.serialized_part_number} - {self.items.part_number}"
        return f"{self.items.part_number} (Qty: {self.quantity})"
    
    class Meta:
        verbose_name_plural = "Work Order Items"

# Scans de los numeros de parte en la orden de trabajo
class Scans(models.Model):
    workOrderItems = models.ForeignKey(WorkOrderItems, on_delete=models.CASCADE, related_name='scans')
    items = models.ForeignKey(Items, on_delete=models.CASCADE, related_name='scans')
    timestamp = models.DateTimeField(default=timezone.now)
    scanned_items = models.PositiveIntegerField(default=1)
    
    # Así se ve en el django admin
    def __str__(self):
        return f"Scan - {self.items.part_number} at {self.timestamp}"
    
    class Meta:
        verbose_name_plural = "Scans"

# Aquí se guardan los errores 
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
    
    # Así se ve en el django admin
    def __str__(self):
        return f"Error: {self.get_error_display()} - {self.workorders.number}"
    
    class Meta:
        verbose_name_plural = "Errors"