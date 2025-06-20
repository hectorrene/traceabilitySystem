# Sistema de Gestión de Órdenes de Trabajo
# Este archivo contiene las vistas (views) de Django para manejar las operaciones
# principales del sistema: creación, visualización y cierre de órdenes de trabajo

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

def engineerGuide (request):
    return render (request, 'system/engineerGuide.html')

# ========================================
# FUNCIONES AUXILIARES Y PERMISOS
# ========================================

def user_in_allowed_groups(user):
    """
    Verifica si un usuario pertenece a los grupos autorizados para realizar operaciones administrativas.
    
    Args:
        user: Usuario de Django a verificar
        
    Returns:
        bool: True si el usuario pertenece a 'admin' o 'ingenieros'
    """
    return user.groups.filter(name__in=['admin', 'ingenieros']).exists()

def noAccess(request):
    """
    Página que se muestra cuando un usuario no tiene permisos para acceder a una sección.
    
    Args:
        request: HttpRequest de Django
        
    Returns:
        HttpResponse: Renderiza página de error 403
    """
    return render(request, 'system/sin_permisos.html', status=403)

# ========================================
# VISTAS DE ÓRDENES DE TRABAJO ACTIVAS
# ========================================

class activeOrdersListView(ListView):
    """
    Vista que muestra todas las órdenes de trabajo activas (abiertas).
    Incluye filtros por tipo de línea y celda específica.
    """
    model = WorkOrders  
    template_name = 'system/activeWorkOrders.html'
    context_object_name = 'orders'
    paginate_by = 50  # Muestra 50 órdenes por página

    def get_queryset(self):
        """
        Obtiene las órdenes activas aplicando filtros según los parámetros GET.
        
        Returns:
            QuerySet: Órdenes filtradas y ordenadas por fecha de publicación descendente
        """
        # Filtrar solo órdenes activas (status=True)
        queryset = WorkOrders.objects.filter(status=True).order_by("-pub_date")

        # Aplicar filtro por tipo de línea de producción
        line_type = self.request.GET.get('line_type')
        if line_type and line_type != 'all':
            queryset = queryset.filter(items__cells__lineType=line_type).distinct()
        
        # Aplicar filtro por celda específica
        cell_id = self.request.GET.get('cell')
        if cell_id and cell_id != 'all':
            try:
                queryset = queryset.filter(items__cells__lineType__id=int(cell_id)).distinct()
            except (ValueError, TypeError):
                # Si el ID no es válido, ignorar el filtro
                pass 
        
        return queryset 
    
    def get_context_data(self, **kwargs):
        """
        Añade datos adicionales al contexto para mostrar en la plantilla.
        
        Returns:
            dict: Contexto con celdas, tipos de línea y filtros actuales
        """
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        context['line_types'] = Cells.LINE_TYPE_CHOICES
        context['current_line_type'] = self.request.GET.get('line_type', 'all')
        context['current_cell'] = self.request.GET.get('cell', 'all')
        return context

# ========================================
# REGISTRO DE NUEVAS ÓRDENES DE TRABAJO
# ========================================

class RegisterWorkOrder(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Vista para crear nuevas órdenes de trabajo.
    Solo usuarios de grupos 'admin' e 'ingenieros' pueden acceder.
    """
    model = WorkOrders  
    template_name = 'system/registerWorkOrder.html'
    fields = []  # No usa formulario automático, maneja POST personalizado
    success_url = reverse_lazy('activeWorkOrders')
    
    def test_func(self):
        """Verificar permisos de usuario"""
        return self.request.user.groups.filter(name__in=['admin', 'ingenieros']).exists()
    
    def handle_no_permission(self):
        """Maneja usuarios sin permisos: redirige a login o página de error"""
        if not self.request.user.is_authenticated:
            return self.redirect_to_login(self.request.get_full_path())
        else:
            return redirect('noAccess')

    def post(self, request, *args, **kwargs):
        """
        Procesa la creación de una nueva orden de trabajo con serialización automática.
        
        El sistema toma las cantidades solicitadas y crea items individuales con
        números de serie únicos (ej: PART123-01, PART123-02, etc.)
        """
        # Crear la orden de trabajo principal
        work_order = WorkOrders.objects.create(
            number=request.POST.get('number'),
            status=True  # Nueva orden siempre está activa
        )
        
        # Asignar celdas de producción a la orden
        selected_cells = request.POST.getlist('cells')
        if selected_cells:
            work_order.cells.set(selected_cells)
        
        # Procesar números de parte con serialización automática
        part_numbers = request.POST.getlist('part_number')
        quantities = request.POST.getlist('quantity')
        
        for part_id, quantity in zip(part_numbers, quantities):
            if part_id and quantity:
                # Obtener información del item base
                item = Items.objects.get(id=part_id)
                base_part_number = item.part_number
                
                # Crear items individuales con números serializados
                quantity_int = int(quantity)
                for i in range(1, quantity_int + 1):
                    # Generar número de serie con formato: PART-01, PART-02, etc.
                    serial_suffix = f"{i:02d}"
                    serialized_part_number = f"{base_part_number}-{serial_suffix}"
                    
                    # Crear WorkOrderItem individual (cantidad=1 por item serializado)
                    WorkOrderItems.objects.create(
                        workorders=work_order,
                        items_id=part_id,
                        quantity=1,
                        serialized_part_number=serialized_part_number
                    )
        
        return redirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        """Proporciona datos para el formulario de creación"""
        context = super().get_context_data(**kwargs)
        context['parts'] = Items.objects.all()  # Todos los números de parte disponibles
        context['cells'] = Cells.objects.all()  # Todas las celdas disponibles
        return context

# ========================================
# REGISTRO DE NÚMEROS DE PARTE
# ========================================

class registerPartNumber(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """
    Vista para registrar nuevos números de parte en el sistema.
    Incluye validación para evitar duplicados.
    """
    model = Items
    template_name = 'system/registerPartNumber.html'
    fields = ['part_number', 'cells']
    success_url = reverse_lazy('activeWorkOrders')

    def test_func(self):
        """Verificar permisos de usuario"""
        return self.request.user.groups.filter(name__in=['admin', 'ingenieros']).exists()
    
    def handle_no_permission(self):
        """Maneja usuarios sin permisos"""
        if not self.request.user.is_authenticated:
            return self.redirect_to_login(self.request.get_full_path())
        else:
            return redirect('noAccess')

    def form_valid(self, form):
        """
        Valida y guarda el nuevo número de parte.
        Verifica que no exista duplicado antes de guardar.
        """
        part_number = form.cleaned_data['part_number']
        
        # Verificar si el número de parte ya existe
        if Items.objects.filter(part_number=part_number).exists():
            form.add_error('part_number', 'Este número de parte ya está registrado.')
            messages.error(self.request, "Ese número de parte ya está registrado.")
            return self.form_invalid(form)
        
        # Si no existe, proceder con el guardado
        form.instance.pub_date = timezone.now()
        response = super().form_valid(form)
        messages.success(self.request, "Número de parte registrado correctamente.")
        return response

    def form_invalid(self, form):
        """Maneja errores en el formulario"""
        messages.error(self.request, "Error al registrar el número de parte. Verifica los campos.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        """Proporciona lista de celdas para el formulario"""
        contexts = super().get_context_data(**kwargs)
        contexts['cells'] = Cells.objects.all()
        return contexts

# ========================================
# VISTAS DE ÓRDENES CERRADAS
# ========================================

class closedOrdersListView(ListView):
    """
    Vista que muestra todas las órdenes de trabajo cerradas/completadas.
    Similar a activeOrdersListView pero para órdenes terminadas.
    """
    model = WorkOrders  
    template_name = 'system/closedOrders.html'
    context_object_name = 'orders'
    paginate_by = 50

    def get_queryset(self):
        """Obtiene órdenes cerradas con filtros aplicados"""
        # Filtrar solo órdenes cerradas (status=False)
        queryset = WorkOrders.objects.filter(status=False).order_by("-pub_date")

        # Aplicar mismo sistema de filtros que órdenes activas
        line_type = self.request.GET.get('line_type')
        if line_type and line_type != 'all':
            queryset = queryset.filter(items__cells__lineType=line_type).distinct()
        
        cell_id = self.request.GET.get('cell')
        if cell_id and cell_id != 'all':
            try:
                queryset = queryset.filter(items__cells__lineType__id=int(cell_id)).distinct()
            except (ValueError, TypeError):
                pass 
        
        return queryset 
    
    def get_context_data(self, **kwargs):
        """Contexto para filtros en órdenes cerradas"""
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        context['line_types'] = Cells.LINE_TYPE_CHOICES
        context['current_line_type'] = self.request.GET.get('line_type', 'all')
        context['current_cell'] = self.request.GET.get('cell', 'all')
        return context

class closedOrdersDetailView(DetailView):
    """
    Vista detallada de una orden cerrada específica.
    Muestra todos los items, escaneos realizados y estadísticas.
    """
    model = WorkOrders
    template_name = 'system/closedOrderDetails.html'
    context_object_name = 'orders'

    def get_queryset(self):
        """Solo permite ver órdenes cerradas"""
        return WorkOrders.objects.filter(status=False)
    
    def get_context_data(self, **kwargs):
        """
        Prepara información detallada de la orden cerrada:
        - Items de la orden
        - Escaneos organizados por item
        - Estadísticas totales
        """
        context = super().get_context_data(**kwargs)
        
        # Obtener todos los items de la orden
        work_order_items = WorkOrderItems.objects.filter(
            workorders=self.object
        ).select_related('items')
        
        # Organizar escaneos por item para facilitar visualización
        scans_by_item = {}
        total_scans = 0
        
        for item in work_order_items:
            item_scans = Scans.objects.filter(
                workOrderItems=item
            ).select_related('items').order_by('-timestamp')
            scans_by_item[item.id] = item_scans
            total_scans += item_scans.count()
        
        # Añadir información al contexto
        context.update({
            'work_order_items': work_order_items,
            'scans_by_item': scans_by_item,
            'total_scans': total_scans,
            'cells': self.object.cells.all(),  # Celdas asignadas a esta orden
        })
        return context

# ========================================
# GESTIÓN DE NÚMEROS DE PARTE
# ========================================

class partNumbersListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Vista que lista todos los números de parte registrados en el sistema"""
    model = Items
    template_name = "system/partNumbers.html"
    context_object_name = 'pieces'

    def test_func(self):
        """Solo admin e ingenieros pueden ver números de parte"""
        return self.request.user.groups.filter(name__in=['admin', 'ingenieros']).exists()
    
    def handle_no_permission(self):
        """Maneja acceso no autorizado"""
        if not self.request.user.is_authenticated:
            return self.redirect_to_login(self.request.get_full_path())
        else:
            return redirect('noAccess')

    def get_context_data(self, **kwargs):
        """Añade lista de celdas al contexto"""
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        return context

class partNumbersDetailView(DetailView):
    """Vista detallada de un número de parte específico"""
    model = Items
    template_name = 'system/partNumberDetails.html'
    context_object_name = 'items'

    def test_func(self):
        """Control de acceso para detalles de números de parte"""
        return self.request.user.groups.filter(name__in=['admin', 'ingenieros']).exists()
    
    def handle_no_permission(self):
        """Maneja usuarios sin permisos"""
        if not self.request.user.is_authenticated:
            return self.redirect_to_login(self.request.get_full_path())
        else:
            return redirect('noAccess')

# ========================================
# GESTIÓN DE ERRORES DEL SISTEMA
# ========================================

def errors_view(request):
    """
    Vista completa para visualizar y filtrar errores del sistema.
    Incluye múltiples filtros y estadísticas básicas.
    """
    # Obtener todos los errores con relaciones cargadas para optimizar consultas
    errors_list = Errors.objects.select_related('workorders', 'items').order_by('-pub_date')
    
    # Obtener parámetros de filtrado de la URL
    search_query = request.GET.get('search', '')
    error_type = request.GET.get('error_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    work_order_filter = request.GET.get('work_order', '')
    
    # Aplicar filtros según parámetros
    if search_query:
        # Búsqueda en múltiples campos
        errors_list = errors_list.filter(
            Q(workorders__number__icontains=search_query) |
            Q(items__part_number__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if error_type:
        errors_list = errors_list.filter(error=error_type)
    
    if work_order_filter:
        errors_list = errors_list.filter(workorders__number__icontains=work_order_filter)
    
    # Filtros de fecha con manejo de errores
    if date_from:
        try:
            date_from_parsed = datetime.strptime(date_from, '%Y-%m-%d')
            errors_list = errors_list.filter(pub_date__date__gte=date_from_parsed.date())
        except ValueError:
            pass  # Ignorar fecha inválida
    
    if date_to:
        try:
            date_to_parsed = datetime.strptime(date_to, '%Y-%m-%d')
            errors_list = errors_list.filter(pub_date__date__lte=date_to_parsed.date())
        except ValueError:
            pass  # Ignorar fecha inválida
    
    # Configurar paginación
    paginator = Paginator(errors_list, 20)  # 20 errores por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calcular estadísticas básicas
    total_errors = errors_list.count()
    today_errors = errors_list.filter(pub_date__date=timezone.now().date()).count()
    week_errors = errors_list.filter(
        pub_date__date__gte=timezone.now().date() - timedelta(days=7)
    ).count()
    
    # Preparar datos para filtros en la plantilla
    error_types = Errors.ERROR_CHOICES
    active_work_orders = WorkOrders.objects.filter(status=True).order_by('number')
    
    context = {
        'page_obj': page_obj,
        'total_errors': total_errors,
        'today_errors': today_errors,
        'week_errors': week_errors,
        'error_types': error_types,
        'active_work_orders': active_work_orders,
        # Mantener valores de filtros para mostrar en formulario
        'search_query': search_query,
        'error_type': error_type,
        'date_from': date_from,
        'date_to': date_to,
        'work_order_filter': work_order_filter,
    }
    
    return render(request, 'system/errors.html', context)

# ========================================
# SISTEMA DE ESCANEO Y SEGUIMIENTO
# ========================================

def receipts_view(request, order_id):
    """
    Vista principal para el sistema de escaneo de piezas.
    Muestra el progreso actual y permite el escaneo por etapas.
    
    El sistema maneja 3 etapas: ensamble -> pintura -> empaque
    """
    # Obtener la orden activa
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Determinar celda actual según la etapa del proceso
    try:
        current_cell = work_order.cells.get(lineType=work_order.current_stage)
    except Cells.DoesNotExist:
        messages.error(request, f"No hay celda configurada para la etapa {work_order.current_stage}")
        return redirect('activeWorkOrders')
    
    # Obtener items de la orden con sus relaciones
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order).select_related('items')
    
    # Calcular progreso detallado por cada item
    progress_data = []
    total_items = 0
    total_scanned = 0
    
    for item in work_order_items:
        # Contar escaneos completados para este item específico
        scanned_count = Scans.objects.filter(
            workOrderItems=item,
            items=item.items
        ).count()
        
        # Cada item serializado representa 1 pieza esperada
        expected_count = 1
        total_items += expected_count
        total_scanned += min(scanned_count, expected_count)
        
        # Preparar datos de progreso para la plantilla
        progress_data.append({
            'item': item,
            'scanned': scanned_count,
            'expected': expected_count,
            'completed': scanned_count >= expected_count,
            'cells_assigned': list(work_order.cells.values('work_cell', 'lineType'))
        })
    
    # Determinar estados de control del proceso
    can_advance = total_scanned == total_items and total_items > 0
    can_close_order = can_advance and work_order.current_stage == 'empaque'
    
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
    """
    Endpoint AJAX para registrar escaneos de piezas.
    Maneja toda la lógica de validación y registro de errores.
    
    Returns:
        JsonResponse: Resultado del escaneo (éxito o error con detalles)
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})

    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)

    try:
        # Parsear datos JSON del request
        data = json.loads(request.body)
        scanned_part = data.get('part_number', '').strip()
        current_cell_name = data.get('work_cell', '').strip()

        if not scanned_part or not current_cell_name:
            return JsonResponse({'success': False, 'error': 'Datos incompletos'})

        # Verificar que la celda es válida para la etapa actual
        try:
            current_cell = Cells.objects.get(work_cell=current_cell_name, lineType=work_order.current_stage)
        except Cells.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Celda no válida para la etapa actual'})

        # Buscar el item de la orden con el número serializado escaneado
        try:
            work_order_item = WorkOrderItems.objects.get(
                workorders=work_order,
                serialized_part_number=scanned_part
            )
        except WorkOrderItems.DoesNotExist:
            # Si no se encuentra, intentar con el número base
            base_part_number = scanned_part.split('-')[0] if '-' in scanned_part else scanned_part
            try:
                scanned_item = Items.objects.get(part_number=base_part_number)
            except Items.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': 'Número de parte no encontrado en la orden',
                    'error_type': 'invalid_part'
                })
            
            # Registrar error: pieza no pertenece a esta orden
            error_msg = dict(Errors.ERROR_CHOICES).get('wrong_work_order', 'Error de orden')
            Errors.objects.create(
                workorders=work_order,
                items=scanned_item,
                error='wrong_work_order',
                description=f'Pieza escaneada: {scanned_part} no pertenece a WO-{work_order.number}'
            )
            return JsonResponse({
                'success': False, 
                'error': f'{error_msg}: {scanned_part}',
                'error_type': 'wrong_work_order'
            })

        # Verificar routing: la pieza debe poder procesarse en esta etapa
        if not work_order_item.items.cells.filter(lineType=work_order.current_stage).exists():
            error_msg = dict(Errors.ERROR_CHOICES).get('wrong_cell', 'Error de celda')
            Errors.objects.create(
                workorders=work_order,
                items=work_order_item.items,
                error='wrong_cell',
                description=f'Pieza {scanned_part} no tiene routing para {work_order.current_stage}'
            )
            return JsonResponse({
                'success': False,
                'error': f'{error_msg}: {scanned_part} en {work_order.current_stage}',
                'error_type': 'wrong_cell'
            })

        # Verificar duplicados: evitar escanear la misma pieza dos veces
        existing_scan = Scans.objects.filter(
            workOrderItems=work_order_item,
            items=work_order_item.items
        ).first()

        if existing_scan:
            error_msg = dict(Errors.ERROR_CHOICES).get('already_entered', 'Ya ingresada')
            Errors.objects.create(
                workorders=work_order,
                items=work_order_item.items,
                error='already_entered',
                description=f'Pieza {scanned_part} ya fue escaneada en {work_order.current_stage}'
            )
            return JsonResponse({
                'success': False,
                'error': f'{error_msg}: {scanned_part} en {work_order.current_stage}',
                'error_type': 'already_entered'
            })

        # Todo validado correctamente: crear el escaneo
        scan = Scans.objects.create(
            workOrderItems=work_order_item,
            items=work_order_item.items,
            scanned_items=1
        )

        # Recalcular progreso general de la orden
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

# ========================================
# CONTROL DE FLUJO DE PROCESO
# ========================================

def advance_to_next_stage(request, order_id):
    """
    Avanza una orden de trabajo a la siguiente etapa del proceso.
    Secuencia: ensamble -> pintura -> empaque
    """
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Verificar que todas las piezas de la etapa actual estén completas
    total_items = WorkOrderItems.objects.filter(workorders=work_order).count()
    scanned_items = Scans.objects.filter(
        workOrderItems__workorders=work_order
    ).count()
    
    if scanned_items < total_items:
        messages.error(request, 'Debes escanear todas las piezas antes de avanzar')
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Determinar siguiente etapa en la secuencia
    stage_order = ['ensamble', 'pintura', 'empaque']
    current_index = stage_order.index(work_order.current_stage)
    
    if current_index < len(stage_order) - 1:
        # Limpiar escaneos para preparar nueva etapa
        Scans.objects.filter(workOrderItems__workorders=work_order).delete()
        
        # Avanzar a siguiente etapa
        work_order.current_stage = stage_order[current_index + 1]
        work_order.save()
        
        messages.success(request, f'Avanzado a etapa: {work_order.current_stage}')
    else:
        messages.info(request, 'Ya estás en la última etapa')
    
    return redirect('activeWorkOrdersDetail', order_id=order_id)

# ========================================
# CIERRE DE ÓRDENES DE TRABAJO
# ========================================

def close_order_view(request, order_id):
    """
    Vista para mostrar la página de confirmación de cierre de orden.
    Presenta un resumen completo de la orden antes del cierre definitivo.
    
    Args:
        request: HttpRequest de Django
        order_id: ID de la orden de trabajo a cerrar
        
    Returns:
        HttpResponse: Página de confirmación con estadísticas de la orden
    """
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Verificar que está en la etapa final y todas las piezas están escaneadas
    if work_order.current_stage != 'empaque':
        messages.error(request, 'Debes completar todas las etapas antes de cerrar')
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Verificar completitud antes de permitir cierre
    total_items = WorkOrderItems.objects.filter(workorders=work_order).count()
    scanned_items = Scans.objects.filter(
        workOrderItems__workorders=work_order
    ).count()
    
    if scanned_items < total_items:
        messages.error(request, 'Debes escanear todas las piezas antes de cerrar')
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    # Obtener todos los items y sus escaneos para mostrar resumen
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order).select_related('items')
    all_scans = []
    total_scanned = 0
    
    for item in work_order_items:
        scans = Scans.objects.filter(
            workOrderItems=item
        ).select_related('items').order_by('-timestamp')
        all_scans.extend(scans)
        if scans.exists():
            total_scanned += 1
    
    # Preparar contexto para la plantilla de confirmación
    context = {
        'work_order': work_order,
        'all_scans': all_scans,
        'work_order_items': work_order_items,
        'total_items': total_items,
        'total_scanned': total_scanned,
        'completion_percentage': (total_scanned / total_items * 100) if total_items > 0 else 0
    }
    
    return render(request, 'system/closeOrder.html', context)

def confirm_close_order_view(request, order_id):
    """
    Ejecuta el cierre definitivo de una orden de trabajo.
    Realiza validaciones finales y actualiza el estado de la orden.
    
    Args:
        request: HttpRequest de Django
        order_id: ID de la orden de trabajo a cerrar
        
    Returns:
        HttpResponse: Redirección según el resultado de la operación
    """
    # Solo permitir método POST para operaciones de escritura
    if request.method != 'POST':
        return redirect('close_order', order_id=order_id)
    
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Verificación final: validar que todos los items están completos
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order)
    total_expected_items = work_order_items.count()
    
    # Contar escaneos completados
    total_scanned_items = 0
    for wo_item in work_order_items:
        item_scans = Scans.objects.filter(
            workOrderItems=wo_item,
            items=wo_item.items
        ).count()
        
        # Cada item serializado debe tener al menos 1 escaneo
        if item_scans > 0:
            total_scanned_items += 1
    
    # Verificar completitud total antes de cerrar
    if total_scanned_items < total_expected_items:
        messages.error(
            request, 
            f"Error: No se puede cerrar la orden. Faltan {total_expected_items - total_scanned_items} items por completar"
        )
        return redirect('close_order', order_id=order_id)
    
    # Verificar que está en la etapa final
    if work_order.current_stage != 'empaque':
        messages.error(request, "Error: La orden debe estar en la etapa de empaque para cerrarse")
        return redirect('close_order', order_id=order_id)
    
    try:
        # Ejecutar cierre de la orden
        work_order.status = False  # Marcar como cerrada
        work_order.closed_date = timezone.now()  # Registrar fecha de cierre
        work_order.closedBy = request.user  # Registrar quien cerró la orden
        work_order.save()
        
        # Limpiar datos de sesión relacionados con esta orden (si existen)
        session_key = f'wo_{order_id}'
        if session_key in request.session:
            del request.session[session_key]
        
        messages.success(
            request, 
            f"Orden WO-{work_order.number} cerrada exitosamente por {request.user.username}"
        )
        return redirect('activeWorkOrders')
        
    except Exception as e:
        # Manejar errores inesperados durante el cierre
        messages.error(
            request, 
            f"Error al cerrar la orden: {str(e)}. Contacte al administrador del sistema."
        )
        return redirect('close_order', order_id=order_id)