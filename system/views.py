from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from .models import Items,  Errors, WorkOrderItems, WorkOrders, Scans, Cells
from django.utils import timezone
from django.urls import reverse_lazy
from django.db.models import Sum, Q
from django.db import IntegrityError, models
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from datetime import timedelta
from django.core.paginator import Paginator
import datetime, json

# Ordenes de trabajo activas
class activeOrdersListView(ListView):
    model = WorkOrders  
    template_name = 'system/activeWorkOrders.html'
    context_object_name = 'orders'
    paginate_by = 50

    def get_queryset(self):
        # Filtrar órdenes activas directamente
        queryset = WorkOrders.objects.filter(status=True).order_by("-pub_date")

        # Filtrar por tipo de celda
        line_type = self.request.GET.get('line_type')
        if line_type and line_type != 'all':
            queryset = queryset.filter(items__cells__lineType=line_type).distinct()
        
        # Filtro por celda específica 
        cell_id = self.request.GET.get('cell')
        if cell_id and cell_id != 'all':
            try:
                queryset = queryset.filter(items__cells__lineType__id=int(cell_id)).distinct()
            except (ValueError, TypeError):
                pass 
        
        return queryset 
    
    # Gets all cells
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        context['line_types'] = Cells.LINE_TYPE_CHOICES
        context['current_line_type'] = self.request.GET.get('line_type', 'all')
        context['current_cell'] = self.request.GET.get('cell', 'all')
        return context

# Registrar una orden de trabajo
class registerWorkOrder(CreateView):
    model = WorkOrders  
    template_name = 'system/registerWorkOrder.html'
    fields = [] 
    success_url = reverse_lazy('activeWorkOrders')  

    # Create a new work order
    def post(self, request, *args, **kwargs):
        work_order = WorkOrders.objects.create(
            number=request.POST.get('number'),
            status=True
        )
        
        # Assign cells to the work order
        selected_cells = request.POST.getlist('cells')
        if selected_cells:
            work_order.cells.set(selected_cells)
        
        # Assign part numbers to the work order
        part_numbers = request.POST.getlist('part_number')
        quantities = request.POST.getlist('quantity')
        
        for part_id, quantity in zip(part_numbers, quantities):
            if part_id and quantity:
                WorkOrderItems.objects.create(
                    workorders=work_order,
                    items_id=part_id,
                    quantity=int(quantity)
                )
        
        return redirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['parts'] = Items.objects.all()
        context['cells'] = Cells.objects.all()
        return context

# Registrar un número de parte
class registerPartNumber(CreateView):
    model = Items
    template_name = 'system/registerPartNumber.html'
    fields = ['part_number', 'cells']
    success_url = reverse_lazy('activeWorkOrders')

    def form_valid(self, form):
        # Verificar si el part_number ya existe antes de intentar guardar
        part_number = form.cleaned_data['part_number']
        if Items.objects.filter(part_number=part_number).exists():
            form.add_error('part_number', 'Este número de parte ya está registrado.')
            messages.error(self.request, "Ese número de parte ya está registrado.")
            return self.form_invalid(form)
        
        # Si no existe, proceder normalmente
        form.instance.pub_date = timezone.now()
        response = super().form_valid(form)
        messages.success(self.request, "Número de parte registrado correctamente.")
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Error al registrar el número de parte. Verifica los campos.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        contexts = super().get_context_data(**kwargs)
        contexts['cells'] = Cells.objects.all()
        return contexts
    
# Ordenes de trabajo cerradas 
class closedOrdersListView(ListView):
    model = WorkOrders  
    template_name = 'system/closedOrders.html'
    context_object_name = 'orders'
    paginate_by = 50

    def get_queryset(self):
        # Filtrar órdenes activas directamente
        queryset = WorkOrders.objects.filter(status=False).order_by("-pub_date")

        # Filtrar por tipo de celda
        line_type = self.request.GET.get('line_type')
        if line_type and line_type != 'all':
            queryset = queryset.filter(items__cells__lineType=line_type).distinct()
        
        # Filtro por celda específica 
        cell_id = self.request.GET.get('cell')
        if cell_id and cell_id != 'all':
            try:
                queryset = queryset.filter(items__cells__lineType__id=int(cell_id)).distinct()
            except (ValueError, TypeError):
                pass 
        
        return queryset 
    
    # Gets all cells
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        context['line_types'] = Cells.LINE_TYPE_CHOICES
        context['current_line_type'] = self.request.GET.get('line_type', 'all')
        context['current_cell'] = self.request.GET.get('cell', 'all')
        return context
    
# Detalles de ordenes de trabajo cerradas
class closedOrdersDetailView(DetailView):
    model = WorkOrderItems
    template_name = 'system/closedOrderDetails.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return WorkOrders.objects.filter(status=False)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        work_order_items = WorkOrderItems.objects.filter(workorders=self.object).select_related('items')
        context['scans'] = Scans.objects.filter(workOrderItems__in=work_order_items)
        return context
    
# Todos los numeros de parte
class partNumbersListView (ListView):
    model = Items
    template_name = "system/partNumbers.html"
    context_object_name = 'pieces'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        return context

# Detalles de los numeros de parte
class partNumbersDetailView(DetailView):
    model = Items
    template_name = 'system/partNumberDetails.html'
    context_object_name = 'items'

# Todos los errores 
def errors_view(request):
    errors_list = Errors.objects.select_related('workorders', 'items').order_by('-pub_date')
    
    # Filtros
    search_query = request.GET.get('search', '')
    error_type = request.GET.get('error_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    work_order_filter = request.GET.get('work_order', '')
    
    # Aplicar filtros
    if search_query:
        errors_list = errors_list.filter(
            Q(workorders__number__icontains=search_query) |
            Q(items__part_number__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if error_type:
        errors_list = errors_list.filter(error=error_type)
    
    if work_order_filter:
        errors_list = errors_list.filter(workorders__number__icontains=work_order_filter)
    
    if date_from:
        try:
            date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d')
            errors_list = errors_list.filter(pub_date__date__gte=date_from_parsed.date())
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d')
            errors_list = errors_list.filter(pub_date__date__lte=date_to_parsed.date())
        except ValueError:
            pass
    
    # Paginación
    paginator = Paginator(errors_list, 20)  # 20 errores por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Estadísticas básicas
    total_errors = errors_list.count()
    today_errors = errors_list.filter(pub_date__date=timezone.now().date()).count()
    week_errors = errors_list.filter(pub_date__date__gte=timezone.now().date() - timedelta(days=7)).count()
    
    # Obtener tipos de error para el filtro
    error_types = Errors.ERROR_CHOICES
    
    # Obtener órdenes de trabajo activas para el filtro
    active_work_orders = WorkOrders.objects.filter(status=True).order_by('number')
    
    context = {
        'page_obj': page_obj,
        'total_errors': total_errors,
        'today_errors': today_errors,
        'week_errors': week_errors,
        'error_types': error_types,
        'active_work_orders': active_work_orders,
        'search_query': search_query,
        'error_type': error_type,
        'date_from': date_from,
        'date_to': date_to,
        'work_order_filter': work_order_filter,
    }
    
    return render(request, 'system/errors.html', context)

@login_required
def receipts_view(request, order_id):
    """Vista principal de scaneo y visualización de progreso"""
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Inicializar sesión si no existe
    session_key = f'wo_{order_id}'
    if session_key not in request.session:
        request.session[session_key] = {
            'current_cell_type': 'ensamble',
            'cell_type_index': 0,
        }
    
    session_data = request.session[session_key]
    current_cell_type = session_data['current_cell_type']
    
    # Obtener celdas disponibles para la etapa actual
    available_cells = Cells.objects.filter(lineType=current_cell_type)
    
    # Obtener work order items con progreso
    work_order_items_data = []
    all_items_complete = True
    can_proceed_to_next_cell = True
    
    work_order_items = WorkOrderItems.objects.filter(
        workorders=work_order
    ).select_related('items').prefetch_related('scans')
    
    for wo_item in work_order_items:
        # Calcular scans para la etapa actual únicamente
        current_scans = Scans.objects.filter(
            workOrderItems=wo_item,
            items=wo_item.items
        ).aggregate(total=Sum('scanned_items'))['total'] or 0
        
        # Para el cálculo de progreso por etapa actual
        remaining_quantity = max(0, wo_item.quantity - current_scans)
        progress_percentage = min(100, (current_scans / wo_item.quantity) * 100) if wo_item.quantity > 0 else 0
        is_complete = current_scans >= wo_item.quantity
        
        # Para verificar si puede proceder a siguiente etapa
        if not is_complete:
            can_proceed_to_next_cell = False
        
        # Para verificar si puede cerrar la orden (necesita scans en las 3 etapas)
        total_required_scans = wo_item.quantity * 3  # 3 etapas
        total_scans = Scans.objects.filter(
            workOrderItems=wo_item,
            items=wo_item.items
        ).aggregate(total=Sum('scanned_items'))['total'] or 0
        
        if total_scans < total_required_scans:
            all_items_complete = False
        
        work_order_items_data.append({
            'item': wo_item,
            'part_number': wo_item.items.part_number,
            'required_quantity': wo_item.quantity,
            'scanned_quantity': current_scans,
            'remaining_quantity': remaining_quantity,
            'progress_percentage': progress_percentage,
            'is_complete': is_complete,
        })
    
    # Calcular progreso general
    if work_order_items_data:
        overall_progress = sum(item['progress_percentage'] for item in work_order_items_data) / len(work_order_items_data)
    else:
        overall_progress = 0
    
    # Determinar siguiente etapa
    cell_type_index = session_data['cell_type_index']
    next_cell_type = None
    if cell_type_index < 2:  # 0=ensamble, 1=pintura, 2=empaque
        next_types = ['ensamble', 'pintura', 'empaque']
        next_cell_type = next_types[cell_type_index + 1]
    
    # Obtener scans y errores recientes
    recent_scans = Scans.objects.filter(
        workOrderItems__workorders=work_order
    ).select_related('items').order_by('-timestamp')[:10]
    
    recent_errors = Errors.objects.filter(
        workorders=work_order
    ).select_related('items').order_by('-pub_date')[:5]
    
    context = {
        'work_order': work_order,
        'current_cell_type': current_cell_type,
        'available_cells': available_cells,
        'work_order_items': work_order_items_data,
        'recent_scans': recent_scans,
        'recent_errors': recent_errors,
        'can_proceed_to_next_cell': can_proceed_to_next_cell,
        'next_cell_type': next_cell_type,
        'overall_progress': overall_progress,
        'all_items_complete': all_items_complete,
        'order_id': order_id,
    }
    
    return render(request, 'system/activeWorkOrdersDetail.html', context)

@login_required
def add_scan_view(request, order_id):
    """Procesar scans con validaciones completas"""
    if request.method != 'POST':
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Obtener parámetros del POST
    celda_trabajo = request.POST.get('celda_trabajo', '').strip()
    numero_parte = request.POST.get('numero_parte', '').strip()
    cantidad_str = request.POST.get('cantidad', '1').strip()
    
    try:
        cantidad = int(cantidad_str)
        if cantidad <= 0:
            raise ValueError("Cantidad debe ser mayor a 0")
    except ValueError:
        messages.error(request, "Error: Cantidad inválida")
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Obtener estado de sesión
    session_key = f'wo_{order_id}'
    if session_key not in request.session:
        messages.error(request, "Error: Sesión inválida")
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    current_cell_type = request.session[session_key]['current_cell_type']
    
    # Validación 1: Verificar que Items.part_number existe
    try:
        item = Items.objects.get(part_number=numero_parte)
    except Items.DoesNotExist:
        Errors.objects.create(
            workorders=work_order,
            items=None,
            error='wrong_work_order',
            description=f"Part number {numero_parte} no existe en el sistema"
        )
        messages.error(request, "Error: Esta pieza no pertenece a esta orden de trabajo")
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Validación 2: Verificar que pertenece a WorkOrderItems de esta orden
    try:
        wo_item = WorkOrderItems.objects.get(workorders=work_order, items=item)
    except WorkOrderItems.DoesNotExist:
        Errors.objects.create(
            workorders=work_order,
            items=item,
            error='wrong_work_order',
            description=f"Part number {numero_parte} no pertenece a la orden {work_order.number}"
        )
        messages.error(request, "Error: Esta pieza no pertenece a esta orden de trabajo")
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Validación 3: Verificar celda correcta según flujo
    try:
        selected_cell = Cells.objects.get(work_cell=celda_trabajo)
        if selected_cell.lineType != current_cell_type:
            Errors.objects.create(
                workorders=work_order,
                items=item,
                error='wrong_cell',
                description=f"Celda {celda_trabajo} es tipo {selected_cell.lineType}, pero la etapa actual es {current_cell_type}"
            )
            messages.error(request, "Error: Esta pieza no debería estar aún en esta celda")
            return redirect('activeWorkOrdersDetail', order_id=order_id)
    except Cells.DoesNotExist:
        messages.error(request, "Error: Celda de trabajo no válida")
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Validación 4: Verificar límite de cantidad
    current_scans = Scans.objects.filter(
        workOrderItems=wo_item,
        items=item
    ).aggregate(total=Sum('scanned_items'))['total'] or 0
    
    if current_scans + cantidad > wo_item.quantity:
        Errors.objects.create(
            workorders=work_order,
            items=item,
            error='exceeded_limit',
            description=f"Intentó escanear {cantidad} piezas, pero solo quedan {wo_item.quantity - current_scans} disponibles"
        )
        messages.error(request, "Error: Excedió el límite de piezas en esta celda")
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Validación 5: Verificar duplicados recientes (últimos 5 minutos)
    five_minutes_ago = timezone.now() - timedelta(minutes=5)
    recent_scan = Scans.objects.filter(
        workOrderItems=wo_item,
        items=item,
        timestamp__gte=five_minutes_ago
    ).exists()
    
    if recent_scan:
        Errors.objects.create(
            workorders=work_order,
            items=item,
            error='already_entered',
            description=f"Scan duplicado detectado para {numero_parte} en los últimos 5 minutos"
        )
        messages.error(request, "Error: Esta pieza ya fue ingresada")
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Si todas las validaciones pasan, crear el scan
    Scans.objects.create(
        workOrderItems=wo_item,
        items=item,
        scanned_items=cantidad
    )
    
    messages.success(request, f"Éxito: Escaneadas {cantidad} piezas de {numero_parte}")
    return redirect('activeWorkOrdersDetail', order_id=order_id)

@login_required
def advance_to_next_stage(request, order_id):
    """Cambiar automáticamente a siguiente etapa"""
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    session_key = f'wo_{order_id}'
    if session_key not in request.session:
        messages.error(request, "Error: Sesión inválida")
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    session_data = request.session[session_key]
    current_index = session_data['cell_type_index']
    
    # Verificar que etapa actual esté 100% completa
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order)
    
    for wo_item in work_order_items:
        current_scans = Scans.objects.filter(
            workOrderItems=wo_item,
            items=wo_item.items
        ).aggregate(total=Sum('scanned_items'))['total'] or 0
        
        if current_scans < wo_item.quantity:
            messages.error(request, "Error: No se puede avanzar. Faltan piezas por escanear en la etapa actual")
            return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Avanzar a siguiente etapa
    if current_index < 2:  # 0=ensamble, 1=pintura, 2=empaque
        new_index = current_index + 1
        cell_types = ['ensamble', 'pintura', 'empaque']
        new_cell_type = cell_types[new_index]
        
        request.session[session_key] = {
            'current_cell_type': new_cell_type,
            'cell_type_index': new_index,
        }
        
        messages.success(request, f"Éxito: Avanzado a etapa de {new_cell_type}")
    else:
        messages.info(request, "Ya está en la última etapa")
    
    return redirect('activeWorkOrdersDetail', order_id=order_id)

@login_required
def close_order_view(request, order_id):
    """Mostrar pantalla de confirmación de cierre"""
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Calcular items incompletos
    incomplete_items = []
    can_close = True
    
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order)
    
    for wo_item in work_order_items:
        total_required = wo_item.quantity * 3  # 3 etapas
        total_scanned = Scans.objects.filter(
            workOrderItems=wo_item,
            items=wo_item.items
        ).aggregate(total=Sum('scanned_items'))['total'] or 0
        
        if total_scanned < total_required:
            can_close = False
            incomplete_items.append({
                'part_number': wo_item.items.part_number,
                'completed': total_scanned,
                'required': total_required
            })
    
    context = {
        'work_order': work_order,
        'incomplete_items': incomplete_items,
        'can_close': can_close,
        'order_id': order_id,
    }
    
    return render(request, 'system/close_order.html', context)

@login_required
def confirm_close_order_view(request, order_id):
    """Ejecutar cierre definitivo de orden"""
    if request.method != 'POST':
        return redirect('close_order', order_id=order_id)
    
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Verificar que se puede cerrar
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order)
    
    for wo_item in work_order_items:
        total_required = wo_item.quantity * 3
        total_scanned = Scans.objects.filter(
            workOrderItems=wo_item,
            items=wo_item.items
        ).aggregate(total=Sum('scanned_items'))['total'] or 0
        
        if total_scanned < total_required:
            messages.error(request, "Error: No se puede cerrar la orden. Hay items incompletos")
            return redirect('close_order', order_id=order_id)
    
    # Cerrar la orden
    work_order.status = False
    work_order.closed_date = timezone.now()
    work_order.closedBy = request.user
    work_order.save()
    
    # Limpiar sesión
    session_key = f'wo_{order_id}'
    if session_key in request.session:
        del request.session[session_key]
    
    messages.success(request, f"Orden {work_order.number} cerrada exitosamente")
    return redirect('activeWorkOrders')