schema="""
MySQL database: northwind

Tables:
  customers(id, company, last_name, first_name, email_address, job_title,
            business_phone, city, state_province, zip_postal_code, country_region)

  employees(id, company, last_name, first_name, email_address, job_title,
            city, state_province, country_region)

  orders(id, employee_id, customer_id, order_date, shipped_date, shipper_id,
         shipping_fee, taxes, payment_type, paid_date, tax_rate,
         tax_status_id, status_id)

  order_details(id, order_id, product_id, quantity, unit_price, discount,
                status_id, date_allocated, purchase_order_id, inventory_id)

  products(id, product_code, product_name, description, standard_cost,
           list_price, reorder_level, target_level, quantity_per_unit,
           discontinued, minimum_reorder_quantity, category)

  suppliers(id, company, last_name, first_name, email_address, job_title,
            city, state_province, country_region)

  shippers(id, company, last_name, first_name, business_phone)

  purchase_orders(id, supplier_id, created_by, submitted_date, creation_date,
                  status_id, expected_date, shipping_fee, taxes,
                  payment_date, payment_amount, payment_method)

  purchase_order_details(id, purchase_order_id, product_id, quantity,
                         unit_cost, date_received, posted_to_inventory)

  inventory_transactions(id, transaction_type, transaction_created_date,
                         product_id, quantity, purchase_order_id, customer_order_id)

  invoices(id, order_id, invoice_date, due_date, tax, shipping, amount_due)

  order_details_status(id, status_name)
  orders_status(id, status_name)
  orders_tax_status(id, tax_status_name)
  purchase_order_status(id, status)
  inventory_transaction_types(id, type_name)
  privileges(id, privilege_name)
  employee_privileges(employee_id, privilege_id)
"""