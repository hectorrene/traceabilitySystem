# ========================================
# MODELOS DE DJANGO - SISTEMA DE GESTIÓN DE ÓRDENES DE TRABAJO
# ========================================
# Este archivo define la estructura de datos del sistema de manufactura
# que maneja órdenes de trabajo con seguimiento por etapas de producción

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json

# ========================================
# MODELO DE CELDAS DE TRABAJO
# ========================================

class Cells(models.Model):
    """
    Modelo que representa las celdas de trabajo en el sistema de manufactura.
    Cada celda está asociada a una etapa específica del proceso productivo.
    
    El sistema maneja tres etapas principales:
    - Ensamble: Montaje inicial de componentes
    - Pintura: Aplicación de acabados y recubrimientos  
    - Empaque: Preparación final para envío
    """
    
    # Definición de las etapas disponibles en el proceso
    LINE_TYPE_CHOICES = [
        ('ensamble', 'Ensamble'),
        ('pintura', 'Pintura'),
        ('empaque', 'Empaque')
    ]
    
    # Nombre único de la celda de trabajo (ej: "CELL-001", "PAINT-A")
    work_cell = models.CharField(max_length=100, unique=True)
    
    # Tipo de proceso que se realiza en esta celda
    lineType = models.CharField(max_length=10, choices=LINE_TYPE_CHOICES)
    
    def __str__(self):
        """Representación legible del objeto en el admin de Django"""
        return f"{self.work_cell} - ({self.lineType})"
    
    class Meta:
        verbose_name_plural = "Cells"

# ========================================
# MODELO DE NÚMEROS DE PARTE
# ========================================

class Items(models.Model):
    """
    Modelo que representa los números de parte (ítems) que se fabrican.
    Cada ítem tiene un routing definido que especifica por qué celdas debe pasar.
    
    La relación ManyToMany con Cells define el flujo de trabajo (routing)
    permitiendo que un ítem pase por múltiples etapas del proceso.
    """
    
    # Número de parte único (ej: "ABC123", "MOTOR-V8")
    part_number = models.CharField(max_length=100, unique=True)
    
    # Celdas por las que debe pasar este ítem (routing de manufactura)
    cells = models.ManyToManyField(Cells, related_name='items')
    
    def __str__(self):
        """Representación del objeto en el admin"""
        return self.part_number
    
    def get_valid_cells_json(self):
        """
        Método auxiliar que devuelve las celdas válidas para este ítem
        en formato JSON. Útil para APIs y frontend dinámico.
        
        Returns:
            str: JSON con información de celdas válidas
        """
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

# ========================================
# MODELO DE ÓRDENES DE TRABAJO
# ========================================

class WorkOrders(models.Model):
    """
    Modelo principal que representa una orden de trabajo.
    
    Una orden agrupa múltiples ítems que deben ser procesados juntos
    y sigue un flujo secuencial por las etapas: ensamble -> pintura -> empaque
    
    El sistema rastrea el progreso de la orden a través de las etapas
    y mantiene un historial completo de cuándo se abrió y cerró.
    """
    
    # Número identificador de la orden (ej: "2024-001", "BATCH-A")
    number = models.CharField(max_length=100, db_index=True)  
    
    # Estado de la orden: True = Activa, False = Cerrada
    status = models.BooleanField(default=True)
    
    # Celdas asignadas a esta orden (define dónde se puede trabajar)
    cells = models.ManyToManyField(Cells, related_name='workOrderItems')
    
    # Metadatos de fechas y usuario
    pub_date = models.DateTimeField(default=timezone.now)  # Fecha de creación
    closed_date = models.DateTimeField(null=True, blank=True)  # Fecha de cierre
    closedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)  # Usuario que cerró
    
    # Etapa actual del proceso (controla el flujo de trabajo)
    current_stage = models.CharField(
        max_length=10, 
        choices=[('ensamble', 'Ensamble'), ('pintura', 'Pintura'), ('empaque', 'Empaque')],
        default='ensamble'  # Toda orden comienza en ensamble
    )

    def __str__(self):
        """Representación del objeto mostrando número y estado"""
        return f"WO-{self.number} ({'Active' if self.status else 'Closed'})"
    
    def save(self, *args, **kwargs):
        """
        Override del método save para automatizar el registro de fecha de cierre.
        Cuando una orden se marca como cerrada (status=False), automáticamente
        registra la fecha actual si no se había establecido previamente.
        """
        if not self.status and not self.closed_date:
            self.closed_date = timezone.now()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Work Orders"

# ========================================
# MODELO DE ÍTEMS EN ÓRDENES DE TRABAJO
# ========================================

class WorkOrderItems(models.Model):
    """
    Modelo que representa la relación entre órdenes de trabajo e ítems.
    
    Este modelo implementa el concepto de "serialización automática":
    - Cada ítem se registra con una cantidad solicitada
    - El sistema genera automáticamente números serializados únicos
    - Ejemplo: Si se piden 5 unidades de "MOTOR-V8", se crean:
                MOTOR-V8-01, MOTOR-V8-02, MOTOR-V8-03, etc.
    
    Esta serialización permite rastrear cada pieza individual a través
    del proceso de manufactura.
    """
    
    # Relación con la orden de trabajo padre
    workorders = models.ForeignKey(WorkOrders, on_delete=models.CASCADE, related_name='work_order_items')
    
    # Relación con el ítem base (número de parte)
    items = models.ForeignKey(Items, on_delete=models.CASCADE, related_name='work_order_items')
    
    # Cantidad solicitada (usada para generar serializaciones)
    quantity = models.PositiveIntegerField(default=1)
    
    # Número de parte serializado único (ej: "MOTOR-V8-01")
    # Este campo se genera automáticamente durante la creación de la orden
    serialized_part_number = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        """
        Representación que muestra el número serializado o el básico con cantidad
        """
        if self.serialized_part_number:
            return f"{self.serialized_part_number} - {self.items.part_number}"
        return f"{self.items.part_number} (Qty: {self.quantity})"
    
    class Meta:
        verbose_name_plural = "Work Order Items"

# ========================================
# MODELO DE ESCANEOS/REGISTROS
# ========================================

class Scans(models.Model):
    """
    Modelo que registra cada escaneo de una pieza en el sistema.
    
    Cada vez que un operador escanea una pieza con el lector de códigos,
    se crea un registro en esta tabla. El sistema usa estos registros para:
    - Rastrear el progreso de cada ítem individual
    - Validar que las piezas estén en la etapa correcta
    - Detectar duplicados y errores de proceso
    - Generar estadísticas de producción
    
    El modelo mantiene una relación con WorkOrderItems para vincular
    cada escaneo con la orden específica y el ítem correspondiente.
    """
    
    # Relación con el ítem específico de la orden
    workOrderItems = models.ForeignKey(WorkOrderItems, on_delete=models.CASCADE, related_name='scans')
    
    # Relación directa con el ítem base (para consultas optimizadas)
    items = models.ForeignKey(Items, on_delete=models.CASCADE, related_name='scans')
    
    # Timestamp del escaneo (cuándo se registró)
    timestamp = models.DateTimeField(default=timezone.now)
    
    # Cantidad de ítems escaneados en esta operación (típicamente 1)
    scanned_items = models.PositiveIntegerField(default=1)
    
    def __str__(self):
        """Representación que muestra qué se escaneó y cuándo"""
        return f"Scan - {self.items.part_number} at {self.timestamp}"
    
    class Meta:
        verbose_name_plural = "Scans"

# ========================================
# MODELO DE ERRORES DEL SISTEMA
# ========================================

class Errors(models.Model):
    """
    Modelo que registra todos los errores y excepciones que ocurren
    durante el proceso de escaneo y seguimiento.
    
    El sistema detecta automáticamente varios tipos de errores:
    - Piezas que no pertenecen a la orden actual
    - Intentos de escanear la misma pieza múltiples veces
    - Piezas en etapas incorrectas del proceso
    - Excesos de cantidad en celdas específicas
    
    Este modelo es crucial para:
    - Auditoria y control de calidad
    - Identificación de problemas de proceso
    - Entrenamiento de operadores
    - Análisis de eficiencia del sistema
    """
    
    # Tipos de errores que puede detectar el sistema
    ERROR_CHOICES = [
        ('exceeded_limit', 'Excedió el límite de piezas en esta celda'),
        ('missing_parts', 'Faltan piezas en esta celda'),
        ('already_entered', 'Esta pieza ya fue ingresada'),
        ('wrong_work_order', 'Esta pieza no pertenece a esta orden de trabajo'),
        ('wrong_cell', 'Esta pieza no debería estar aún en esta celda'),
    ]
    
    # Relación con la orden de trabajo donde ocurrió el error
    workorders = models.ForeignKey(WorkOrders, on_delete=models.CASCADE, related_name='errors')
    
    # Relación con el ítem que causó el error
    items = models.ForeignKey(Items, on_delete=models.CASCADE, related_name='errors')
    
    # Tipo de error ocurrido (uno de ERROR_CHOICES)
    error = models.CharField(max_length=20, choices=ERROR_CHOICES)
    
    # Timestamp de cuándo ocurrió el error
    pub_date = models.DateTimeField(default=timezone.now)
    
    # Descripción detallada del error (contexto adicional)
    description = models.TextField(blank=True)
    
    def __str__(self):
        """Representación que muestra tipo de error y orden afectada"""
        return f"Error: {self.get_error_display()} - {self.workorders.number}"
    
    class Meta:
        verbose_name_plural = "Errors"