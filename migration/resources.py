import sys
import zipfile
import os
from os import path
import shutil
import zipfile as zp
import re
import json
import requests
from pathlib import Path
from datetime import date
from datetime import datetime, timezone

# Configuration will be passed dynamically via function parameters
# No global config loading needed


class MigrateResources:
    def __init__(self, arg):
        super(MigrateResources, self).__init__()
    
    @staticmethod
    def get_resource(resource, apigeex_mgmt_url, org, token):
        try:
            url = f"{apigeex_mgmt_url}{org}/{resource}/"
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(url, headers=headers, stream=True)
            status_code = response.status_code
            return response, status_code
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(response.text)  # Write response text to error log
            return None, str(e)

    @staticmethod
    def Migrate_app(apigeex_mgmt_url, org, token, email, data):
        try:
            url = f"{apigeex_mgmt_url}{org}/developers/{email}/apps"
            payload = json.dumps(data)
            headers = {'Authorization': f'Bearer {token}','Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, data=payload)
            status_code = response.status_code
            response_text = response.text
            return status_code, response_text
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(response.text)  # Write response text to error log
            return None, str(e)


    @staticmethod
    def Migrate_product(apigeex_mgmt_url, org, token, data):
        try:
            url = f"{apigeex_mgmt_url}{org}/apiproducts"
            payload = json.dumps(data)
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, data=payload)
            status_code = response.status_code
            response_text = response.text
            return status_code, response_text
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(response.text)  # Write response text to error log
            return None, str(e)

    # def Rewrite_product_file(path):
    #     pyutil.filereplace(path,'"lastModifiedBy" : .*,','')
    #     pyutil.filereplace(path,'"lastModifiedAt" : .*,','')
    #     pyutil.filereplace(path,'"createdAt" : .*,','')
    #     pyutil.filereplace(path,'"environments" : .*,','')
    #     pyutil.filereplace(path,'"createdBy" : .*,','')

    @staticmethod
    def Rewrite_product_file(file_path):
        try:
            with open(file_path, 'r') as file:
                content = file.read()

            # Define a list of patterns to replace
            patterns_to_replace = [
                r'"lastModifiedBy" : .*',
                r'"lastModifiedAt" : .*',
                r'"createdAt" : .*',
                r'"environments" : .*',
                r'"createdBy" : .*'
            ]

            # Iterate over the patterns and replace them with an empty string
            for pattern in patterns_to_replace:
                content = re.sub(pattern, '', content)

            # Write the modified content back to the same file
            with open(file_path, 'w') as file:
                file.write(content)

        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(response.text)  # Write response text to error log
            return None, str(e)

    @staticmethod
    def Proxies(apigeex_mgmt_url, org, token, path, filename):
        try:
            url = f"{apigeex_mgmt_url}{org}/apis?action=import&name={filename}"
            print(url)
            payload = {}
            with open(f"{path}/{filename}.zip", 'rb') as file:
                files = [(f"{filename}.zip", (f"{filename}.zip", file, 'application/zip'))]
                headers = {'Authorization': f'Bearer {token}'}
                response = requests.post(url, headers=headers, data=payload, files=files)
                status_code = response.status_code
                print(response.text)
                response_product_text = response.text
                return status_code, response_product_text
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(response.text)  # Write response text to error log
            return None, str(e)

    @staticmethod
    def Shared_Flows(apigeex_mgmt_url, org, token, path, filename):
        try:
            url = f"{apigeex_mgmt_url}{org}/sharedflows?action=import&name={filename}"
            print(url)
            payload = {}
            with open(f"{path}/{filename}.zip", 'rb') as file:
                files = [(f"{filename}.zip", (f"{filename}.zip", file, 'application/zip'))]
                headers = {'Authorization': f'Bearer {token}'}
                response = requests.post(url, headers=headers, data=payload, files=files)
                status_code = response.status_code
                print(response.text)
                response_product_text = response.text
                return status_code, response_product_text
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(response.text)  # Write response text to error log
            return None, str(e)


    @staticmethod
    def Envs(apigeex_mgmt_url, org, token):
        try:
            response, status_code = MigrateResources.get_resource("environments", apigeex_mgmt_url, org, token)
            response = re.sub(r'\n', '', response.text)
            output = re.search(r'\[(.*?)\]', response, flags=re.IGNORECASE)
            if output is not None:
                all_env = output.group(0)
                all_env = re.sub(r'[\[\]\s*]\"\"', '', all_env)
                return all_env
            else:
                print("No environments found in the response.")
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(response.text)  # Write response text to error log
            return None, str(e)

    @staticmethod
    def Target_Servers(apigeex_mgmt_url, org, token, data, env):
        try:
            url = f"{apigeex_mgmt_url}{org}/environments/{env}/targetservers"
            payload = json.dumps(data)
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, data=payload)
            status_code = response.status_code
            response_product_text = response.text
            return status_code, response_product_text
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(response.text)  # Write response text to error log
            return None, str(e)



    @staticmethod
    def Kvms_Env_Level(apigeex_mgmt_url, org, token, data, env):
        try:
            url = f"{apigeex_mgmt_url}{org}/environments/{env}/keyvaluemaps"
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, json=data)
            return response.status_code, response.text
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(str(e))  # Write error to error log
            return None, str(e)

    @staticmethod
    def Kvms_Org_Level(apigeex_mgmt_url, org, token, data):
        try:
            url = f"{apigeex_mgmt_url}{org}/keyvaluemaps"
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, json=data)
            return response.status_code, response.text
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(str(e))  # Write error to error log
            return None, str(e)



    @staticmethod
    def Developers(apigeex_mgmt_url, org, token, data):
        try:
            url = f"{apigeex_mgmt_url}{org}/developers"
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            response = requests.post(url, headers=headers, json=data)
            print(response.text)  # Print response text
            return response.status_code, response.text
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(str(e))  # Write error to error log
            return None, str(e)

    @staticmethod
    def Get_developer_email_by_id(apigee_edge_mgmt_url, org, token, developer_id):
        try:
            url = f"{apigee_edge_mgmt_url}{org}/developers/{developer_id}"
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(url, headers=headers)
            status_code = response.status_code
            return response, status_code
        except requests.exceptions.RequestException as e:
            print(f"Failed with: {e.strerror}")
            with open("error_log.txt", "a") as file:
                file.write(str(e))  # Write error to error log
            return None, str(e)
	    