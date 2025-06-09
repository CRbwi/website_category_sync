from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ProductSetNoTrackingWizard(models.TransientModel):
    _name = 'product.set.no.tracking.wizard'
    _description = 'Wizard to Set No Tracking on All Products'

    confirmation_text = fields.Char(
        string="Confirmación",
        compute='_compute_confirmation_text',
        readonly=True
    )
    
    # Campos para diagnóstico
    product_id_tracked = fields.Many2one(
        'product.template',
        string="Producto con 'Rastrear inventario' MARCADO",
        help="Selecciona un producto que tenga el checkbox 'Rastrear inventario' marcado"
    )
    
    product_id_not_tracked = fields.Many2one(
        'product.template', 
        string="Producto con 'Rastrear inventario' DESMARCADO",
        help="Selecciona un producto que tenga el checkbox 'Rastrear inventario' desmarcado y que se vea correctamente"
    )

    @api.depends('confirmation_text') # Dummy depends to trigger compute
    def _compute_confirmation_text(self):
        product_template_count_to_update = self.env['product.template'].search_count([
            ('tracking', '!=', 'none')
        ])
        self.confirmation_text = _(
            "Esta acción establecerá la opción de seguimiento de inventario a 'Sin seguimiento' "
            "para TODOS los %s productos en el sistema. NOTA: Primero ejecuta 'Descubrir Valores de Type' "
            "para identificar los valores correctos del campo 'type' en tu versión de Odoo. "
            "¿Estás seguro de que deseas continuar?"
        ) % product_template_count_to_update

    def action_confirm_set_no_tracking(self):
        _logger.info("Iniciando proceso para establecer 'Sin seguimiento' en todos los productos base aplicables.")

        # Log para depuración
        all_products_count = self.env['product.template'].search_count([])
        _logger.info(f"Total de plantillas de producto en el sistema: {all_products_count}")
        
        products_to_change_count = self.env['product.template'].search_count([
            ('tracking', '!=', 'none')
        ])
        _logger.info(f"Plantillas de producto que necesitan corrección: {products_to_change_count}")

        # Logs adicionales para tipos de seguimiento específicos
        products_with_lot_tracking = self.env['product.template'].search_count([('tracking', '=', 'lot')])
        _logger.info(f"Plantillas de producto con tracking = 'lot': {products_with_lot_tracking}")
        products_with_serial_tracking = self.env['product.template'].search_count([('tracking', '=', 'serial')])
        _logger.info(f"Plantillas de producto con tracking = 'serial': {products_with_serial_tracking}")

        product_templates_to_process = self.env['product.template'].search([
            ('tracking', '!=', 'none')
        ])
        
        if not product_templates_to_process:
            _logger.info("No se encontraron plantillas de producto que requieran actualización a 'Sin seguimiento'.")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Información'),
                    'message': _('No se encontraron productos que necesiten ser cambiados a "Sin seguimiento".'),
                    'sticky': False,
                    'type': 'info',
                }
            }

        ids_to_process = product_templates_to_process.ids
        _logger.info(f"Se intentarán actualizar {len(ids_to_process)} plantillas de producto. IDs: {ids_to_process}")

        _logger.info("Estado ANTES de la escritura:")
        for prod_template in product_templates_to_process:
            _logger.info(f"  ID: {prod_template.id}, Nombre: {prod_template.name}")
            _logger.info(f"    Tracking ANTES: {prod_template.tracking}")
            _logger.info(f"    type ANTES: {prod_template.type}")
            _logger.info(f"    is_storable ANTES: {prod_template.is_storable}")

        updated_count = 0
        not_updated_count = 0
        
        try:
            # Primero solo actualizar tracking, luego descubriremos los valores correctos para type
            values_to_update = {
                'tracking': 'none'
            }
            product_templates_to_process.write(values_to_update)
            _logger.info(f"Operación de escritura {values_to_update} ejecutada para IDs: {ids_to_process}.")

            _logger.info("Estado DESPUÉS de la escritura (re-leyendo los mismos productos para verificación):")
            
            self.env.invalidate_all() # Invalidar toda la caché del entorno.

            re_fetched_products = self.env['product.template'].search([('id', 'in', ids_to_process)])

            if not re_fetched_products and ids_to_process: # Check if ids_to_process was not empty
                 _logger.warning(f"No se pudieron recuperar los productos después de la actualización para los IDs: {ids_to_process}. Esto es inesperado si se procesaron productos.")

            # Crear un diccionario para facilitar la búsqueda de productos re-leídos
            re_fetched_map = {p.id: p for p in re_fetched_products}

            for original_prod_id in ids_to_process:
                current_prod_state = re_fetched_map.get(original_prod_id)
                original_prod_template = next((p for p in product_templates_to_process if p.id == original_prod_id), None) # Para nombre y estado anterior
                
                if current_prod_state:
                    _logger.info(f"  ID: {current_prod_state.id}, Nombre: {current_prod_state.name}")
                    _logger.info(f"    Tracking DESPUÉS: {current_prod_state.tracking}")
                    _logger.info(f"    type DESPUÉS: {current_prod_state.type}")
                    _logger.info(f"    is_storable DESPUÉS: {current_prod_state.is_storable}")
                    
                    if current_prod_state.tracking == 'none':
                        updated_count += 1
                    else:
                        not_updated_count += 1
                        _logger.warning(f"  FALLO AL ACTUALIZAR: ID: {current_prod_state.id}, Nombre: {current_prod_state.name}")
                        _logger.warning(f"    Tracking: {current_prod_state.tracking} (esperado: 'none')")
                else:
                    # Esto no debería suceder si el producto no fue eliminado
                    original_name = original_prod_template.name if original_prod_template else "Nombre Desconocido"
                    original_tracking = original_prod_template.tracking if original_prod_template else "Tracking Desconocido"
                    _logger.warning(f"  ID: {original_prod_id}, Nombre: {original_name} no encontrado después de la actualización. Tracking ANTES: {original_tracking}")
                    not_updated_count += 1


            if not_updated_count > 0:
                 _logger.error(f"Resumen: {not_updated_count} de {len(ids_to_process)} productos NO se actualizaron correctamente a 'tracking: none'.")
            elif updated_count > 0 : # Solo si hubo algo que procesar
                 _logger.info(f"Resumen: Todos los {updated_count} productos procesados se actualizaron correctamente a 'tracking: none'.")
            # Si updated_count es 0 y not_updated_count es 0, significa que ids_to_process estaba vacío, lo cual es manejado al inicio.

        except Exception as e:
            _logger.error(f"Error al actualizar el seguimiento de productos: {e}. IDs que se intentaron procesar: {ids_to_process}", exc_info=True)
            raise UserError(_("Ocurrió un error al intentar actualizar las plantillas de producto: %s") % str(e))

        # Mensaje de notificación final
        if not ids_to_process: # Debería ser manejado por el chequeo inicial, pero por si acaso.
            final_message = _('No había productos para procesar.')
            final_type = 'info'
        elif not_updated_count > 0:
            final_message = _('Se procesaron %s plantillas de producto. %s no pudieron ser actualizadas a "Sin seguimiento". Revisa los logs.') % (len(ids_to_process), not_updated_count)
            final_type = 'warning'
        else: # Todos actualizados exitosamente
            final_message = _('Operación completada. %s plantillas de producto fueron actualizadas exitosamente a "Sin seguimiento".') % updated_count
            final_type = 'success'
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Resultado de la Operación'),
                'message': final_message,
                'sticky': True, 
                'type': final_type,
            }
        }

    def action_discover_type_values(self):
        """Descubre los valores válidos para el campo type"""
        _logger.info("=== DESCUBRIMIENTO DE VALORES VÁLIDOS PARA 'type' ===")
        
        # Obtener información del campo type
        product_template_model = self.env['product.template']
        type_field = product_template_model._fields.get('type')
        
        if type_field:
            _logger.info(f"Campo 'type' encontrado: {type(type_field).__name__}")
            if hasattr(type_field, 'selection'):
                _logger.info(f"Valores de selección válidos para 'type': {type_field.selection}")
                # También intentar obtener los valores dinámicamente
                if callable(type_field.selection):
                    try:
                        dynamic_selection = type_field.selection(product_template_model, 'type')
                        _logger.info(f"Valores de selección dinámicos: {dynamic_selection}")
                    except Exception as e:
                        _logger.warning(f"No se pudieron obtener valores dinámicos: {e}")
            else:
                _logger.info("El campo 'type' no es un campo de selección")
        else:
            _logger.warning("Campo 'type' no encontrado en product.template")
        
        # Obtener algunos productos existentes y ver sus valores de 'type'
        existing_products = self.env['product.template'].search([], limit=10)
        _logger.info("=== VALORES DE 'type' EN PRODUCTOS EXISTENTES ===")
        type_values_found = set()
        for product in existing_products:
            _logger.info(f"Producto '{product.name}': type='{product.type}', is_storable={product.is_storable}")
            type_values_found.add(product.type)
        
        _logger.info(f"Valores únicos de 'type' encontrados: {list(type_values_found)}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Descubrimiento Completado'),
                'message': _('Información sobre el campo "type" registrada en los logs. Revisa los logs del servidor para ver los valores válidos.'),
                'sticky': True,
                'type': 'info',
            }
        }

    def action_diagnose_products(self):
        """Compara dos productos para encontrar diferencias en sus campos"""
        if not self.product_id_tracked or not self.product_id_not_tracked:
            raise UserError(_("Debes seleccionar ambos productos para hacer la comparación."))
        
        if self.product_id_tracked.id == self.product_id_not_tracked.id:
            raise UserError(_("Debes seleccionar dos productos diferentes."))
        
        _logger.info(f"=== DIAGNÓSTICO DE PRODUCTOS ===")
        _logger.info(f"Producto MARCADO: ID {self.product_id_tracked.id} - {self.product_id_tracked.name}")
        _logger.info(f"Producto DESMARCADO: ID {self.product_id_not_tracked.id} - {self.product_id_not_tracked.name}")
        _logger.info("=" * 50)
        
        # Campos sospechosos de controlar el comportamiento del UI de tracking
        suspect_fields = [
            'tracking', 'type', 'product_type', 'is_product_variant', 
            'sale_ok', 'purchase_ok', 'is_storable',
            'has_configurable_attributes', 'attribute_line_ids',
            'product_variant_count', 'product_variant_ids'
        ]
        
        _logger.info("=== VERIFICACIÓN DE CAMPOS SOSPECHOSOS ===")
        differences_found = False
        
        for field_name in suspect_fields:
            try:
                if hasattr(self.product_id_tracked, field_name):
                    val_tracked = getattr(self.product_id_tracked, field_name)
                    val_not_tracked = getattr(self.product_id_not_tracked, field_name)
                    
                    # Comparar valores
                    if hasattr(val_tracked, 'ids') and hasattr(val_not_tracked, 'ids'):
                        # Para campos relacionales
                        if set(val_tracked.ids) != set(val_not_tracked.ids):
                            _logger.info(f"🔍 DIFERENCIA EN {field_name}:")
                            _logger.info(f"  MARCADO: {val_tracked} (IDs: {val_tracked.ids})")
                            _logger.info(f"  DESMARCADO: {val_not_tracked} (IDs: {val_not_tracked.ids})")
                            _logger.info("-" * 30)
                            differences_found = True
                    elif val_tracked != val_not_tracked:
                        _logger.info(f"🔍 DIFERENCIA EN {field_name}:")
                        _logger.info(f"  MARCADO: {val_tracked} (Tipo: {type(val_tracked).__name__})")
                        _logger.info(f"  DESMARCADO: {val_not_tracked} (Tipo: {type(val_not_tracked).__name__})")
                        _logger.info("-" * 30)
                        differences_found = True
                    else:
                        _logger.info(f"✓ Campo {field_name} es igual en ambos productos: {val_tracked}")
                else:
                    _logger.warning(f"⚠️ Campo {field_name} no existe en product.template")
            except Exception as e:
                _logger.warning(f"Error al acceder al campo {field_name}: {e}")
        
        # Búsqueda completa de diferencias en TODOS los campos
        _logger.info("=== BÚSQUEDA COMPLETA DE DIFERENCIAS ===")
        all_fields = self.product_id_tracked._fields.keys()
        other_differences = 0
        
        for field_name in all_fields:
            if field_name in suspect_fields:
                continue  # Ya lo verificamos arriba
                
            try:
                val_tracked = getattr(self.product_id_tracked, field_name)
                val_not_tracked = getattr(self.product_id_not_tracked, field_name)
                
                # Comparar valores
                if hasattr(val_tracked, 'ids') and hasattr(val_not_tracked, 'ids'):
                    if set(val_tracked.ids) != set(val_not_tracked.ids):
                        _logger.info(f"📋 Diferencia en {field_name}: MARCADO={val_tracked.ids}, DESMARCADO={val_not_tracked.ids}")
                        other_differences += 1
                elif val_tracked != val_not_tracked:
                    _logger.info(f"📋 Diferencia en {field_name}: MARCADO={val_tracked}, DESMARCADO={val_not_tracked}")
                    other_differences += 1
            except Exception as e:
                _logger.warning(f"Error al acceder al campo {field_name}: {e}")
        
        _logger.info(f"Total de diferencias encontradas en campos no sospechosos: {other_differences}")
        
        # Verificación específica del campo tracking
        _logger.info("=== VERIFICACIÓN ESPECÍFICA ===")
        _logger.info(f"Campo 'tracking' - MARCADO: {self.product_id_tracked.tracking}")
        _logger.info(f"Campo 'tracking' - DESMARCADO: {self.product_id_not_tracked.tracking}")
        
        # Verificación de campos computados relacionados
        computed_fields = ['is_storable', 'type']
        _logger.info("=== CAMPOS COMPUTADOS RELACIONADOS ===")
        for field in computed_fields:
            try:
                if hasattr(self.product_id_tracked, field):
                    val_tracked = getattr(self.product_id_tracked, field)
                    val_not_tracked = getattr(self.product_id_not_tracked, field)
                    _logger.info(f"Campo '{field}' - MARCADO: {val_tracked}, DESMARCADO: {val_not_tracked}")
            except Exception as e:
                _logger.warning(f"Error al verificar campo computado {field}: {e}")
        
        if not differences_found and other_differences == 0:
            _logger.warning("¡No se encontraron diferencias! Esto es inesperado.")
            message = _("No se encontraron diferencias entre los productos seleccionados. Esto podría indicar que el problema no está en los campos del modelo product.template. Revisa los logs para más detalles.")
            msg_type = 'warning'
        else:
            _logger.info("=== DIAGNÓSTICO COMPLETADO ===")
            total_diffs = (1 if differences_found else 0) + other_differences
            message = _("Diagnóstico completado. Se encontraron %s diferencias. Revisa los logs del servidor para ver todas las diferencias encontradas entre los productos.") % total_diffs
            msg_type = 'success'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Diagnóstico de Productos'),
                'message': message,
                'sticky': True,
                'type': msg_type,
            }
        }

    def action_fix_tracking_comprehensive(self):
        """Método alternativo que intenta arreglar el tracking sin tocar el campo type"""
        _logger.info("Iniciando reparación comprensiva del seguimiento de productos...")
        
        # Buscar todos los productos que no tienen tracking='none'
        products_to_fix = self.env['product.template'].search([('tracking', '!=', 'none')])
        _logger.info(f"Total de productos que necesitan corrección: {len(products_to_fix)}")
        
        updated_count = 0
        for product in products_to_fix:
            # Registrar estado actual
            _logger.info(f"Producto {product.name} - Estado actual:")
            _logger.info(f"  tracking: {product.tracking}")
            _logger.info(f"  type: {product.type}")
            _logger.info(f"  is_storable: {product.is_storable}")
            
            try:
                product.write({'tracking': 'none'})
                updated_count += 1
                
                # Verificar después de la actualización
                product.invalidate_recordset(['tracking'])
                _logger.info(f"  Actualizado producto {product.name} (ID: {product.id}) - tracking establecido a 'none'")
                _logger.info(f"  Estado después: tracking={product.tracking}, type={product.type}, is_storable={product.is_storable}")
            except Exception as e:
                _logger.error(f"Error al actualizar producto {product.name} (ID: {product.id}): {e}")
        
        _logger.info(f"Reparación comprensiva completada. {updated_count} productos actualizados.")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reparación Comprensiva'),
                'message': _('Reparación completada. %s productos fueron procesados. Ejecuta "Descubrir Valores de Type" para identificar cómo hacer visible el checkbox de tracking.') % updated_count,
                'sticky': True,
                'type': 'success',
            }
        }

    def action_investigate_is_storable(self):
        """Investiga qué controla el campo is_storable"""
        _logger.info("=== INVESTIGACIÓN DEL CAMPO is_storable ===")
        
        # Obtener información del campo is_storable
        product_template_model = self.env['product.template']
        is_storable_field = product_template_model._fields.get('is_storable')
        
        if is_storable_field:
            _logger.info(f"Campo 'is_storable' encontrado: {type(is_storable_field).__name__}")
            if hasattr(is_storable_field, 'compute'):
                _logger.info(f"is_storable es un campo computado. Método de cómputo: {is_storable_field.compute}")
            if hasattr(is_storable_field, 'depends'):
                _logger.info(f"is_storable depende de: {is_storable_field.depends}")
        else:
            _logger.warning("Campo 'is_storable' no encontrado en product.template")
        
        # Analizar productos con diferentes valores de is_storable
        _logger.info("=== ANÁLISIS DE PRODUCTOS POR is_storable ===")
        
        storable_products = self.env['product.template'].search([('is_storable', '=', True)], limit=10)
        non_storable_products = self.env['product.template'].search([('is_storable', '=', False)], limit=10)
        
        _logger.info("--- PRODUCTOS CON is_storable = True ---")
        for product in storable_products:
            _logger.info(f"ID: {product.id}, Nombre: {product.name}")
            _logger.info(f"  type: {product.type}")
            _logger.info(f"  tracking: {product.tracking}")
            _logger.info(f"  is_storable: {product.is_storable}")
        
        _logger.info("--- PRODUCTOS CON is_storable = False ---")
        for product in non_storable_products:
            _logger.info(f"ID: {product.id}, Nombre: {product.name}")
            _logger.info(f"  type: {product.type}")
            _logger.info(f"  tracking: {product.tracking}")
            _logger.info(f"  is_storable: {product.is_storable}")
        
        # Analizar relación entre type e is_storable
        _logger.info("=== RELACIÓN ENTRE type E is_storable ===")
        all_products = self.env['product.template'].search([])
        type_storable_map = {}
        
        for product in all_products:
            type_val = product.type
            storable_val = product.is_storable
            
            if type_val not in type_storable_map:
                type_storable_map[type_val] = {'storable': 0, 'non_storable': 0, 'examples': []}
            
            if storable_val:
                type_storable_map[type_val]['storable'] += 1
            else:
                type_storable_map[type_val]['non_storable'] += 1
            
            # Guardar algunos ejemplos
            if len(type_storable_map[type_val]['examples']) < 3:
                type_storable_map[type_val]['examples'].append({
                    'id': product.id,
                    'name': product.name,
                    'is_storable': storable_val
                })
        
        for type_val, data in type_storable_map.items():
            _logger.info(f"Type '{type_val}':")
            _logger.info(f"  Productos con is_storable=True: {data['storable']}")
            _logger.info(f"  Productos con is_storable=False: {data['non_storable']}")
            _logger.info(f"  Ejemplos: {data['examples']}")
        
        # Buscar el patrón en las diferencias
        _logger.info("=== BÚSQUEDA DE PATRONES ===")
        
        # Si todos los productos tienen el mismo type pero diferente is_storable, investigar qué más afecta is_storable
        if len(type_storable_map) == 1:
            _logger.info("Todos los productos tienen el mismo 'type', pero is_storable varía.")
            _logger.info("Esto significa que otro campo o lógica controla is_storable.")
            
            # Tomar un producto con is_storable=True y otro con is_storable=False
            storable_example = next((p for p in storable_products), None)
            non_storable_example = next((p for p in non_storable_products), None)
            
            if storable_example and non_storable_example:
                _logger.info("=== COMPARACIÓN DETALLADA ===")
                self._compare_products_for_is_storable(storable_example, non_storable_example)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Investigación Completada'),
                'message': _('Investigación del campo is_storable completada. Revisa los logs del servidor para entender qué controla la visibilidad del checkbox de tracking.'),
                'sticky': True,
                'type': 'info',
            }
        }

    def _compare_products_for_is_storable(self, storable_product, non_storable_product):
        """Compara dos productos para encontrar qué hace que is_storable sea diferente"""
        _logger.info(f"Comparando:")
        _logger.info(f"  STORABLE: {storable_product.name} (ID: {storable_product.id})")
        _logger.info(f"  NON-STORABLE: {non_storable_product.name} (ID: {non_storable_product.id})")
        
        # Campos que podrían afectar is_storable
        fields_to_check = [
            'type', 'categ_id', 'sale_ok', 'purchase_ok', 'active',
            'default_code', 'barcode', 'company_id', 'uom_id', 'uom_po_id',
            'product_variant_count', 'attribute_line_ids', 'product_variant_ids',
            'list_price', 'standard_price', 'weight', 'volume',
            'tracking', 'description', 'description_purchase', 'description_sale'
        ]
        
        differences = []
        for field_name in fields_to_check:
            try:
                if hasattr(storable_product, field_name):
                    val1 = getattr(storable_product, field_name)
                    val2 = getattr(non_storable_product, field_name)
                    
                    # Comparar valores
                    if hasattr(val1, 'ids') and hasattr(val2, 'ids'):
                        if set(val1.ids) != set(val2.ids):
                            differences.append(f"{field_name}: STORABLE={val1} vs NON-STORABLE={val2}")
                    elif val1 != val2:
                        differences.append(f"{field_name}: STORABLE={val1} vs NON-STORABLE={val2}")
            except Exception as e:
                _logger.warning(f"Error comparando campo {field_name}: {e}")
        
        _logger.info("DIFERENCIAS ENCONTRADAS:")
        for diff in differences:
            _logger.info(f"  🔍 {diff}")
        
        if not differences:
            _logger.warning("No se encontraron diferencias en los campos básicos. El campo is_storable podría ser controlado por lógica más compleja.")

    def action_make_products_storable(self):
        """Intenta hacer que todos los productos sean almacenables basándose en el descubrimiento"""
        _logger.info("=== HACIENDO PRODUCTOS ALMACENABLES ===")
        
        # Primero ejecutar descubrimiento para entender el estado actual
        self.action_investigate_is_storable()
        
        # Buscar productos que no son storables
        non_storable_products = self.env['product.template'].search([('is_storable', '=', False)])
        _logger.info(f"Productos no almacenables encontrados: {len(non_storable_products)}")
        
        if not non_storable_products:
            _logger.info("Todos los productos ya son almacenables (is_storable=True)")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Información'),
                    'message': _('Todos los productos ya son almacenables. No se requiere ninguna acción.'),
                    'sticky': False,
                    'type': 'info',
                }
            }
        
        # Obtener un producto que SÍ sea storable para usar como referencia
        storable_products = self.env['product.template'].search([('is_storable', '=', True)], limit=1)
        
        if not storable_products:
            _logger.warning("No se encontraron productos de referencia con is_storable=True")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('No se encontraron productos de referencia con is_storable=True. No se puede determinar la configuración correcta.'),
                    'sticky': True,
                    'type': 'warning',
                }
            }
        
        reference_product = storable_products[0]
        _logger.info(f"Usando como referencia: {reference_product.name} (ID: {reference_product.id})")
        _logger.info(f"  type: {reference_product.type}")
        _logger.info(f"  tracking: {reference_product.tracking}")
        _logger.info(f"  is_storable: {reference_product.is_storable}")
        
        # Intentar actualizar los productos no almacenables con la misma configuración que el de referencia
        updated_count = 0
        failed_count = 0
        
        for product in non_storable_products:
            _logger.info(f"Actualizando producto: {product.name} (ID: {product.id})")
            _logger.info(f"  Estado ANTES: type={product.type}, is_storable={product.is_storable}")
            
            try:
                # Intentar con la misma configuración que el producto de referencia
                product.write({
                    'type': reference_product.type,
                    'tracking': 'none'  # Establecer tracking en none también
                })
                
                # Invalidar caché y volver a leer
                product.invalidate_recordset(['type', 'is_storable', 'tracking'])
                
                _logger.info(f"  Estado DESPUÉS: type={product.type}, is_storable={product.is_storable}")
                
                if product.is_storable:
                    updated_count += 1
                    _logger.info(f"  ✅ ÉXITO: Producto ahora es almacenable")
                else:
                    failed_count += 1
                    _logger.warning(f"  ❌ FALLO: Producto sigue sin ser almacenable")
                    
            except Exception as e:
                failed_count += 1
                _logger.error(f"  ❌ ERROR al actualizar: {e}")
        
        _logger.info(f"=== RESUMEN ===")
        _logger.info(f"Productos actualizados exitosamente: {updated_count}")
        _logger.info(f"Productos que fallaron: {failed_count}")
        
        if updated_count > 0:
            msg_type = 'success'
            message = _('Se actualizaron %s productos para ser almacenables. %s productos fallaron. Revisa los logs para detalles.') % (updated_count, failed_count)
        else:
            msg_type = 'warning'
            message = _('No se pudo hacer almacenable ningún producto. Revisa los logs para entender qué controla el campo is_storable.')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Resultado'),
                'message': message,
                'sticky': True,
                'type': msg_type,
            }
        }

    def action_deep_is_storable_investigation(self):
        """Investigación profunda del campo is_storable para entender su lógica de cómputo"""
        _logger.info("=== INVESTIGACIÓN PROFUNDA DEL CAMPO is_storable ===")
        
        # 1. Analizar el campo is_storable en detalle
        product_template_model = self.env['product.template']
        is_storable_field = product_template_model._fields.get('is_storable')
        
        if is_storable_field:
            _logger.info(f"Tipo de campo 'is_storable': {type(is_storable_field).__name__}")
            
            # Si es un campo computado, intentar obtener información sobre el método
            if hasattr(is_storable_field, 'compute'):
                compute_method = is_storable_field.compute
                _logger.info(f"Método de cómputo: {compute_method}")
                
                # Intentar acceder al código del método si es posible
                if hasattr(product_template_model, compute_method):
                    method_obj = getattr(product_template_model, compute_method)
                    _logger.info(f"Método encontrado: {method_obj}")
                    
                    # Intentar obtener el código fuente del método
                    try:
                        import inspect
                        source_code = inspect.getsource(method_obj)
                        _logger.info(f"CÓDIGO FUENTE DEL MÉTODO {compute_method}:")
                        _logger.info(source_code)
                    except Exception as e:
                        _logger.warning(f"No se pudo obtener código fuente: {e}")
            
            # Verificar dependencias
            if hasattr(is_storable_field, 'depends'):
                depends = is_storable_field.depends
                _logger.info(f"is_storable depende de: {depends}")
            
            # Verificar si es readonly, store, etc.
            _logger.info(f"Campo readonly: {getattr(is_storable_field, 'readonly', False)}")
            _logger.info(f"Campo store: {getattr(is_storable_field, 'store', False)}")
            _logger.info(f"Campo compute_sudo: {getattr(is_storable_field, 'compute_sudo', False)}")
        
        # 2. Buscar patrones en valores existentes del sistema
        _logger.info("=== ANÁLISIS DE PATRONES EN EL SISTEMA ===")
        
        # Obtener todos los productos únicos por combinaciones de campos relacionados
        all_products = self.env['product.template'].search([])
        _logger.info(f"Total de productos en el sistema: {len(all_products)}")
        
        # Analizar todas las combinaciones posibles
        combinations = {}
        for product in all_products:
            # Crear una clave con los campos que podrían afectar is_storable
            key_fields = [
                product.type,
                product.categ_id.id if product.categ_id else None,
                product.sale_ok,
                product.purchase_ok,
                product.active,
                len(product.attribute_line_ids),
                product.product_variant_count,
                bool(product.default_code),
                bool(product.barcode)
            ]
            key = tuple(key_fields)
            
            if key not in combinations:
                combinations[key] = {
                    'storable_true': 0,
                    'storable_false': 0,
                    'examples_true': [],
                    'examples_false': []
                }
            
            if product.is_storable:
                combinations[key]['storable_true'] += 1
                if len(combinations[key]['examples_true']) < 3:
                    combinations[key]['examples_true'].append({
                        'id': product.id, 
                        'name': product.name[:50]
                    })
            else:
                combinations[key]['storable_false'] += 1
                if len(combinations[key]['examples_false']) < 3:
                    combinations[key]['examples_false'].append({
                        'id': product.id, 
                        'name': product.name[:50]
                    })
        
        # Reportar combinaciones que tienen ambos valores (True y False)
        _logger.info("=== COMBINACIONES CON AMBOS VALORES is_storable ===")
        mixed_combinations = 0
        for key, data in combinations.items():
            if data['storable_true'] > 0 and data['storable_false'] > 0:
                mixed_combinations += 1
                _logger.info(f"Combinación mixta #{mixed_combinations}:")
                _logger.info(f"  Campos: type={key[0]}, categ_id={key[1]}, sale_ok={key[2]}, purchase_ok={key[3]}")
                _logger.info(f"  active={key[4]}, attrs={key[5]}, variants={key[6]}, has_code={key[7]}, has_barcode={key[8]}")
                _logger.info(f"  is_storable=True: {data['storable_true']} productos")
                _logger.info(f"  is_storable=False: {data['storable_false']} productos")
                _logger.info(f"  Ejemplos True: {data['examples_true']}")
                _logger.info(f"  Ejemplos False: {data['examples_false']}")
                _logger.info("-" * 50)
        
        if mixed_combinations == 0:
            _logger.info("No se encontraron combinaciones mixtas. Cada combinación de campos resulta consistentemente en True o False.")
        
        # 3. Buscar productos específicos para análisis detallado
        _logger.info("=== PRODUCTOS ESPECÍFICOS PARA ANÁLISIS ===")
        
        # Productos con is_storable=True
        storable_true_products = self.env['product.template'].search([('is_storable', '=', True)], limit=5)
        _logger.info("PRODUCTOS CON is_storable=True:")
        for product in storable_true_products:
            self._log_product_detailed_info(product)
        
        # Productos con is_storable=False
        storable_false_products = self.env['product.template'].search([('is_storable', '=', False)], limit=5)
        _logger.info("PRODUCTOS CON is_storable=False:")
        for product in storable_false_products:
            self._log_product_detailed_info(product)
        
        # 4. Intentar forzar recálculo del campo is_storable
        _logger.info("=== INTENTO DE RECÁLCULO DE is_storable ===")
        test_product = storable_false_products[0] if storable_false_products else None
        if test_product:
            _logger.info(f"Producto de prueba: {test_product.name} (ID: {test_product.id})")
            _logger.info(f"  is_storable ANTES del recálculo: {test_product.is_storable}")
            
            try:
                # Intentar forzar recálculo
                test_product.invalidate_recordset(['is_storable'])
                test_product._compute_is_storable() if hasattr(test_product, '_compute_is_storable') else None
                _logger.info(f"  is_storable DESPUÉS del recálculo: {test_product.is_storable}")
            except Exception as e:
                _logger.warning(f"Error al intentar recalcular is_storable: {e}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Investigación Profunda Completada'),
                'message': _('Investigación profunda del campo is_storable completada. Revisa los logs para entender la lógica exacta que controla este campo.'),
                'sticky': True,
                'type': 'info',
            }
        }

    def _log_product_detailed_info(self, product):
        """Registra información detallada de un producto"""
        _logger.info(f"  Producto: {product.name} (ID: {product.id})")
        _logger.info(f"    type: {product.type}")
        _logger.info(f"    is_storable: {product.is_storable}")
        _logger.info(f"    tracking: {product.tracking}")
        _logger.info(f"    categ_id: {product.categ_id.name if product.categ_id else 'Sin categoría'}")
        _logger.info(f"    sale_ok: {product.sale_ok}")
        _logger.info(f"    purchase_ok: {product.purchase_ok}")
        _logger.info(f"    active: {product.active}")
        _logger.info(f"    default_code: {product.default_code or 'Sin código'}")
        _logger.info(f"    barcode: {product.barcode or 'Sin código de barras'}")
        _logger.info(f"    attribute_line_ids: {len(product.attribute_line_ids)} líneas")
        _logger.info(f"    product_variant_count: {product.product_variant_count}")
        _logger.info(f"    uom_id: {product.uom_id.name if product.uom_id else 'Sin UdM'}")
        _logger.info(f"    company_id: {product.company_id.name if product.company_id else 'Sin compañía'}")

    def action_force_storable_experiment(self):
        """Experimenta con diferentes combinaciones de campos para hacer productos almacenables"""
        _logger.info("=== EXPERIMENTO PARA FORZAR is_storable=True ===")
        
        # Obtener productos que NO son almacenables
        non_storable_products = self.env['product.template'].search([('is_storable', '=', False)], limit=20)
        _logger.info(f"Productos no almacenables encontrados para prueba: {len(non_storable_products)}")
        
        if not non_storable_products:
            _logger.info("No hay productos no almacenables para probar")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Información'),
                    'message': _('Todos los productos ya son almacenables.'),
                    'sticky': False,
                    'type': 'info',
                }
            }
        
        success_count = 0
        failed_count = 0
        
        for product in non_storable_products:
            _logger.info(f"Experimentando con producto: {product.name} (ID: {product.id})")
            _logger.info(f"  Estado ANTES: type={product.type}, is_storable={product.is_storable}, tracking={product.tracking}")
            
            try:
                # Método 1: Escritura directa del campo is_storable
                # Dado que el campo es store=True y readonly=False, debería funcionar
                product.write({'is_storable': True})
                
                # Forzar invalidación de caché para asegurar actualización
                product.invalidate_recordset(['is_storable'])
                
                # Verificar el resultado
                product.refresh()
                _logger.info(f"  Estado DESPUÉS: type={product.type}, is_storable={product.is_storable}, tracking={product.tracking}")
                
                if product.is_storable:
                    success_count += 1
                    _logger.info(f"  ✅ ÉXITO: Producto ahora es almacenable")
                else:
                    _logger.warning(f"  ⚠️ Método 1 falló, intentando método 2...")
                    
                    # Método 2: Usando SQL directo para bypass completo
                    try:
                        self.env.cr.execute(
                            "UPDATE product_template SET is_storable = %s WHERE id = %s",
                            (True, product.id)
                        )
                        self.env.cr.commit()
                        
                        # Invalidar y verificar nuevamente
                        product.invalidate_recordset(['is_storable'])
                        product.refresh()
                        
                        if product.is_storable:
                            success_count += 1
                            _logger.info(f"  ✅ ÉXITO con SQL: Producto ahora es almacenable")
                        else:
                            failed_count += 1
                            _logger.error(f"  ❌ AMBOS MÉTODOS FALLARON")
                            
                    except Exception as sql_error:
                        failed_count += 1
                        _logger.error(f"  ❌ Error en SQL: {sql_error}")
                        
            except Exception as e:
                failed_count += 1
                _logger.error(f"  ❌ Error general: {e}")
        
        _logger.info(f"=== RESUMEN DEL EXPERIMENTO ===")
        _logger.info(f"Productos exitosamente convertidos: {success_count}")
        _logger.info(f"Productos que fallaron: {failed_count}")
        
        if success_count > 0:
            msg_type = 'success'
            title = _('Experimento Exitoso')
            message = _('¡Descubrimiento importante! Se logró convertir %s productos a almacenables. El método funciona. Ahora podemos aplicarlo a todos los productos.') % success_count
        else:
            msg_type = 'warning'
            title = _('Experimento Falló')
            message = _('No se pudo convertir ningún producto. El campo is_storable podría estar protegido por otra lógica.')
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'sticky': True,
                'type': msg_type,
            }
        }
        
        # Buscar un producto que SÍ sea storable para usar como template
        reference_products = self.env['product.template'].search([('is_storable', '=', True)], limit=1)
        
        if not reference_products:
            _logger.warning("No se encontró ningún producto con is_storable=True para usar como referencia")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('No se encontró ningún producto con is_storable=True para usar como referencia en el experimento.'),
                    'sticky': True,
                    'type': 'warning',
                }
            }
        
        reference = reference_products[0]
        _logger.info(f"Producto de referencia (is_storable=True): {reference.name}")
        self._log_product_detailed_info(reference)
        
        # Buscar un producto que NO sea storable para experimentar
        test_products = self.env['product.template'].search([('is_storable', '=', False)], limit=1)
        
        if not test_products:
            _logger.info("Todos los productos ya son almacenables")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Información'),
                    'message': _('Todos los productos ya tienen is_storable=True. No se requiere experimentación.'),
                    'sticky': False,
                    'type': 'info',
                }
            }
        
        test_product = test_products[0]
        _logger.info(f"Producto de prueba (is_storable=False): {test_product.name}")
        _logger.info("ESTADO INICIAL:")
        self._log_product_detailed_info(test_product)
        
        # Intentar diferentes combinaciones de campos
        experiments = [
            # Experimento 1: Copiar configuración básica del producto de referencia
            {
                'name': 'Configuración básica de referencia',
                'fields': {
                    'type': reference.type,
                    'sale_ok': reference.sale_ok,
                    'purchase_ok': reference.purchase_ok,
                    'tracking': 'none'
                }
            },
            # Experimento 2: Copiar categoría también
            {
                'name': 'Configuración + categoría de referencia',
                'fields': {
                    'type': reference.type,
                    'categ_id': reference.categ_id.id if reference.categ_id else False,
                    'sale_ok': reference.sale_ok,
                    'purchase_ok': reference.purchase_ok,
                    'tracking': 'none'
                }
            },
            # Experimento 3: Copiar UdM también
            {
                'name': 'Configuración + categoría + UdM',
                'fields': {
                    'type': reference.type,
                    'categ_id': reference.categ_id.id if reference.categ_id else False,
                    'uom_id': reference.uom_id.id if reference.uom_id else False,
                    'uom_po_id': reference.uom_po_id.id if reference.uom_po_id else False,
                    'sale_ok': reference.sale_ok,
                    'purchase_ok': reference.purchase_ok,
                    'tracking': 'none'
                }
            }
        ]
        
        for i, experiment in enumerate(experiments, 1):
            _logger.info(f"=== EXPERIMENTO {i}: {experiment['name']} ===")
            
            try:
                # Aplicar los cambios
                test_product.write(experiment['fields'])
                _logger.info(f"Campos aplicados: {experiment['fields']}")
                
                # Invalidar caché y verificar resultado
                test_product.invalidate_recordset(['is_storable', 'type'])
                
                _logger.info(f"RESULTADO EXPERIMENTO {i}:")
                _logger.info(f"  is_storable DESPUÉS: {test_product.is_storable}")
                self._log_product_detailed_info(test_product)
                
                if test_product.is_storable:
                    _logger.info(f"🎉 ¡ÉXITO! El experimento {i} logró hacer is_storable=True")
                    _logger.info(f"🔑 CONFIGURACIÓN GANADORA: {experiment['fields']}")
                    break
                else:
                    _logger.info(f"❌ Experimento {i} falló. is_storable sigue siendo False")
                
            except Exception as e:
                _logger.error(f"Error en experimento {i}: {e}")
        
        _logger.info("=== FIN DE EXPERIMENTOS ===")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Experimentos Completados'),
                'message': _('Experimentos para forzar is_storable=True completados. Revisa los logs para ver qué configuración funciona.'),
                'sticky': True,
                'type': 'success',
            }
        }

    def action_apply_complete_solution(self):
        """Aplica la solución completa: fuerza is_storable=True y establece tracking='none'"""
        _logger.info("=== APLICANDO SOLUCIÓN COMPLETA ===")
        
        # Obtener TODOS los productos
        all_products = self.env['product.template'].search([])
        _logger.info(f"Total de productos encontrados: {len(all_products)}")
        
        # Contadores
        storable_fixed = 0
        tracking_fixed = 0
        total_errors = 0
        
        for product in all_products:
            try:
                needs_update = False
                update_vals = {}
                
                # Verificar si necesita is_storable=True
                if not product.is_storable:
                    update_vals['is_storable'] = True
                    needs_update = True
                
                # Verificar si necesita tracking='none'
                if product.tracking != 'none':
                    update_vals['tracking'] = 'none'
                    needs_update = True
                
                if needs_update:
                    _logger.info(f"Actualizando producto: {product.name} (ID: {product.id})")
                    _logger.info(f"  Valores a cambiar: {update_vals}")
                    
                    # Aplicar cambios
                    product.write(update_vals)
                    
                    # Contar las correcciones
                    if 'is_storable' in update_vals:
                        storable_fixed += 1
                    if 'tracking' in update_vals:
                        tracking_fixed += 1
                        
            except Exception as e:
                total_errors += 1
                _logger.error(f"Error actualizando producto {product.name}: {e}")
        
        # Si hubo errores con el método normal, intentar con SQL
        if total_errors > 0:
            _logger.warning(f"Hubo {total_errors} errores. Intentando con SQL directo...")
            try:
                # Forzar is_storable=True para todos
                self.env.cr.execute(
                    "UPDATE product_template SET is_storable = TRUE WHERE is_storable = FALSE"
                )
                affected_storable = self.env.cr.rowcount
                
                # Forzar tracking='none' para todos
                self.env.cr.execute(
                    "UPDATE product_template SET tracking = 'none' WHERE tracking != 'none'"
                )
                affected_tracking = self.env.cr.rowcount
                
                self.env.cr.commit()
                
                _logger.info(f"SQL: {affected_storable} productos actualizados para is_storable")
                _logger.info(f"SQL: {affected_tracking} productos actualizados para tracking")
                
                storable_fixed += affected_storable
                tracking_fixed += affected_tracking
                
            except Exception as sql_error:
                _logger.error(f"Error con SQL: {sql_error}")
        
        _logger.info(f"=== SOLUCIÓN COMPLETA APLICADA ===")
        _logger.info(f"Productos con is_storable corregido: {storable_fixed}")
        _logger.info(f"Productos con tracking corregido: {tracking_fixed}")
        _logger.info(f"Errores totales: {total_errors}")
        
        message = _('Solución aplicada exitosamente!\n\n') + \
                 _('• Productos con checkbox visible: %s\n') % storable_fixed + \
                 _('• Productos con tracking desactivado: %s\n') % tracking_fixed + \
                 _('• Errores: %s') % total_errors
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('¡Solución Completa Aplicada!'),
                'message': message,
                'sticky': True,
                'type': 'success',
            }
        }
