# Copyright (c) 2026, laxman and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests, json

class PwaniDataUpload(Document):
	def before_save(self):
		self.generate_customer_file()
		self.generate_item_file()
		self.generate_sales_invoice_file()

	def before_submit(self):

		token = self.get_auth_token()
		self.upload_customer_file(token)
		self.upload_item_file(token)
		self.upload_sales_invoice_file(token)


	def delete_existing_file(self, fieldname):
		if not self.name:
			return

		existing_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"attached_to_field": fieldname,
			},
			fields=["name"],
		)

		for file_row in existing_files:
			frappe.delete_doc("File", file_row.name, force=True, ignore_permissions=True)


	def generate_customer_file(self):
		"""Generate CSV file with distinct customers from sales invoices.
		
		Filters by:
		- Upload date
		- Item group (and its child groups)
		"""
		# Get item group lft and rgt for filtering
		if not self.item_group:
			frappe.msgprint("Item Group not configured")
			return
		
		item_group = frappe.get_doc("Item Group", self.item_group)
		item_group_lft = item_group.lft
		item_group_rgt = item_group.rgt

		data = frappe.db.sql("""
			SELECT DISTINCT
				si.customer customer_code,
				si.customer_name,
				"Active" account_status
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii on sii.parent = si.name
			INNER JOIN `tabItem` i on i.name = sii.item_code
			INNER JOIN `tabItem Group` ig on ig.name = i.item_group
			WHERE si.posting_date = %s
			AND si.docstatus in (0, 1)
			AND ig.lft >= %s
			AND ig.rgt <= %s
			AND si.update_stock = 1
			ORDER BY si.customer
		""", (self.upload_date, item_group_lft, item_group_rgt), as_dict=True)

		if data:

			# CSV Content
			csv_content = ""

			# Header
			headers = list(data[0].keys())
			csv_content = csv_content+ ",".join(headers) + "\n"

			# Rows
			for row in data:
				values = []

				for h in headers:
					value = row.get(h) or ""

					# Escape commas and quotes
					value = str(value).replace('"', '""')

					if "," in value or '"' in value:
						value = f'"{value}"'

					values.append(value)

				csv_content = csv_content+ ",".join(values) + "\n"

			# Delete any existing attachment for this field before creating a new one
			self.delete_existing_file("customer_file")

			# Create File attachment
			file_doc = frappe.get_doc({
				"doctype": "File",
				"file_name": f"customer_{self.name}.csv",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"attached_to_field": "customer_file",
				"content": csv_content,
				"is_private": 1
			})

			file_doc.insert(ignore_permissions=True)

			self.customer_file = file_doc.file_url

			frappe.msgprint("CSV Attached Successfully")

	def generate_item_file(self):
		"""Generate CSV file with distinct items from sales invoices.
		
		Filters by:
		- Upload date
		- Item group (and its child groups)
		- Only submitted sales invoices
		
		Includes uom_list field with JSON array of UOMs from Item doctype.
		"""
		pw_settings = frappe.get_doc("Pwani Settings")
		
		# Get item group lft and rgt for filtering
		if not self.item_group:
			frappe.msgprint("Item Group not configured")
			return
		
		item_group = frappe.get_doc("Item Group", self.item_group)
		item_group_lft = item_group.lft
		item_group_rgt = item_group.rgt
		
		data = frappe.db.sql("""
			SELECT DISTINCT
				sii.item_code distributor_product_code,
				"" manufacturer_product_code,
				i.item_group category,
				i.item_group sub_category,
				i.item_name product_name,
				i.item_name description,
				1 status
			FROM `tabSales Invoice` si
			LEFT JOIN `tabSales Invoice Item` sii on sii.parent = si.name
			LEFT JOIN `tabItem` i on i.name = sii.item_code
			LEFT JOIN `tabItem Group` ig on ig.name = i.item_group
			WHERE si.posting_date = %s
			AND si.docstatus in (0,1)
			AND ig.lft >= %s
			AND ig.rgt <= %s
			AND si.update_stock = 1
			ORDER BY sii.item_code
		""", (self.upload_date, item_group_lft, item_group_rgt), as_dict=True)

		if data:
			# Add uom_list to each row
			for row in data:
				item_code = row.get('distributor_product_code')
				
				# Get UOM list from Item doctype child table
				uom_data = frappe.db.sql("""
					SELECT `uom`, `conversion_factor`
					FROM `tabUOM Conversion Detail`
					WHERE parent = %s
					ORDER BY `idx`
				""", (item_code,), as_dict=True)
				
				# Build uom_list JSON array
				uom_list = []
				for uom in uom_data:
					uom_list.append({
						"p_code_distributor": item_code,
						"uom_code": uom.get('uom'),
						"uom_name": uom.get('uom'),
						"conversion_factor": uom.get('conversion_factor')
					})
				
				row['uom_list'] = json.dumps(uom_list)

			# CSV Content
			csv_content = ""

			# Header
			headers = list(data[0].keys())
			csv_content = csv_content+ ",".join(headers) + "\n"

			# Rows
			for row in data:
				values = []

				for h in headers:
					value = row.get(h) or ""

					# Escape commas and quotes
					value = str(value).replace('"', '""')

					if "," in value or '"' in value:
						value = f'"{value}"'

					values.append(value)

				csv_content = csv_content+ ",".join(values) + "\n"

			# Delete any existing attachment for this field before creating a new one
			self.delete_existing_file("item_file")

			# Create File attachment
			file_doc = frappe.get_doc({
				"doctype": "File",
				"file_name": f"item_{self.name}.csv",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"attached_to_field": "item_file",
				"content": csv_content,
				"is_private": 1
			})

			file_doc.insert(ignore_permissions=True)

			self.item_file = file_doc.file_url

			frappe.msgprint("CSV Attached Successfully")

	def generate_sales_invoice_file(self):

		pw_settings = frappe.get_doc("Pwani Settings")
		
		# Get item group lft and rgt for filtering
		if not self.item_group:
			frappe.msgprint("Item Group not configured")
			return
		
		item_group = frappe.get_doc("Item Group", self.item_group)
		item_group_lft = item_group.lft
		item_group_rgt = item_group.rgt

		data = frappe.db.sql("""
			SELECT
				si.name invoice_id,
				sii.item_code product_code,
				si.customer customer_code,
				si.name erp_reference,
				si.posting_date doc_date,
				sii.uom uom_code,
				sii.qty quantity,
				sii.price_list_rate selling_price,
				(sii.price_list_rate * sii.qty) line_total
			FROM `tabSales Invoice` si
			LEFT JOIN `tabSales Invoice Item` sii on sii.parent = si.name
			LEFT JOIN `tabItem` i on i.name = sii.item_code
			LEFT JOIN `tabItem Group` ig on ig.name = i.item_group
			WHERE si.posting_date = %s
			AND ig.lft >= %s
			AND ig.rgt <= %s
			AND si.update_stock = 1
		""", (self.upload_date, item_group_lft, item_group_rgt), as_dict=True)

		if data:

			# CSV Content
			csv_content = ""

			# Header
			headers = list(data[0].keys())
			csv_content = csv_content+ ",".join(headers) + "\n"

			# Rows
			for row in data:
				values = []

				for h in headers:
					value = row.get(h) or ""

					# Escape commas and quotes
					value = str(value).replace('"', '""')

					if "," in value or '"' in value:
						value = f'"{value}"'

					values.append(value)

				csv_content = csv_content+ ",".join(values) + "\n"

			# Delete any existing attachment for this field before creating a new one
			self.delete_existing_file("sales_invoice_file")

			# Create File attachment
			file_doc = frappe.get_doc({
				"doctype": "File",
				"file_name": f"sales_invoice_{self.name}.csv",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"attached_to_field": "sales_invoice_file",
				"content": csv_content,
				"is_private": 1
			})

			file_doc.insert(ignore_permissions=True)

			self.sales_invoice_file = file_doc.file_url

			frappe.msgprint("Sales Invoice CSV Attached Successfully")

	def get_auth_token(self):
		pw_settings = frappe.get_doc("Pwani Settings")

		auth_url = f"{pw_settings.host_url}/api/v1/auth/login"

		auth_headers = {
			"Content-Type": "application/json"
		}

		auth_payload = {
			"email_address": pw_settings.user_name,
			"password": pw_settings.password
		}

		auth_response = requests.post(auth_url, data=json.dumps(auth_payload), headers=auth_headers)

		return auth_response.json().get("token")

	def log_api_request(self, request_type, endpoint, headers, request_body, response, error_message=None):
		"""
		Log API request and response to Pwani Integration Log

		"""
		try:
			success = 200 <= response.status_code < 300 if response else False
			
			log_doc = frappe.get_doc({
				"doctype": "Pwani Integration Log",
				"request_type": request_type,
				"endpoint": endpoint,
				"reference_name": self.name,
				"status_code": response.status_code if response else None,
				"success": success,
				"request_headers": json.dumps(dict(headers)) if headers else None,
				"response_headers": json.dumps(dict(response.headers)) if response else None,
				"request_body": request_body,
				"response_body": response.text if response else None,
				"error_message": error_message
			})
			log_doc.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(
				message=str(e),
				title="Error Creating Pwani Integration Log"
			)

	def upload_customer_file(self, token):
		"""
		Data Upload Request

		"""
		pw_settings = frappe.get_doc("Pwani Settings")

		url = f"{pw_settings.host_url}/api/v1/distributor-files/import/customers"

		headers = {
			"Authorization": f"Bearer {token}"
		}

		# Get file path from File doctype
		file_doc = frappe.get_doc("File", {"file_url": self.customer_file})

		file_path = file_doc.get_full_path()

		with open(file_path, "rb") as f:
			
			files = {
				"file": (file_doc.file_name, f, "text/csv")
			}

			response = requests.post(
				url,
				headers=headers,
				files=files
			)

		self.log_api_request(
			request_type="Customer Upload",
			endpoint=url,
			headers=headers,
			request_body=f"File: {file_doc.file_name}",
			response=response
		)

	def upload_item_file(self, token):
		"""
		Upload Item/Product File to Pwani

		"""
		pw_settings = frappe.get_doc("Pwani Settings")

		url = f"{pw_settings.host_url}/api/v1/distributor-files/import/products"

		headers = {
			"Authorization": f"Bearer {token}"
		}

		# Get file path from File doctype
		file_doc = frappe.get_doc("File", {"file_url": self.item_file})

		file_path = file_doc.get_full_path()

		with open(file_path, "rb") as f:
			
			files = {
				"file": (file_doc.file_name, f, "text/csv")
			}

			response = requests.post(
				url,
				headers=headers,
				files=files
			)

		self.log_api_request(
			request_type="Item Upload",
			endpoint=url,
			headers=headers,
			request_body=f"File: {file_doc.file_name}",
			response=response
		)

	def upload_sales_invoice_file(self, token):
		"""
		Upload Sales Invoice File to Pwani

		"""
		pw_settings = frappe.get_doc("Pwani Settings")

		url = f"{pw_settings.host_url}/api/v1/distributor-files/import/invoices"

		headers = {
			"Authorization": f"Bearer {token}"
		}

		# Get file path from File doctype
		file_doc = frappe.get_doc("File", {"file_url": self.sales_invoice_file})

		file_path = file_doc.get_full_path()

		with open(file_path, "rb") as f:
			
			files = {
				"file": (file_doc.file_name, f, "text/csv")
			}

			response = requests.post(
				url,
				headers=headers,
				files=files
			)

		self.log_api_request(
			request_type="Sales Invoice Upload",
			endpoint=url,
			headers=headers,
			request_body=f"File: {file_doc.file_name}",
			response=response
		)
