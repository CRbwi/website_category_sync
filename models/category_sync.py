from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    inventory_category_id = fields.Many2one(
        'product.category',
        string='Original Inventory Category',
        index=True,
        help="The inventory category this website category was created from."
    )

class CategorySyncManager(models.AbstractModel):
    _name = 'category.sync.manager'
    _description = 'Manages synchronization of inventory categories to website categories'

    @api.model
    def _find_or_create_website_category(self, inventory_category, website_category_map):
        # Check cache first
        if inventory_category.id in website_category_map:
            return website_category_map[inventory_category.id]

        website_cat = self.env['product.public.category'].search([
            ('inventory_category_id', '=', inventory_category.id)
        ], limit=1)

        if not website_cat:
            website_cat_vals = {
                'name': inventory_category.name,
                'inventory_category_id': inventory_category.id,
            }
            website_cat = self.env['product.public.category'].create(website_cat_vals)
            _logger.info(f"Created new website category '{website_cat.name}' (ID: {website_cat.id}) from inventory category '{inventory_category.name}' (ID: {inventory_category.id}).")
        else:
            if website_cat.name != inventory_category.name: # Sync name if changed
                website_cat.name = inventory_category.name
                _logger.info(f"Updated name for website category '{website_cat.name}' from inventory category '{inventory_category.name}'.")
        
        website_category_map[inventory_category.id] = website_cat.id
        return website_cat.id

    @api.model
    def sync_categories_to_website(self):
        _logger.info("Starting synchronization of inventory categories to website categories...")
        
        inventory_categories = self.env['product.category'].search([])
        website_category_map = {} # Cache: {inv_cat_id: web_cat_id}

        # First pass: Create/update all website categories and populate map
        for inv_cat in inventory_categories:
            self._find_or_create_website_category(inv_cat, website_category_map)

        # Second pass: Set parents for website categories
        for inv_cat in inventory_categories:
            website_cat_id = website_category_map.get(inv_cat.id)
            if not website_cat_id:
                _logger.error(f"Consistency error: Inventory category '{inv_cat.name}' (ID: {inv_cat.id}) not found in map during parent assignment.")
                continue
            
            website_cat = self.env['product.public.category'].browse(website_cat_id)
            
            if inv_cat.parent_id:
                parent_website_cat_id = website_category_map.get(inv_cat.parent_id.id)
                if parent_website_cat_id:
                    if website_cat.parent_id.id != parent_website_cat_id:
                        website_cat.parent_id = parent_website_cat_id
                        _logger.info(f"Set parent for website category '{website_cat.name}' to '{website_cat.parent_id.name}'.")
                else:
                    _logger.warning(f"Could not find mapped parent website category for inventory parent: {inv_cat.parent_id.name} (ID: {inv_cat.parent_id.id}).")
            elif website_cat.parent_id: # No parent in inventory, so ensure no parent on website
                website_cat.parent_id = False
                _logger.info(f"Set website category '{website_cat.name}' as a top-level category.")

        # Third pass: Assign products to the correct website category hierarchy
        all_managed_website_category_ids = self.env['product.public.category'].search([
            ('inventory_category_id', '!=', False)
        ]).ids
        
        all_products = self.env['product.template'].search([('categ_id', '!=', False)])

        for product_tmpl in all_products:
            inv_cat = product_tmpl.categ_id # Product's direct inventory category
            
            target_website_category_hierarchy_ids = []
            temp_inv_cat = inv_cat
            while temp_inv_cat:
                mapped_web_cat_id = website_category_map.get(temp_inv_cat.id)
                if mapped_web_cat_id:
                    target_website_category_hierarchy_ids.append(mapped_web_cat_id)
                else:
                    _logger.warning(f"Inventory category {temp_inv_cat.name} (ID: {temp_inv_cat.id}) not in website_category_map for product '{product_tmpl.name}'. It might be a new/unprocessed category.")
                    break 
                temp_inv_cat = temp_inv_cat.parent_id
            
            current_public_ids_set = set(product_tmpl.public_categ_ids.ids)
            
            # Start with non-managed categories the product is already in
            final_public_ids_set = {pid for pid in current_public_ids_set if pid not in all_managed_website_category_ids}
            
            # Add the target hierarchy
            for target_id in target_website_category_hierarchy_ids:
                final_public_ids_set.add(target_id)
            
            if final_public_ids_set != current_public_ids_set:
                product_tmpl.public_categ_ids = [(6, 0, list(final_public_ids_set))]
                _logger.info(f"Updated website categories for product '{product_tmpl.name}' (ID: {product_tmpl.id}) based on inventory category '{inv_cat.name}'. New Web IDs: {list(final_public_ids_set)}")

        _logger.info("Synchronization of inventory categories to website categories completed.")
        return True

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def action_sync_inventory_categories_to_website(self):
        self.env['category.sync.manager'].sync_categories_to_website()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Synchronization Complete'),
                'message': _('Inventory to Website category synchronization has finished.'),
                'type': 'success',
                'sticky': False,
            }
        }
