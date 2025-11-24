import sys
import zipfile
import os
from os import path
import shutil
import zipfile as zp
import re
import pyutil
import json
import requests
from pathlib import Path
from datetime import date
from resources import MigrateResources
from datetime import datetime, timezone
import csv
import time
import xlsxwriter


with open("config/app_config.json") as json_data_file:
    data = json.load(json_data_file)

# Set variables based on loaded data
apigeex_mgmt_url = data.get("apigeex_mgmt_url", "")
apigeex_org_name = data.get("apigeex_org_name", "")
apigeex_token = data.get("apigeex_token", "")
apigeex_env = data.get("apigeex_env", "")
apigee_edge_host = data.get("apigee_edge_host", "")
folder_name = data.get("folder_name", "")
apigeex_domain = data.get("apigeex_domain", "")
apigee_edge_env=data.get("apigee_edge_env", "")
apigee_edge_mgmt_url=data.get("apigee_edge_mgmt_url", "")
apigee_edge_org_name = data.get("apigee_edge_org_name", "")
apigee_edge_token =data.get("apigee_edge_token", "")
user_choice =''

# Create a log file with timestamp
log_file = "logs/migration_logs.txt"
with open(log_file, "w+", encoding="utf-8") as f:
    timestamp = datetime.now(timezone.utc)
    f.write(f"TimeStamp {timestamp}\n")

    print("This tool migrates all Apigee Edge Data to ApigeeX")


response,status_code=MigrateResources.get_resource("apis",apigeex_mgmt_url,apigeex_org_name,apigeex_token)
if status_code == 200:
    user_choice =''
print("User Authenticated Successfully")
while user_choice !='quit':
    print("--------------------------------------------")    
    print("|  Type All to Migrate All Resources      |")
    print("|  Type Proxy to Migrate Only Proxies     |")
    print("|  Type SF to Migrate Only SharedFlows    |")
    print("|  Type Product to Migrate Only Products  |")
    print("|  Type App to Migrate Only Apps          |")
    print("|  Type KVM to Migrate Only KVM           |")
    print("|  Type TS to Migrate Only Target Servers |")
    print("|  Type DEV to Migrate Only Developers    |")
    print("|  Type QUIT to Migrate EXIT              |")
    print("--------------------------------------------")   
    user_choice = input("Enter Your Choice : ")
    user_choice = user_choice.lower().strip()
    if user_choice == "all" or user_choice == "ts":
        print("For migrating the environment-based Target Servers, please update the update_list_of_ts.csv file and TYPE proceed to Migrate Target Servers")            
        user_choice = input("TYPE proceed : ")
        if user_choice == "proceed":
            try:
                ts_path = os.path.join(folder_name, "targetservers", "env", apigee_edge_env)
                ts_names_arr = os.listdir(ts_path)

                # Specify the path where you want to save the Excel file
                file_path = './migration_logs/migrated_ts.xlsx'
                # Create a new Excel workbook and add a worksheet
                workbook = xlsxwriter.Workbook(file_path)
                worksheet = workbook.add_worksheet()
                # Initialize a row index counter
                row_index = 0

                for filename in ts_names_arr:
                    print(filename)
                    f_path = os.path.join(ts_path, filename)

                    with open(f_path, 'r') as file2:
                        data = json.load(file2)

                    status_target_servers, response_target_servers_text = MigrateResources.Target_Servers(apigeex_mgmt_url, apigeex_org_name, apigeex_token, data, apigeex_env)
                    json_response_target_servers = json.loads(response_target_servers_text)

                    if status_target_servers == 200:
                        # Write each name to the worksheet
                        worksheet.write(row_index, 0, str(filename))  # write(row, col, value)
                        # Manually increase the row index
                        row_index += 1

                    with open(log_file, "a", encoding="utf-8") as f:
                        if status_target_servers >= 400:
                            new_log = f"|| Target Server {filename}  || {status_target_servers} || {json_response_target_servers['error']['message']} || \n"
                        else:
                            new_log = f"|| Target Server {filename}  || {status_target_servers} || Target Server Created Successfully || \n"
                        f.write(new_log)

                print("Target Servers Migration Complete")
                # Close the workbook
                workbook.close()
            except requests.exceptions.RequestException as e:
                print("Failed with:", e.strerror)                           
                with open("error_log.txt", "a") as file:
                    file.write(e.strerror)  # Write response text to error log

    if user_choice == "all" or user_choice == "kvm":
        print("For migrating the environment-based KVMs, please update the update_list_of_kvms.csv file and TYPE proceed to Migrate KVMs")
        user_choice = input("TYPE proceed : ")
        if user_choice == "proceed":
            try:
                kmv_path = os.path.join(folder_name, "keyvaluemaps", "env", apigee_edge_env)
                print(kmv_path)
                kvm_names_arr = os.listdir(kmv_path)
                # Specify the path where you want to save the Excel file
                file_path = './migration_logs/migrated_kvm.xlsx'
                # Create a new Excel workbook and add a worksheet
                workbook = xlsxwriter.Workbook(file_path)
                worksheet = workbook.add_worksheet()
                # Initialize a row index counter
                row_index = 0
                with open('update_list_of_kvms.csv', 'r') as fd:
                    reader = csv.reader(fd)
                    kvm_data_list = []

                    for selected_kvm in reader:
                        if selected_kvm == ["KVM Names"]:
                            continue
                        if selected_kvm == ["Privacy"]:
                            continue

                        selected_kvm = selected_kvm[0]
                        selected_kvm = selected_kvm.strip('[]\'')
                        
                        if selected_kvm in kvm_names_arr:
                            print("KVM Matched")
                            f_path = os.path.join(kmv_path, selected_kvm)
                            
                            with open(f_path, 'r') as file2:
                                data = json.load(file2)
                                name = data['name']
                                print(name)
                                encrypted = data['encrypted']
                                print(encrypted)

                            kvm_data = {
                                "name": name,
                                "encrypted": str(encrypted)
                            }
                            kvm_data_list.append(kvm_data)

                for kvm_data in kvm_data_list:
                    status_kvms, response_kvms_text = MigrateResources.Kvms_Env_Level(apigeex_mgmt_url, apigeex_org_name, apigeex_token, kvm_data, apigeex_env)
                    print(status_kvms)
                    json_response_kvms = json.loads(response_kvms_text)
                    if status_kvms == 201:
                        # Write each name to the worksheet
                        worksheet.write(row_index, 0, str(kvm_data["name"]))  # write(row, col, value)
                        # Manually increase the row index
                        row_index += 1

                    with open(log_file, "a", encoding="utf-8") as f:
                        if status_kvms >= 400:
                            new_log = f"|| KVM {kvm_data['name']}  || {status_kvms} || {json_response_kvms['error']['message']} || \n"
                        else:
                            new_log = f"|| KVM {kvm_data['name']}  || {status_kvms} || KVM Created Successfully || \n"
                        f.write(new_log)

                print("KVMs Migration for environment Complete")
                # Close the workbook
                workbook.close()

                # print("Now, lets try to validate the migrated resources")
                # validate.proceed_validate()


            except requests.exceptions.RequestException as e:
                print("Failed with:", e.strerror)                           
                with open("error_log.txt", "a") as file:
                    file.write(e.strerror)  # Write response text to error log                  

            try:
                kmv_org_path = os.path.join(folder_name, "keyvaluemaps", "org")
                kvm_org_names_arr = os.listdir(kmv_org_path)

                for filename in kvm_org_names_arr:
                    print(filename)
                    f_path = os.path.join(kmv_org_path, filename)
                    print(f_path)
                    if f_path == "data_edge\\keyvaluemaps\\org\\privacy":
                        print("Skipping the Privacy KVM at ORG Level")
                        continue
                    with open(f_path, 'r') as file2:
                        data = json.load(file2)
                        name = data['name']
                        print(name)
                        encrypted = data['encrypted']
                        print(encrypted)
                                
                    kvm_data = {
                        "name": name,
                        "encrypted": str(encrypted)
                    }

                    status_org_kvms, response_org_kvms_text = MigrateResources.Kvms_Org_Level(apigeex_mgmt_url, apigeex_org_name, apigeex_token, kvm_data)
                    json_response_org_kvms = json.loads(response_org_kvms_text)

                    with open(log_file, "a", encoding="utf-8") as f:
                        if status_org_kvms >= 400:
                            new_log = f"|| KVM ORG {filename}  || {status_org_kvms} || {json_response_org_kvms['error']['message']} || \n"
                        else:
                            new_log = f"|| KVM ORG {filename}  || {status_org_kvms} || Org KVM Created Successfully || \n"
                        f.write(new_log)

                print("All KVMs Migrated")
            except requests.exceptions.RequestException as e:
                print("Failed with:", e.strerror)                           
                with open("error_log.txt", "a") as file:
                    file.write(e.strerror)  # Write response text to error log                 


    if user_choice == "all" or user_choice == "dev":
        try:
            dev_path = os.path.join(folder_name, "developers")
            dev_names_arr = os.listdir(dev_path)

            # Specify the path where you want to save the Excel file
            file_path = './migration_logs/migrated_dev.xlsx'
            # Create a new Excel workbook and add a worksheet
            workbook = xlsxwriter.Workbook(file_path)
            worksheet = workbook.add_worksheet()
            # Initialize a row index counter
            row_index = 0

            for filename in dev_names_arr:
                print(filename)
                f_path = os.path.join(dev_path, filename)

                with open(f_path, 'r') as file2:
                    data = json.load(file2)
                    firstName = data['firstName']
                    lastName = data['lastName']
                    userName = data['userName']
                    email = data['email']
                    organizationName = data['organizationName']

                developer_data = {
                    "firstName": firstName,
                    "lastName": lastName,
                    "userName": userName,
                    "email": email,
                    "organizationName": organizationName
                }

                status_developers, response_developers_text = MigrateResources.Developers(apigeex_mgmt_url, apigeex_org_name, apigeex_token, developer_data)
                json_response_developers = json.loads(response_developers_text)

                print(status_developers)

                if status_developers == 201:
                    # Write each name to the worksheet
                    worksheet.write(row_index, 0, str(filename))  # write(row, col, value)
                    # Manually increase the row index
                    row_index += 1

                with open(log_file, "a", encoding="utf-8") as f:
                    if status_developers >= 400:
                        new_log = f"|| Developers {filename}  || {status_developers} || {json_response_developers['error']['message']} || \n"
                    else:
                        new_log = f"|| Developers {filename}  || {status_developers} || Developers Created Successfully || \n"
                    f.write(new_log)

            print("All Developers Downloaded")
            # Close the workbook
            workbook.close()
        except requests.exceptions.RequestException as e:
            print("Failed with:", e.strerror)                           
            with open("error_log.txt", "a") as file:
                file.write(e.strerror)  # Write response text to error log 
    
    if user_choice == "all" or user_choice == "product":
        try:
            prod_path = os.path.join(folder_name, "apiproducts")
            prod_names_arr = os.listdir(prod_path)

            # Specify the path where you want to save the Excel file
            file_path = './migration_logs/migrated_product.xlsx'
            # Create a new Excel workbook and add a worksheet
            workbook = xlsxwriter.Workbook(file_path)
            worksheet = workbook.add_worksheet()
            # Initialize a row index counter
            row_index = 0

            for filename in prod_names_arr:
                #print(filename)
                f_path = os.path.join(prod_path, filename)

                MigrateResources.Rewrite_product_file(f_path)

                with open(f_path, 'r') as file2:
                    data = json.load(file2)
                    #print(data)

                status_product, response_product_text = MigrateResources.Migrate_product(apigeex_mgmt_url, apigeex_org_name, apigeex_token, data)
                json_response_product = json.loads(response_product_text)

                if status_product == 201:
                    # Write each name to the worksheet
                    worksheet.write(row_index, 0, str(filename))  # write(row, col, value)
                    # Manually increase the row index
                    row_index += 1

                with open(log_file, "a", encoding="utf-8") as f:
                    if status_product >= 400:
                        new_log = f"|| PRODUCT {filename}  || {status_product} || {json_response_product['error']['message']} || \n"
                        print(new_log)
                    else:
                        print("Product cretated: ",{filename})
                        new_log = f"|| PRODUCT {filename}  || {status_product} || PRODUCT Created Successfully || \n"
                    f.write(new_log)

            print("All Products Migrated")
            # Close the workbook
            workbook.close()
        except requests.exceptions.RequestException as e:
            print("Failed with:", e.strerror)                           
            with open("error_log.txt", "a") as file:
                file.write(e.strerror)  # Write response text to error log

    if user_choice == "all" or user_choice == "app":
        try:
            app_path = os.path.join(folder_name, "apps")
            dev_path = os.path.join(folder_name, "developers")
            app_names_arr = os.listdir(app_path)
            number_of_apps = len(app_names_arr)

            # Specify the path where you want to save the Excel file
            file_path = './migration_logs/migrated_app.xlsx'
            # Create a new Excel workbook and add a worksheet
            workbook = xlsxwriter.Workbook(file_path)
            worksheet = workbook.add_worksheet()
            # Initialize a row index counter
            row_index = 0

            for filename in app_names_arr:
                f_path = os.path.join(app_path, filename)
                with open(f_path, 'r') as file2:
                    line_as_string = file2.read()

                #get appName
                appData = json.loads(line_as_string)
                appName = appData.get('name')

                matches_app_name = re.findall('name"\s*:\s*"(.*?)"', line_as_string, re.DOTALL)
                matches_products_name = re.findall('apiproduct"\s*:\s*"(.*?)"', line_as_string, re.DOTALL)
                matches_consumerKey = re.findall('consumerKey"\s*:\s*"(.*?)"', line_as_string, re.DOTALL)
                number_of_key = len(matches_consumerKey)
                matches_consumerSecret = re.findall('consumerSecret"\s*:\s*"(.*?)"', line_as_string, re.DOTALL)
                matches_expiresAt = re.findall('expiresAt"\s*:(.*?),', line_as_string, re.DOTALL)
                matches_status = re.findall('status"\s*:\s*"(.*?)"', line_as_string, re.DOTALL)
                matches_expiresInSeconds = re.findall('status"\s*:\s*"(.*?)"', line_as_string, re.DOTALL)
                matches_attributes_name = re.findall('name"\s*:\s*"(.*?)"', line_as_string, re.DOTALL)

                data = {}
                data_only_product_names = {}
                mul_arr = []
                filename = filename.strip(" ")
                user_selected_app = ''
                empty_prod_name = []

                with open(f_path, 'r') as file2:
                    line_as_string = file2.read()

                match_user_selected_app_from_list = re.findall('name"\s*\:\s*"(.*?)"', line_as_string, re.DOTALL)
                user_selected_app = match_user_selected_app_from_list[-1]
                print(user_selected_app)

                empty_prod_name = list(set(matches_products_name))
                print(empty_prod_name)

                with open(f_path, 'r') as file2:
                    file_content = file2.read()

                file_content = re.sub('"apiProducts"\s*\:\s*\[ \]\,', f'"apiProducts" : {empty_prod_name},', file_content)
                file_content = re.sub('"lastModifiedBy" : .*,', '', file_content)
                file_content = re.sub('"lastModifiedAt" : .*,', '', file_content)
                file_content = re.sub('"createdAt" : .*,', '', file_content)
                file_content = re.sub('"environments" : .*,', '', file_content)
                file_content = re.sub('"createdBy" : .*,', '', file_content)
                file_content = re.sub("'", '"', file_content)

                data_only_product_names['apiProducts'] = empty_prod_name
                data2 = json.loads(file_content)

                custom_attributes_name = matches_attributes_name[2:-1]
                print("custom Attributes", custom_attributes_name)
                number_of_custom_attributes = len(custom_attributes_name)
                timestamp = str(datetime.now(timezone.utc))
                print(number_of_custom_attributes)

                developer_id = data2['developerId']                
                #developer_response, developer_status_code = MigrateResources.Get_developer_email_by_id(apigee_edge_mgmt_url, apigee_edge_org_name, apigee_edge_token, developer_id)
                #developer_email = json.loads(developer_response.text)['email']
                developer_email="ahamilton@example.com"
                #print(developer_email)

                try:
                    url = f"https://apigee.googleapis.com/v1/organizations/{apigeex_org_name}/developers/{developer_email}/apps/"
                    payload = json.dumps(data2)
                    headers = {'Authorization': f'Bearer {apigeex_token}', 'Content-Type': 'application/json'}
                    response = requests.post(url, headers=headers, data=payload)
                    status_code = response.status_code
                    print(status_code)
                    response_text_app = response.text
                    print(response_text_app)
                    json_response_apps = json.loads(response_text_app)

                    if status_code == 201:
                        # Write each name to the worksheet
                        worksheet.write(row_index, 0, str(appName))  # write(row, col, value)
                        # Manually increase the row index
                        row_index += 1

                    with open(log_file, "a", encoding="utf-8") as f:
                        if status_code >= 400:
                            new_log="|| APP "+user_selected_app+"  || "+str(status_code)+" || "+str(json_response_apps['error']['message'])+" || "+"\n"
                            f.write(new_log)
                            f.close()
                            print(new_log)
                        else:
                            new_log="|| APP "+user_selected_app+"  || "+str(status_code)+" || APP Created Successfully || "+"\n"
                            f.write(new_log)
                            f.close()
                            print(new_log)
                    print("All Apps Migrated")

                    for i in range(len(matches_consumerKey)):
                        current_epoch_time = int(time.time() * 1000)

                        consumerKey = matches_consumerKey[i].strip()
                        consumerSecret = matches_consumerSecret[i].strip()
                        expiresAt = int(matches_expiresAt[i].strip())
                        status = matches_status[i].strip()

                        key_data_10 = {
                            'consumerKey': consumerKey,
                            'consumerSecret': consumerSecret,
                            'expiresAt': str(expiresAt),
                            'status': status
                        }
                        print(json.dumps(key_data_10))

                        if expiresAt > current_epoch_time or expiresAt == -1:
                            url = f"https://apigee.googleapis.com/v1/organizations/{apigeex_org_name}/developers/{developer_email}/apps/{user_selected_app}/keys"
                            payload = json.dumps(key_data_10)
                            headers = {'Authorization': f'Bearer {apigeex_token}', 'Content-Type': 'application/json'}
                            response = requests.post(url, headers=headers, data=payload)
                            print(response.text)
                            status_code_key = response.status_code
                            print(status_code_key)

                            url = f"https://apigee.googleapis.com/v1/organizations/{apigeex_org_name}/developers/{developer_email}/apps/{user_selected_app}/keys/{matches_consumerKey[i]}"
                            print(url)
                            print(json.dumps(data_only_product_names))
                            payload = json.dumps(data_only_product_names)
                            headers = {'Authorization': f'Bearer {apigeex_token}', 'Content-Type': 'application/json'}
                            response = requests.post(url, headers=headers, data=payload)
                            print(response.text)
                            status_code_update = response.status_code
                        
                except requests.exceptions.RequestException as e:
                    print("Failed with:", e.strerror)                           
                    with open("error_log.txt", "a") as file:
                        file.write(e.strerror)  # Write response text to error log
            # Close the workbook
            workbook.close()
        except requests.exceptions.RequestException as e:
            print("Failed with:", e.strerror)                           
            with open("error_log.txt", "a") as file:
                file.write(e.strerror)  # Write response text to error log
    if user_choice == "all" or user_choice == "proxy":
        try:
            proxy_path = os.path.join(folder_name, "proxies")
            proxy_names_arr = os.listdir(proxy_path)

            # Specify the path where you want to save the Excel file
            file_path = './migration_logs/migrated_proxy.xlsx'
            # Create a new Excel workbook and add a worksheet
            workbook = xlsxwriter.Workbook(file_path)
            worksheet = workbook.add_worksheet()
            # Initialize a row index counter
            row_index = 0

            for filename in proxy_names_arr:
                print(filename)
                file_name_without_zip = re.search(r'(.*?)\.zip', filename)
                
                if file_name_without_zip:
                    file_name_without_zip = file_name_without_zip.group(1)
                    print(file_name_without_zip)
                    
                    status_proxy, response_proxy_text = MigrateResources.Proxies(apigeex_mgmt_url,apigeex_org_name,apigeex_token, proxy_path, file_name_without_zip)
                    json_response_proxy = json.loads(response_proxy_text)

                    if status_proxy == 200:
                        # Write each name to the worksheet
                        worksheet.write(row_index, 0, str(filename))  # write(row, col, value)
                        # Manually increase the row index
                        row_index += 1

                    with open(log_file, "a", encoding="utf-8") as f:
                        if status_proxy >= 400:
                            new_log = f"|| PROXY {filename}  || {status_proxy} || {json_response_proxy['error']['message']} || \n"
                        else:
                            new_log = f"|| PROXY {filename}  || {status_proxy} || PROXY Created Successfully || \n"
                        f.write(new_log)

            print("All Proxies Migrated")
            # Close the workbook
            workbook.close()
        except requests.exceptions.RequestException as e:
            print("Failed with:", e.strerror)                           
            with open("error_log.txt", "a") as file:
                file.write(e.strerror)  # Write response text to error log
    
    if user_choice == "all" or user_choice == "sf":
        try:
            sf_path = os.path.join(folder_name, "sharedflows")
            sf_names_arr = os.listdir(sf_path)

            # Specify the path where you want to save the Excel file
            file_path = './migration_logs/migrated_sf.xlsx'
            # Create a new Excel workbook and add a worksheet
            workbook = xlsxwriter.Workbook(file_path)
            worksheet = workbook.add_worksheet()
            # Initialize a row index counter
            row_index = 0

            for filename in sf_names_arr:
                print(filename)
                file_name_without_zip = re.search(r'(.*?)\.zip', filename)
                
                if file_name_without_zip:
                    file_name_without_zip = file_name_without_zip.group(1)
                    print(file_name_without_zip)
                    
                    status_sf, response_sf_text = MigrateResources.Shared_Flows(apigeex_mgmt_url, apigeex_org_name,apigeex_token,sf_path, file_name_without_zip)
                    json_response_sf = json.loads(response_sf_text)

                    if status_sf == 200:
                        # Write each name to the worksheet
                        worksheet.write(row_index, 0, str(filename))  # write(row, col, value)
                        # Manually increase the row index
                        row_index += 1


                    with open(log_file, "a", encoding="utf-8") as f:
                        if status_sf >= 400:
                            new_log = f"|| SHARED FLOW {filename}  || {status_sf} || {json_response_sf['error']['message']} || \n"
                        else:
                            new_log = f"|| SHARED FLOW {filename}  || {status_sf} || SHARED FLOW Created Successfully || \n"
                        f.write(new_log)

            print("All Shared Flows Downloaded")
            # Close the workbook
            workbook.close()
        except requests.exceptions.RequestException as e:
            print("Failed with:", e.strerror)                           
            with open("error_log.txt", "a") as file:
                file.write(e.strerror)  # Write response text to error log
else:
    print("Error !!! ")
    print("Invalid Org Name or Invalid Token")
with open("error_log.txt", "a") as file:
    file.write(response.text)  # Write response text to error log
