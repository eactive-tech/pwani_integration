# Copyright (c) 2026, laxman and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests, json

class PwaniDataUpload(Document):
	def before_save(self):

		self.generate_customer_file()



	def generate_customer_file(self):


		data = frappe.db.sql("""
			SELECT
				name customer_name,
				customer_name customer_name,
				"Active" account_status
			FROM tabCustomer
			limit 3
		""", as_dict=True)

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

			# Create File attachment
			file_doc = frappe.get_doc({
				"doctype": "File",
				"file_name": f"items_{self.name}.csv",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"attached_to_field": "customer_files"
				"content": csv_content,
				"is_private": 1
			})

			file_doc.insert(ignore_permissions=True)

			frappe.msgprint("CSV Attached Successfully")

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

		auth_response = frappe.make_post_request(auth_url, data=json.dumps(auth_payload), headers=auth_headers)

		return auth_response.get("token")

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

		frappe.log_error(
			message=response.text,
			title="Customer Upload Response"
		)
