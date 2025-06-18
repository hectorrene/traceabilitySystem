from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from .models import Items,  Errors, WorkOrderItems, WorkOrders, Scans, Cells
from django.utils import timezone
from django.urls import reverse_lazy
from django.db.models import Sum, Q
from django.db import IntegrityError, models
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from datetime import timedelta
from django.core.paginator import Paginator
import datetime, json

def user_in_allowed_groups(user):
    return user.groups.filter(name__in=['admin', 'ingenieros']).exists()

def noAccess(request):
    """Página que se muestra cuando no tiene permisos"""
    return render(request, 'system/sin_permisos.html', status=403)

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
class RegisterWorkOrder(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = WorkOrders  
    template_name = 'system/registerWorkOrder.html'
    fields = [] 
    success_url = reverse_lazy('activeWorkOrders')
    
    def test_func(self):
        """Verificar si el usuario pertenece a admin o ingenieros"""
        return self.request.user.groups.filter(name__in=['admin', 'ingenieros']).exists()
    
    def handle_no_permission(self):
        """Qué hacer cuando no tiene permisos"""
        if not self.request.user.is_authenticated:
            # Si no está logueado, redirigir a login
            return self.redirect_to_login(self.request.get_full_path())
        else:
            # Si está logueado pero no tiene permisos, redirigir a página de error
            return redirect('noAccess')

    def post(self, request, *args, **kwargs):
        work_order = WorkOrders.objects.create(
            number=request.POST.get('number'),
            status=True
        )
        
        # Assign cells to the work order
        selected_cells = request.POST.getlist('cells')
        if selected_cells:
            work_order.cells.set(selected_cells)
        
        # Assign part numbers to the work order with serialization
        part_numbers = request.POST.getlist('part_number')
        quantities = request.POST.getlist('quantity')
        
        for part_id, quantity in zip(part_numbers, quantities):
            if part_id and quantity:
                # Obtener el objeto Items para acceder al part_number
                item = Items.objects.get(id=part_id)
                base_part_number = item.part_number  # Suponiendo que este es el campo con el número de parte
                
                # Crear múltiples items con serialización
                quantity_int = int(quantity)
                for i in range(1, quantity_int + 1):
                    # Formatear el número de serie con ceros a la izquierda (ej: 01, 02, 03...)
                    serial_suffix = f"{i:02d}"
                    serialized_part_number = f"{base_part_number}-{serial_suffix}"
                    
                    # Crear un WorkOrderItem individual con quantity=1 y el part_number serializado
                    WorkOrderItems.objects.create(
                        workorders=work_order,
                        items_id=part_id,
                        quantity=1,  # Cada item serializado tiene quantity=1
                        serialized_part_number=serialized_part_number  # Nuevo campo para almacenar el número serializado
                    )
        
        return redirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['parts'] = Items.objects.all()
        context['cells'] = Cells.objects.all()
        return context

# Registrar un número de parte
class registerPartNumber(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Items
    template_name = 'system/registerPartNumber.html'
    fields = ['part_number', 'cells']
    success_url = reverse_lazy('activeWorkOrders')

    def test_func(self):
        """Verificar si el usuario pertenece a admin o ingenieros"""
        return self.request.user.groups.filter(name__in=['admin', 'ingenieros']).exists()
    
    def handle_no_permission(self):
        """Qué hacer cuando no tiene permisos"""
        if not self.request.user.is_authenticated:
            # Si no está logueado, redirigir a login
            return self.redirect_to_login(self.request.get_full_path())
        else:
            # Si está logueado pero no tiene permisos, redirigir a página de error
            return redirect('noAccess')

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
class partNumbersListView (LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Items
    template_name = "system/partNumbers.html"
    context_object_name = 'pieces'

    def test_func(self):
        """Verificar si el usuario pertenece a admin o ingenieros"""
        return self.request.user.groups.filter(name__in=['admin', 'ingenieros']).exists()
    
    def handle_no_permission(self):
        """Qué hacer cuando no tiene permisos"""
        if not self.request.user.is_authenticated:
            # Si no está logueado, redirigir a login
            return self.redirect_to_login(self.request.get_full_path())
        else:
            # Si está logueado pero no tiene permisos, redirigir a página de error
            return redirect('noAccess')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        return context

# Detalles de los numeros de parte
class partNumbersDetailView(DetailView):
    model = Items
    template_name = 'system/partNumberDetails.html'
    context_object_name = 'items'

    def test_func(self):
        """Verificar si el usuario pertenece a admin o ingenieros"""
        return self.request.user.groups.filter(name__in=['admin', 'ingenieros']).exists()
    
    def handle_no_permission(self):
        """Qué hacer cuando no tiene permisos"""
        if not self.request.user.is_authenticated:
            # Si no está logueado, redirigir a login
            return self.redirect_to_login(self.request.get_full_path())
        else:
            # Si está logueado pero no tiene permisos, redirigir a página de error
            return redirect('noAccess')
        
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

def receipts_view(request, order_id):
    """Vista principal de la pantalla de escaneo - WO-M338845"""
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Obtener la celda actual basada en la etapa
    try:
        current_cell = work_order.cells.get(lineType=work_order.current_stage)
    except Cells.DoesNotExist:
        messages.error(request, f"No hay celda configurada para la etapa {work_order.current_stage}")
        return redirect('activeWorkOrders')
    
    # Obtener todos los items de la orden con sus escaneos en la celda actual
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order).select_related('items')
    
    # Preparar datos de progreso por cada item
    progress_data = []
    total_items = 0
    total_scanned = 0
    
    for item in work_order_items:
        # Contar escaneos en la celda actual para este item específico
        scanned_count = Scans.objects.filter(
            workOrderItems=item,
            items=item.items
        ).count()
        
        # El item serializado cuenta como 1 pieza
        expected_count = 1
        total_items += expected_count
        total_scanned += min(scanned_count, expected_count)
        
        progress_data.append({
            'item': item,
            'scanned': scanned_count,
            'expected': expected_count,
            'completed': scanned_count >= expected_count,
            'cells_assigned': list(item.items.cells.values('work_cell', 'lineType'))
        })
    
    # Verificar si se puede avanzar a la siguiente etapa
    can_advance = total_scanned == total_items and total_items > 0
    
    # Verificar si se puede cerrar la orden (todas las etapas completadas)
    can_close_order = False
    if can_advance and work_order.current_stage == 'empaque':
        can_close_order = True
    
    context = {
        'work_order': work_order,
        'current_cell': current_cell,
        'progress_data': progress_data,
        'total_items': total_items,
        'total_scanned': total_scanned,
        'can_advance': can_advance,
        'can_close_order': can_close_order,
        'progress_percentage': (total_scanned / total_items * 100) if total_items > 0 else 0
    }
    
    return render(request, 'system/activeWorkOrdersDetail.html', context)

def add_scan_view(request, order_id):
    """Vista para agregar un escaneo via AJAX"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    try:
        data = json.loads(request.body)
        scanned_part = data.get('part_number', '').strip()
        current_cell_name = data.get('work_cell', '').strip()
        
        if not scanned_part or not current_cell_name:
            return JsonResponse({'success': False, 'error': 'Datos incompletos'})
        
        # Verificar que la celda existe y corresponde a la etapa actual
        try:
            current_cell = Cells.objects.get(work_cell=current_cell_name, lineType=work_order.current_stage)
        except Cells.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Celda no válida para la etapa actual'})
        
        # Buscar el WorkOrderItem con el número de parte serializado
        try:
            work_order_item = WorkOrderItems.objects.get(
                workorders=work_order,
                serialized_part_number=scanned_part
            )
        except WorkOrderItems.DoesNotExist:
            # Error: Esta pieza no pertenece a esta orden de trabajo
            Errors.objects.create(
                workorders=work_order,
                items_id=1,  # Necesitarás ajustar esto
                error='wrong_work_order',
                description=f'Pieza escaneada: {scanned_part} no pertenece a WO-{work_order.number}'
            )
            return JsonResponse({
                'success': False, 
                'error': 'Esta pieza no pertenece a esta orden de trabajo',
                'error_type': 'wrong_work_order'
            })
        
        # Verificar que la pieza puede estar en esta celda (routing correcto)
        if not work_order_item.items.cells.filter(lineType=work_order.current_stage).exists():
            # Error: Esta pieza no debería estar aún en esta celda
            Errors.objects.create(
                workorders=work_order,
                items=work_order_item.items,
                error='wrong_cell',
                description=f'Pieza {scanned_part} no tiene routing para {work_order.current_stage}'
            )
            return JsonResponse({
                'success': False,
                'error': 'Esta pieza no debería estar aún en esta celda',
                'error_type': 'wrong_cell'
            })
        
        # Verificar si ya fue escaneada en esta celda
        existing_scan = Scans.objects.filter(
            workOrderItems=work_order_item,
            items=work_order_item.items
        ).first()
        
        if existing_scan:
            # Error: Esta pieza ya fue ingresada
            Errors.objects.create(
                workorders=work_order,
                items=work_order_item.items,
                error='already_entered',
                description=f'Pieza {scanned_part} ya fue escaneada en {work_order.current_stage}'
            )
            return JsonResponse({
                'success': False,
                'error': 'Esta pieza ya fue ingresada',
                'error_type': 'already_entered'
            })
        
        # Crear el escaneo
        scan = Scans.objects.create(
            workOrderItems=work_order_item,
            items=work_order_item.items,
            scanned_items=1
        )
        
        # Recalcular progreso
        total_items = WorkOrderItems.objects.filter(workorders=work_order).count()
        scanned_items = Scans.objects.filter(
            workOrderItems__workorders=work_order
        ).count()
        
        return JsonResponse({
            'success': True,
            'message': f'Pieza {scanned_part} registrada correctamente',
            'progress': {
                'scanned': scanned_items,
                'total': total_items,
                'percentage': (scanned_items / total_items * 100) if total_items > 0 else 0
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Datos JSON inválidos'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error interno: {str(e)}'})

def advance_to_next_stage(request, order_id):
    """Avanzar a la siguiente etapa del proceso"""
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Verificar que todas las piezas de la etapa actual estén escaneadas
    total_items = WorkOrderItems.objects.filter(workorders=work_order).count()
    scanned_items = Scans.objects.filter(
        workOrderItems__workorders=work_order
    ).count()
    
    if scanned_items < total_items:
        messages.error(request, 'Debes escanear todas las piezas antes de avanzar')
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Determinar siguiente etapa
    stage_order = ['ensamble', 'pintura', 'empaque']
    current_index = stage_order.index(work_order.current_stage)
    
    if current_index < len(stage_order) - 1:
        # Limpiar escaneos para la nueva etapa
        Scans.objects.filter(workOrderItems__workorders=work_order).delete()
        
        # Avanzar etapa
        work_order.current_stage = stage_order[current_index + 1]
        work_order.save()
        
        messages.success(request, f'Avanzado a etapa: {work_order.current_stage}')
    else:
        messages.info(request, 'Ya estás en la última etapa')
    
    return redirect('activeWorkOrdersDetail', order_id=order_id)

def close_order_view(request, order_id):
    """Cerrar orden de trabajo"""
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Verificar que está en la etapa final y todas las piezas están escaneadas
    if work_order.current_stage != 'empaque':
        messages.error(request, 'Debes completar todas las etapas antes de cerrar')
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    total_items = WorkOrderItems.objects.filter(workorders=work_order).count()
    scanned_items = Scans.objects.filter(
        workOrderItems__workorders=work_order
    ).count()
    
    if scanned_items < total_items:
        messages.error(request, 'Debes escanear todas las piezas antes de cerrar')
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    return render(request, 'system/confirm_close_order.html', {'work_order': work_order})

def confirm_close_order_view(request, order_id):
    """Confirmar cierre de orden"""
    if request.method == 'POST':
        work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
        work_order.status = False
        work_order.closedBy = request.user
        work_order.save()
        
        messages.success(request, f'Orden WO-{work_order.number} cerrada correctamente')
        return redirect('activeWorkOrders')
    
    return redirect('activeWorkOrdersDetail', order_id=order_id)
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