from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from .models import Items,  Errors, WorkOrderItems, WorkOrders, Scans, Cells
from django.utils import timezone
from django.urls import reverse_lazy
from django.db.models import Sum, Q
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
import datetime, json

# Active work orders
class activeOrdersListView (ListView):
    model = WorkOrderItems
    template_name = 'system/activeWorkOrders.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return WorkOrderItems.objects.filter(workorders__status=True).select_related('workorders', 'items').order_by("-workorders__pub_date")
    
    # Gets all cells
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        return context

# Active work orders details
@login_required
def receipts_view(request, order_id):
    # Get work order by ID and ensure it's active
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Get all available cells for the work order 
    available_cells = work_order.cells.all()
    
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order).prefetch_related(
        'items', 'scans'
    )
    
    # Get scans for each item and calculate progress
    for item in work_order_items:
        total_scanned = item.scans.aggregate(
            total=Sum('scanned_items')
        )['total'] or 0
        
        item.total_scanned = total_scanned
        item.is_complete = total_scanned >= item.quantity
        item.progress_percentage = min((total_scanned / item.quantity) * 100, 100) if item.quantity > 0 else 0
        
        # Ahora available_cells ya está definida
        item.available_cells = available_cells
    
    # Verify if all items are complete
    all_items_complete = all(item.is_complete for item in work_order_items)
    
    # Get latest scans for the work order
    recent_scans = Scans.objects.filter(
        workOrderItems__workorders=work_order
    ).select_related('items').order_by('-timestamp')[:50]
    
    # Get errors related to the work order
    errors = Errors.objects.filter(
        workorders=work_order
    ).order_by('-pub_date')[:5]
    
    # This allows us to render the template with all necessary data
    context = {
        'work_order': work_order,
        'work_order_items': work_order_items,
        'available_cells': available_cells,
        'recent_scans': recent_scans,
        'all_items_complete': all_items_complete,
        'errors': errors,
    }
    
    return render(request, 'system/activeWorkOrdersDetail.html', context)

# Scans
@login_required
def add_scan_view(request, order_id):
    if request.method == 'POST':
        work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
        
        cell_name = request.POST.get('cell_name')
        part_number = request.POST.get('part_number')
        quantity = int(request.POST.get('quantity', 1))
        
        try:
            # Get the cell by name
            cell = get_object_or_404(Cells, work_cell=cell_name)
            
            # Get the item by part number
            item = get_object_or_404(Items, part_number=part_number)
            
            # Verify if the cell is assigned to this work order
            if not work_order.cells.filter(id=cell.id).exists():
                # Create error
                Errors.objects.create(
                    workorders=work_order,
                    items=item,
                    error='wrong_cell',
                    description=f'La celda {cell_name} no está asignada a esta orden de trabajo'
                )
                messages.error(request, f'La celda {cell_name} no está asignada a esta orden de trabajo.')
                return redirect('activeWorkOrdersDetail', order_id=order_id)
            
            # Verify if the part number belongs to this work order
            work_order_item = WorkOrderItems.objects.filter(
                workorders=work_order,
                items=item
            ).first()
            
            if not work_order_item:
                # Create error
                Errors.objects.create(
                    workorders=work_order,
                    items=item,
                    error='wrong_work_order',
                    description=f'La pieza {part_number} no pertenece a la orden WO-{work_order.number}'
                )
                messages.error(request, f'La pieza {part_number} no pertenece a esta orden de trabajo.')
                return redirect('activeWorkOrdersDetail', order_id=order_id)
              # Verify if the part is configured to be processed in this cell
            if not item.cells.filter(id=cell.id).exists():
                # Create error
                Errors.objects.create(
                    workorders=work_order,
                    items=item,
                    error='wrong_cell',
                    description=f'La parte {part_number} no está configurada para ser procesada en la celda {cell_name}'
                )
                messages.error(request, f'La parte {part_number} no está configurada para ser procesada en la celda {cell_name}.')
                return redirect('activeWorkOrdersDetail', order_id=order_id)
            
            # Verify that the quantity doesn't exceed the required amount
            current_scanned = work_order_item.scans.aggregate(
                total=Sum('scanned_items')
            )['total'] or 0
            
            if current_scanned + quantity > work_order_item.quantity:
                # Create error
                Errors.objects.create(
                    workorders=work_order,
                    items=item,
                    error='exceeded_limit',
                    description=f'Se excedería el límite de {work_order_item.quantity} piezas para {part_number}'
                )
                messages.error(request, f'Se excedería el límite de {work_order_item.quantity} piezas para {part_number}.')
                return redirect('activeWorkOrdersDetail', order_id=order_id)
            
            # Create the scan
            Scans.objects.create(
                workOrderItems=work_order_item,
                items=item,
                scanned_items=quantity
            )
            
            messages.success(request, f'Escaneo registrado: {quantity} piezas de {part_number}')
            
        except Cells.DoesNotExist:
            messages.error(request, f'La celda {cell_name} no existe.')
        except Items.DoesNotExist:
            messages.error(request, f'El número de parte {part_number} no existe.')
        except Exception as e:
            messages.error(request, f'Error al procesar el escaneo: {str(e)}')
    
    return redirect('activeWorkOrdersDetail', order_id=order_id)

#Close the work order
@login_required
def close_order_view(request, order_id):
    work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
    
    # Verificar que todos los items estén completos
    work_order_items = WorkOrderItems.objects.filter(workorders=work_order)
    
    all_complete = True
    for item in work_order_items:
        total_scanned = item.scans.aggregate(
            total=Sum('scanned_items')
        )['total'] or 0
        
        if total_scanned < item.quantity:
            all_complete = False
            break
    
    if not all_complete:
        messages.error(request, 'No se puede cerrar la orden. Faltan piezas por escanear.')
        return redirect('activeWorkOrdersDetail', order_id=order_id)
    
    context = {
        'work_order': work_order,
        'work_order_items': work_order_items,
    }
    
    return render(request, 'system/closeOrder.html', context)

# Confirm close order view
@login_required
def confirm_close_order_view(request, order_id):
    if request.method == 'POST':
        work_order = get_object_or_404(WorkOrders, id=order_id, status=True)
        
        # Cerrar la orden
        work_order.status = False
        work_order.closed_date = timezone.now()
        work_order.closedBy = request.user
        work_order.save()
        
        messages.success(request, f'Orden WO-{work_order.number} cerrada exitosamente.')
        return redirect('closedOrders')
    
    return redirect('activeWorkOrdersDetail', order_id=order_id)

# Register a new work order
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
    
# Create a new part number
class registerPartNumber(CreateView):
    model = Items
    template_name = 'system/registerPartNumber.html'
    fields = ['part_number', 'cells']
    success_url = '/ordenes-abiertas'

    def form_valid(self, form):
        form.instance.pub_date = timezone.now()
        return super().form_valid(form)
    
    # Gets all cells
    def get_context_data(self, **kwargs):
        contexts = super().get_context_data(**kwargs)
        contexts['cells'] = Cells.objects.all()
        return contexts
    
# Closed work orders 
class closedOrdersListView(ListView):
    model = WorkOrderItems
    template_name = 'system/ClosedOrders.html'
    context_object_name = 'orders'

    def get_queryset(self):
        today = timezone.now()
        last_month = today - datetime.timedelta(days=30)
        return WorkOrderItems.objects.filter(workorders__status=False).select_related('workorders', 'items').order_by("-workorders__pub_date")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        return context
    
# Closed work orders details
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
    
# See all part numbers
class partNumbersListView (ListView):
    model = Items
    template_name = "system/partNumbers.html"
    context_object_name = 'pieces'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cells'] = Cells.objects.all()
        return context