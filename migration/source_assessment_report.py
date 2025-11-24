import xlsxwriter
import os
import shutil
import json
import re
import zipfile

def add_new_sheet(resources,resource_str):
	row=0
	col=0
	worksheet_resources = workbook.add_worksheet(resource_str)
	if len(resources) > 0 and isinstance(resources[0], tuple):
		# Header row
		if resource_str == "APPs":
			worksheet_resources.write(row, col, 'App Name')
			worksheet_resources.write(row, col + 1, 'Created By')
			worksheet_resources.write(row, col + 2, 'Credentials')
		else:
			worksheet_resources.write(row, col, resource_str.rstrip('s') + ' Name')
			worksheet_resources.write(row, col + 1, 'Created By')
		row += 1
		# Data rows
		for resource_data in resources:
			if resource_str == "APPs" and len(resource_data) == 3:
				resource_name, created_by, credentials = resource_data
				worksheet_resources.write(row, col, resource_name)
				worksheet_resources.write(row, col + 1, created_by)
				worksheet_resources.write(row, col + 2, credentials)
			else:
				resource_name, created_by = resource_data
				worksheet_resources.write(row, col, resource_name)
				worksheet_resources.write(row, col + 1, created_by)
			row += 1
	else:
		for resource in resources:
			worksheet_resources.write(row, col, resource)
			row += 1
				
with open("config/app_config.json") as json_data_file:
    data = json.load(json_data_file)
    json_data_file.close()

apigee_edge_env= data["apigee_edge_env"]
folder_name= data["folder_name"]

index_of_tuple=0
index_of_tuple_sf=0
if os.path.exists("reports/source_org_assesment_report.xlsx"):
  os.remove("reports/source_org_assesment_report.xlsx")

### Name of output file 
workbook = xlsxwriter.Workbook('reports/source_org_assesment_report.xlsx')

proxy_path=folder_name+"\\proxies"
proxy_names_arr = os.listdir(proxy_path)
proxy_names_with_created_by =[]
for filename in proxy_names_arr:
    file_name_without_zip = re.search(r'(.*?)\.zip', filename)
    if file_name_without_zip:
        proxy_name = file_name_without_zip.group(1)
        # Extract proxy from zip to get metadata
        created_by = "Unknown"
        temp_extract_path = folder_name+"\\temp_"+proxy_name
        if not os.path.exists(temp_extract_path):
            with zipfile.ZipFile(proxy_path+"\\"+filename, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_path)
        proxy_xml_path = temp_extract_path+"\\apiproxy\\"+proxy_name+".xml"
        if os.path.exists(proxy_xml_path):
            with open(proxy_xml_path, 'r') as proxy_file:
                proxy_content = proxy_file.read()
                created_match = re.search(r'<CreatedBy>(.*?)</CreatedBy>', proxy_content)
                if created_match:
                    created_by = created_match.group(1).strip()
        proxy_names_with_created_by.append((proxy_name, created_by))
        # Clean up temp directory
        if os.path.exists(temp_extract_path):
            shutil.rmtree(temp_extract_path)
add_new_sheet(proxy_names_with_created_by,"Proxies")
print(f"Processed {len(proxy_names_with_created_by)} proxies")

sf_path=folder_name+"\\sharedflows"
sf_names_arr = os.listdir(sf_path)
sf_names_with_created_by =[]
for filename in sf_names_arr:
    file_name_without_zip = re.search(r'(.*?)\.zip', filename)
    if file_name_without_zip:
        sf_name = file_name_without_zip.group(1)
        created_by = "Unknown"
        temp_extract_path = folder_name+"\\temp_sf_"+sf_name
        if not os.path.exists(temp_extract_path):
            with zipfile.ZipFile(sf_path+"\\"+filename, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_path)
        sf_xml_path = temp_extract_path+"\\sharedflowbundle\\"+sf_name+".xml"
        if os.path.exists(sf_xml_path):
            with open(sf_xml_path, 'r') as sf_file:
                sf_content = sf_file.read()
                created_match = re.search(r'<CreatedBy>(.*?)</CreatedBy>', sf_content)
                if created_match:
                    created_by = created_match.group(1).strip()
        sf_names_with_created_by.append((sf_name, created_by))
        if os.path.exists(temp_extract_path):
            shutil.rmtree(temp_extract_path)
add_new_sheet(sf_names_with_created_by,"SharedFlows")
print(f"Processed {len(sf_names_with_created_by)} shared flows")

kvm_encryption_tuples = ()
lst_of_tuple_kvm = list(kvm_encryption_tuples)
lst_of_tuple_kvm.insert(0,["KVM", "Created By", "Encrypted"])


kmv_path=folder_name+"\\keyvaluemaps\\env\\"+apigee_edge_env
kvm_names_arr = os.listdir(kmv_path)
kvm_names = []
for kvm in kvm_names_arr:
	list_kvm_dependency_map=[]
	f = open(kmv_path+"\\"+kvm)
	data = json.load(f)
	is_encrypted = data['encrypted']
	created_by = data.get('createdBy', 'Unknown')
	list_kvm_dependency_map.append(kvm)
	list_kvm_dependency_map.append(created_by)
	list_kvm_dependency_map.append(is_encrypted)
	lst_of_tuple_kvm.insert(1,list_kvm_dependency_map)
final_kvm_dependency_map = tuple(lst_of_tuple_kvm)
worksheet = workbook.add_worksheet("KVMs")
row = 0
col = 0
for kvm,created_by,encrypted in (final_kvm_dependency_map):
    worksheet.write(row, col, kvm)
    worksheet.write(row, col + 1, created_by)
    worksheet.write(row, col + 2, encrypted)
    row += 1

#add_new_sheet(kvm_names_arr,"KVMs")

ts_path=folder_name+"\\targetservers\\env\\"+apigee_edge_env
ts_names_arr = os.listdir(ts_path)
ts_names_with_created_by = []
for ts_file in ts_names_arr:
	f = open(ts_path+"\\"+ts_file)
	data = json.load(f)
	created_by = data.get('createdBy', 'Unknown')
	f.close()
	ts_names_with_created_by.append((ts_file, created_by))
add_new_sheet(ts_names_with_created_by,"Target Servers")
print(f"Processed {len(ts_names_with_created_by)} target servers")

product_path=folder_name+"\\apiproducts"
prod_names_arr = os.listdir(product_path)
prod_names_with_created_by = []
for prod in prod_names_arr:
	f = open(product_path+"\\"+prod)
	data = json.load(f)
	created_by = data.get('createdBy', 'Unknown')
	prod_attributes = data['attributes']
	no_of_custom_attributes = len(prod_attributes)
	f.close()
	if no_of_custom_attributes > 16:
		prod_names_with_created_by.append((" Product " +prod+" has more than 14 custom attributes", created_by))
	else:
		prod_names_with_created_by.append((prod, created_by))
add_new_sheet(prod_names_with_created_by,"Products")
print(f"Processed {len(prod_names_with_created_by)} products")

apps_path=folder_name+"\\apps"
app_names_arr = os.listdir(apps_path)
app_names_with_created_by = []
for app in app_names_arr:
	f = open(apps_path+"\\"+app)
	data = json.load(f)
	app_name = data['name']
	created_by = data.get('createdBy', 'Unknown')
	app_attributes = data['attributes']
	no_of_custom_attributes = len(app_attributes)
	# Extract credentials
	credentials = data.get('credentials', [])
	credential_keys = []
	for cred in credentials:
		if 'consumerKey' in cred:
			credential_keys.append(cred['consumerKey'])
	credentials_str = ', '.join(credential_keys) if credential_keys else 'No Credentials'
	f.close()
	if no_of_custom_attributes > 16:
		app_names_with_created_by.append((" APP " +app_name+" has more than 14 custom attributes", created_by, credentials_str))
	else:
		app_names_with_created_by.append((app_name, created_by, credentials_str))
add_new_sheet(app_names_with_created_by,"APPs")
print(f"Processed {len(app_names_with_created_by)} apps")

policies_to_refractor = ''
policies_oauth_v1 = ''

sf_dependency_map=''



proxy_dependency_tuples = ()
lst_of_tuple_proxy = list(proxy_dependency_tuples)
lst_of_tuple_proxy.insert(0,["Proxy Name", "Created By", "Dependant Shared Flow", "Dependent KVM","Encrypted","Dependent TS"])


sf_dependency_tuples = ()
lst_of_tuple_sf = list(sf_dependency_tuples)
lst_of_tuple_sf.insert(0,["Shared Flow Name", "Dependant Shared Flow", "Dependent KVM","Encrypted"])

filenames = os.listdir(folder_name+"\\proxies")
############################## Unzips Proxies ################################################
for filename in filenames:
	check_whether_zip_file = re.search(r'\.(.*)', filename)
	if check_whether_zip_file:
		name_sc = check_whether_zip_file.group(1).strip()
		is_edge_micro_proxy = False
		filename = filename.strip()
		is_edge_micro_proxy_check = re.findall('(?i)edgemicro_', filename)
		is_edge_micro_proxy_check = str(is_edge_micro_proxy_check)
		if is_edge_micro_proxy_check != "[]":
			is_edge_micro_proxy = True
			filename = filename.replace(".zip",'')
			policies_oauth_v1=policies_oauth_v1+("Name of Edge Micro Proxy : "+filename+" |")+","
		
		filename = filename.replace(".zip",'')
		test=os.path.exists(folder_name+"\\proxies"+"\\"+filename)
		if test == False:
			filename = filename+".zip"
			with zipfile.ZipFile(folder_name+"\\proxies"+"\\"+filename, 'r') as zip_ref:
				filename = filename.replace(".zip",'')
				zip_ref.extractall(folder_name+"\\proxies"+"\\"+filename)

filenames = os.listdir(folder_name+"\\sharedflows")
############################## Unzips Shared Flows ################################################
for filename in filenames:
	check_whether_zip_file = re.search(r'\.(.*)', filename)
	if check_whether_zip_file:
		name_sc = check_whether_zip_file.group(1).strip()
		filename = filename.replace(".zip",'')
		test=os.path.exists(folder_name+"\\sharedflows"+"\\"+filename)
		if test == False:
			filename = filename+".zip"
			with zipfile.ZipFile(folder_name+"\\sharedflows"+"\\"+filename, 'r') as zip_ref:
				filename = filename.replace(".zip",'')
				zip_ref.extractall(folder_name+"\\sharedflows"+"\\"+filename)				

############################## Checks for SC policy Proxies ################################################
filenames = os.listdir(folder_name+"\\proxies")
print(f"Found files/directories in proxies folder: {filenames}")
for filename in filenames:
	
	check_whether_zip_file = re.search(r'\.(.*)', filename)
	dependent_sf=''
	dependent_kvm=''
	dependent_ts=''
	dependent_kvm_status=''

	print(f"Processing: {filename}, is_directory: {os.path.isdir(folder_name+'\\proxies\\'+filename)}, has_extension: {check_whether_zip_file is not None}")
	if not check_whether_zip_file and os.path.isdir(folder_name+"\\proxies\\"+filename):
		print(f"Processing proxy dependency for: {filename}")
		
		# Get proxy metadata for Created By
		created_by = "Unknown"
		proxy_xml_path = folder_name+"\\proxies\\"+filename+"\\apiproxy\\"+filename+".xml"
		if os.path.exists(proxy_xml_path):
			with open(proxy_xml_path, 'r') as proxy_file:
				proxy_content = proxy_file.read()
				created_match = re.search(r'<CreatedBy>(.*?)</CreatedBy>', proxy_content)
				if created_match:
					created_by = created_match.group(1).strip()	
		isdir_target = os.path.isdir(folder_name+"\\proxies\\"+filename+"\\apiproxy\\targets\\")
		if isdir_target:
			################################## Target Endpoints #########################################		
			isdir_check_mutiple_endpoints = os.path.isdir(folder_name+"\\proxies\\"+filename+"\\apiproxy\\targets\\")
			if isdir_check_mutiple_endpoints:
				arr_proxy_endpoints = os.listdir(folder_name+"\\proxies\\"+filename+"\\apiproxy\\targets\\")
				for i in arr_proxy_endpoints:
					file2 = open(folder_name+"\\proxies\\"+filename+"\\apiproxy\\targets\\"+i, 'r')
					lines = file2.readlines()
					file2.close()
					for line in lines:
						result_check_ts = re.search(r'<Server.*name="(.*?)"', line)		
						if result_check_ts:
							name_ts = result_check_ts.group(1).strip()
							proxy_name_include_sc = filename.strip()
							dependent_ts=dependent_ts+name_ts+","
		
		isdir = os.path.isdir(folder_name+"\\proxies\\"+filename+"\\apiproxy\\policies\\")

		if isdir:
			################################## Proxy Endpoints #########################################
			isdir_check_mutiple_endpoints = os.path.isdir(folder_name+"\\proxies\\"+filename+"\\apiproxy\\proxies\\")
			if isdir_check_mutiple_endpoints:
				arr_proxy_endpoints = os.listdir(folder_name+"\\proxies\\"+filename+"\\apiproxy\\proxies\\")
				length_of_proxy_endpoints = len(arr_proxy_endpoints)
				if length_of_proxy_endpoints >5:
					policies_oauth_v1=policies_oauth_v1+("Name of Proxy with more than 5 proxy endpoints : "+filename+"|")+","


						
				length_of_target_endpoints = len(arr_proxy_endpoints)
				if length_of_target_endpoints >1000:
					policies_oauth_v1=policies_oauth_v1+("Name of Proxy with more than 5 target endpoints : "+filename+"|")+","



			if os.path.exists(folder_name+"\\proxies\\"+filename+"\\apiproxy\\policies\\"):
				arr = os.listdir(folder_name+"\\proxies\\"+filename+"\\apiproxy\\policies\\")
			else:
				print(f"No policies directory found for {filename}")
				arr = []
			for i in arr:
				file2 = open(folder_name+"\\proxies\\"+filename+"\\apiproxy\\policies\\"+i, 'r')
				lines = file2.readlines()
				file2.close()
				for line in lines:
					result_check_sc = re.search(r'<StatisticsCollector.*name="(.*?)"', line)
					result_check_oauth_v1_policy = re.search(r'<OAuthV1.*name="(.*?)"', line)
					result_check_extensions_policy = re.search(r'<ConnectorCallout.*name="(.*?)"', line)
					result_check_sf = re.search(r'<FlowCallout.*name="(.*?)"', line)
					result_check_kvm = re.search(r'<KeyValueMapOperations.*mapIdentifier="(.*?)"', line)
					#result_check_ts = re.search(r'<Server.*name="(.*?)"', line)
					
					if result_check_extensions_policy:
						name_extensions = result_check_extensions_policy.group(1).strip()
						proxy_name_include_sc = filename.strip()
						policies_oauth_v1=policies_oauth_v1+("Name of Extension Policy : "+name_extensions+" and Name of Proxy: "+proxy_name_include_sc+"|")+","

					if result_check_oauth_v1_policy:
						name_ov1=result_check_oauth_v1_policy.group(1).strip()
						proxy_name_include_sc = filename.strip()
						policies_oauth_v1=policies_oauth_v1+("Name of OAuth v1 Policy : "+name_ov1+" and Name of proxy : "+proxy_name_include_sc+"|")+","
						
					if result_check_sc:
						name_sc = result_check_sc.group(1).strip()
						proxy_name_include_sc = filename.strip()
						policies_to_refractor=policies_to_refractor+("Name of Statistic Collector Policy : "+name_sc+" and Name of proxy : "+proxy_name_include_sc+"|")+","

					if result_check_sf:
						name_sf = result_check_sf.group(1).strip()
						proxy_name_include_sc = filename.strip()
						dependent_sf=dependent_sf+name_sf+","
	
					if result_check_kvm:
						name_kvm = result_check_kvm.group(1).strip()
						proxy_name_include_sc = filename.strip()
						
						isfile=os.path.isfile(folder_name+"\\keyvaluemaps\\env\\"+apigee_edge_env+"\\"+name_kvm)
						if isfile:
							file2 = open(folder_name+"\\keyvaluemaps\\env\\"+apigee_edge_env+"\\"+name_kvm, 'r')
							data = json.load(file2)
							encrypted_status = data['encrypted']
							file2.close()
							dependent_kvm_status=dependent_kvm_status+str(encrypted_status)+","
						else:
							dependent_kvm_status=dependent_kvm_status+"KVM does not exists in data_edge folder"+","	
						dependent_kvm=dependent_kvm+name_kvm+","



						#print("Proxy Name"+filename+"dependant shared flow " +name_sf)

		# Set default values for empty dependencies
		if dependent_sf == '':
			dependent_sf = "No Dependant Shared Flow"			

		if dependent_kvm == '':
			dependent_kvm = "No Dependant KVM"
			dependent_kvm_status = "NA"

		if dependent_ts == '':
			dependent_ts = "No Dependant TS"
		
		# Clean up comma-separated values
		dependent_sf=dependent_sf.strip(",")
		dependent_kvm=dependent_kvm.strip(",")
		dependent_ts=dependent_ts.strip(",")
		dependent_kvm_status=dependent_kvm_status.strip(",")

		# Add this proxy to dependency report (only for directories, not zip files)
		list_proxy_dependency_map = []
		list_proxy_dependency_map.append(filename)
		list_proxy_dependency_map.append(created_by)
		list_proxy_dependency_map.append(dependent_sf)
		list_proxy_dependency_map.append(dependent_kvm)
		list_proxy_dependency_map.append(dependent_kvm_status)
		list_proxy_dependency_map.append(dependent_ts)
		index_of_tuple=index_of_tuple+1
		lst_of_tuple_proxy.insert(index_of_tuple,list_proxy_dependency_map)
		print(f"Added dependency data for proxy: {filename}")
			
############################## Checks for SC policy in Shared Flow ################################################
filenames = os.listdir(folder_name+"\\sharedflows")
for filename in filenames:
	check_whether_zip_file = re.search(r'\.(.*)', filename)
	dependent_sf=''
	dependent_kvm=''
	dependent_kvm_status=''


	if not check_whether_zip_file and os.path.isdir(folder_name+"\\sharedflows\\"+filename):
		isdir = os.path.isdir(folder_name+"\\sharedflows\\"+filename+"\\sharedflowbundle\\policies\\")
		if isdir:
			arr = os.listdir(folder_name+"\\sharedflows\\"+filename+"\\sharedflowbundle\\policies\\")
			for i in arr:
				list_sf_dependency_map = []
				file2 = open(folder_name+"\\sharedflows\\"+filename+"\\sharedflowbundle\\policies\\"+i, 'r')
				lines = file2.readlines()
				file2.close()
				for line in lines:
					result_check_sc = re.search(r'<StatisticsCollector.*name="(.*?)"', line)
					result_check_oauth_v1_policy = re.search(r'<OAuthV1.*name="(.*?)"', line)
					result_check_extensions_policy = re.search(r'<ConnectorCallout.*name="(.*?)"', line)
					result_check_sf = re.search(r'<FlowCallout.*name="(.*?)"', line)

					
					if result_check_extensions_policy:
						name_extensions = result_check_extensions_policy.group(1).strip()
						proxy_name_include_sc = filename.strip()
						policies_oauth_v1=policies_oauth_v1+("Name of Extension Policy : "+name_extensions+" and Name of Shared Flow: "+proxy_name_include_sc+"|")+","	
						
					if result_check_oauth_v1_policy:
						name_ov1=result_check_oauth_v1_policy.group(1).strip()
						proxy_name_include_sc = filename.strip()
						policies_oauth_v1=policies_oauth_v1+("Name of OAuth v1 Policy : "+name_ov1+" and Name of Shared Flow : "+proxy_name_include_sc+"|")+","					
					
					if result_check_sc:
						name_sc = result_check_sc.group(1).strip()
						proxy_name_include_sc = filename.strip()
						policies_to_refractor=policies_to_refractor+("Name of Statistic Collector Policy : "+name_sc+" and Name of Shared Flow : "+proxy_name_include_sc+"|")+","
					
					if result_check_sf:
						name_sf = result_check_sf.group(1).strip()
						proxy_name_include_sc = filename.strip()
						dependent_sf=dependent_sf+name_sf+","

					if result_check_kvm:
						name_kvm = result_check_kvm.group(1).strip()
						proxy_name_include_sc = filename.strip()
						
						isfile=os.path.isfile(folder_name+"\\keyvaluemaps\\env\\"+apigee_edge_env+"\\"+name_kvm)
						if isfile:
							file2 = open(folder_name+"\\keyvaluemaps\\env\\"+apigee_edge_env+"\\"+name_kvm, 'r')
							data = json.load(file2)
							encrypted_status = data['encrypted']
							#print(encrypted_status)
							file2.close()
							dependent_kvm_status=dependent_kvm_status+str(encrypted_status)+","
						else:
							dependent_kvm_status=dependent_kvm_status+"KVM does not exists in data_edge folder"+","	
												
						dependent_kvm=dependent_kvm+name_kvm+","




			if dependent_sf == '':
				dependent_sf = "No Dependant Shared Flow"			

			if dependent_kvm == '':
				dependent_kvm = "No Dependant KVM"
				dependent_kvm_status = "NA"

			dependent_sf=dependent_sf.strip(",")
			dependent_kvm=dependent_kvm.strip(",")
			dependent_ts=dependent_ts.strip(",")
			sf_dependency_map = sf_dependency_map + "SF Name --> "+filename+" & Dependent SF --> " +dependent_sf+" & Dependent KVM --> " +dependent_kvm +" |"
			#print("SF Name --> "+filename+" Dependent SF --> " +dependent_sf+" Dependent KVM --> " +dependent_kvm)

			list_sf_dependency_map.append(filename)
			list_sf_dependency_map.append(dependent_sf)
			list_sf_dependency_map.append(dependent_kvm)
			list_sf_dependency_map.append(dependent_kvm_status)
			index_of_tuple_sf=index_of_tuple_sf+1
			lst_of_tuple_sf.insert(index_of_tuple_sf,list_sf_dependency_map)

string_to_list_of_refractored=policies_to_refractor.split(",")
add_new_sheet(string_to_list_of_refractored,"Policies to Refractor")

string_to_list_of_oauth_v1=policies_oauth_v1.split(",")
add_new_sheet(string_to_list_of_oauth_v1,"Deprecated Policies")

##################### Dependency Map Proxy ######################
final_proxy_dependency_map = tuple(lst_of_tuple_proxy)
worksheet = workbook.add_worksheet("Proxy_Dependency_Map")
row = 0
col = 0
for proxy_name,created_by,shared_flow,kvm,encrypted,ts in (final_proxy_dependency_map):
    worksheet.write(row, col, proxy_name)
    worksheet.write(row, col + 1, created_by)
    worksheet.write(row, col + 2, shared_flow)
    worksheet.write(row, col + 3, kvm)
    worksheet.write(row, col + 4, encrypted)
    worksheet.write(row, col + 5, ts)
    row += 1


##################### Dependency Map SF ######################
final_sf_dependency_map = tuple(lst_of_tuple_sf)
worksheet = workbook.add_worksheet("SF_Dependency_Ma")
row = 0
col = 0
for shared_flow,dependent_sf,dependent_kvm,encrypted in (final_sf_dependency_map):
    worksheet.write(row, col, shared_flow)
    worksheet.write(row, col + 1, dependent_sf)
    worksheet.write(row, col + 2, dependent_kvm)
    worksheet.write(row, col + 3, encrypted)
    row += 1


#add_new_sheet(kvm_names_arr,"KVMs")
workbook.close()
print("\n=== Source Assessment Report Generated Successfully ===")
print(f"Report saved to: reports/source_org_assesment_report.xlsx")
print(f"Total Proxies processed: {len(proxy_names_with_created_by)}")
print(f"Total SharedFlows processed: {len(sf_names_with_created_by)}")
print(f"Total KVMs processed: {len(kvm_names_arr)}")
print(f"Total Target Servers processed: {len(ts_names_with_created_by)}")
print(f"Total Products processed: {len(prod_names_with_created_by)}")
print(f"Total Apps processed: {len(app_names_with_created_by)}")
print(f"Total Proxy Dependencies processed: {len(lst_of_tuple_proxy)-1}")
print(f"Total SharedFlow Dependencies processed: {len(lst_of_tuple_sf)-1}")
print("Report generation completed!")
