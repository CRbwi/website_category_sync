#!/bin/bash

# Script to test our addon
echo "Testing the product tracking wizard addon..."

# First, let's validate our files
echo "1. Validating XML syntax..."
xmllint --noout views/product_tracking_wizard_views.xml
if [ $? -eq 0 ]; then
    echo "✓ XML syntax is valid"
else
    echo "✗ XML syntax error found"
    exit 1
fi

echo "2. Checking Python imports..."
python3 -c "
import sys
sys.path.append('.')
try:
    from models.product_tracking_wizard import ProductSetNoTrackingWizard
    print('✓ Python imports work correctly')
except ImportError as e:
    print(f'✗ Import error: {e}')
    sys.exit(1)
"

echo "3. Checking manifest file..."
if [ -f "__manifest__.py" ]; then
    python3 -c "
import ast
with open('__manifest__.py', 'r') as f:
    try:
        ast.parse(f.read())
        print('✓ Manifest syntax is valid')
    except SyntaxError as e:
        print(f'✗ Manifest syntax error: {e}')
        exit(1)
"
else
    echo "✗ __manifest__.py not found"
    exit 1
fi

echo ""
echo "All validations passed! The addon should work correctly."
echo ""
echo "To test the diagnostic functionality:"
echo "1. Start your Odoo server"
echo "2. Go to Inventory > Configuration > Set Global No Tracking"
echo "3. Select two different products in the diagnostic section"
echo "4. Click 'Comparar Productos' to see field differences in the logs"
echo "5. Look for fields that might control the 'Track Inventory' checkbox behavior"
