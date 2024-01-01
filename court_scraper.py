import requests
from bs4 import BeautifulSoup
from selenium import webdriver
#from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
#from selenium.webdriver.support.ui import WebDriverWait
#from selenium.webdriver.support import expected_conditions as EC
import time
import random
from io import BytesIO
import pytesseract
from PIL import Image
import pandas as pd
from datetime import datetime
import re
import asyncio


case_numbers = None
street_addresses = None
def set_duplicate_checker():
	global case_numbers, street_addresses, df
	#Change for Docker
	df = pd.read_excel('/Users/alexheeb/Documents/Court_Scraper/excel_files/MasterData.xlsx')
	case_numbers = df['case_number'].tolist()
	street_addresses = df['street'].tolist()

def get_casenumber_from_href(href):
	return href.split('case_id=')[1].split('&begin')[0]

#Sample docket for testing
#driver.get("https://caseinfo.arcourts.gov/cconnect/PROD/public/ck_public_qry_doct.cp_dktrpt_frames?backto=F&case_id=60CR-23-3729&begin_date=&end_date=")

# Set the path to the Chrome WebDriver executable
#Change for Docker
webdriver_path = "/Users/alexheeb/Downloads/chromedriver-mac-arm64/chromedriver"

# Initialize Chrome WebDriver
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": "/path/to/save/pdf",
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "plugins.plugins_disabled": ["Chrome PDF Viewer"],
    "download.prompt_for_download": False,
    'plugins.always_open_pdf_externally': False
})

#Comment out three lines below to launch browser GUI
#chrome_options.add_argument("--window-size=1920,1080")
#chrome_options.add_argument("--headless")
#chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

service = ChromeService(executable_path=webdriver_path)

driver = webdriver.Chrome(service=service, options=chrome_options)

#Change for Docker
image_path = '/Users/alexheeb/Documents/Court_Scraper/screenshots/screenshot.png'

def get_earliest_date():
    global filing_date
    pattern = r"\b\d{2}/\d{2}/\d{4}\b"
    dates = []
    for item in driver.find_elements(By.TAG_NAME, "td"):
        match = re.search(pattern, item.text)
        if match:
            # Convert the found date string to a datetime object
            date_obj = datetime.strptime(match.group(), '%m/%d/%Y')
            dates.append(date_obj)
    if dates:
        filing_date = min(dates)  # Find the earliest date
    else:
        pass

def get_full_docket_link(href):
	return f"https://caseinfo.arcourts.gov/cconnect/PROD/public/{href}"


async def get_pdf(href):
    global tripwire
    tripwire = False
    driver.get(get_full_docket_link(href))
    pdf_link = None  # Initialize pdf_link
    try:
        # Find data frame
        frame = driver.find_element(By.NAME, "main")
        # Switch to frame
        driver.switch_to.frame(frame)
        get_earliest_date()
        # Initialize tripewire variable
        for item in driver.find_elements(By.TAG_NAME, "td"):
            if "NOTICE HEARING SCHEDULED" in item.text:
                tripwire = True
            if tripwire and len(item.find_elements(By.TAG_NAME, "a")) > 0:
                pdf_link = item.find_element(By.TAG_NAME, "a").get_attribute("href")
                break
        if tripwire == False:
        	return False
        if pdf_link:  # Check if pdf_link is not None
            driver.get(pdf_link)
            time.sleep(random.randint(10, 25))
            driver.save_screenshot(image_path)
            return True
    except Exception as e:
        print("An error occurred:", e)


def extract_text():
    img = Image.open(image_path)
    text = pytesseract.image_to_string(image_path)
    return [x for x in text.split('\n') if x != '']


def extract_address_details(ocr_text, href):
    global final_data
    final_data = {'case_number': get_casenumber_from_href(href), 'filing_date': None, 'first_name': None, 'last_name': None, 'street': None, 'city': None, 'state': None, 'zipcode': None, 'link': None}
    city_state_zip_regex = re.compile(r',\s[A-Z]{2}\s\d{5}$')  # Matches ', STATE ZIP'
    room_regex = re.compile(r'\broom\b', re.IGNORECASE)
    apt_regex = re.compile(r'\bapt\b', re.IGNORECASE)
    address_regex = re.compile(r'\d+\s[A-Za-z\s,.]+')  # Matches street address    
    for i in range(1, len(ocr_text)):
        if city_state_zip_regex.search(ocr_text[i]):
            # Check for 'Room' in the preceding string
            if room_regex.search(ocr_text[i - 1]):
                continue
            # Check for 'Apt' in the preceding string
            if apt_regex.search(ocr_text[i - 1]):
                # Check if the string also contains a street address
                if address_regex.search(ocr_text[i - 1]):
                    # Street address with apartment
                    address = ocr_text[i - 1]
                    name = ocr_text[i - 2] if i >= 2 else None
                else:
                    # Apartment number, separate street address
                    apt = ocr_text[i - 1]
                    address = ocr_text[i - 2] + ', ' + apt if i >= 2 else apt
                    name = ocr_text[i - 3] if i >= 3 else None
            else:
                # Street address without apartment
                address = ocr_text[i - 1]
                name = ocr_text[i - 2] if i >= 2 else None            
            city_state_zip = ocr_text[i]
            if name:
                final_data['first_name'] = name.split(' ')[0]
                final_data['last_name'] = ' '.join(name.split(' ')[1:])
            if address:
                final_data['street'] = address
            if city_state_zip:				
                final_data['city'] = city_state_zip.split(',')[0]
                final_data['state'] = city_state_zip.split(' ')[-2]
                final_data['zipcode'] = city_state_zip.split(' ')[-1]
            final_data['filing_date'] = filing_date
            final_data['case_number'] = get_casenumber_from_href(href)
            final_data['link'] = get_full_docket_link(href)
            print(final_data)
            return final_data
    return None

# Global variable declaration
filtered_final_data = []
def check_for_duplicate_addresses(data):
	global filtered_final_data
	for item in data:
		try:
			if item['street'] not in street_addresses:
				filtered_final_data.append(item)
			else:
				print("Skipping duplicate address")
		except:
			print("Skipping non-valid PDF")

def save_data_to_files():
	final_data_df = pd.DataFrame(filtered_final_data)
	#Change for Docker
	final_data_df.to_excel('/Users/alexheeb/Documents/Court_Scraper/excel_files/DataForMailers.xlsx', index=False)
	updated_master_df = pd.concat([df, final_data_df])
# 	#Change for Docker
	updated_master_df.to_excel('/Users/alexheeb/Documents/Court_Scraper/excel_files/MasterData.xlsx', index=False)

all_dockets = []

async def main(quantity, hrefs_to_scrape):
    global all_dockets  # Declare that all_dockets is a global variable
    for index in range(quantity):
        print(' ')
        print(f"Scraping docket {index + 1}/{quantity}")
        print(get_casenumber_from_href(hrefs_to_scrape[index]))
        status = await get_pdf(hrefs_to_scrape[index])
        if status == False:
        	print("Skipping case as 'NOTICE HEARING SCHEDULED' not found.")
        	continue
        ocr_text = extract_text()
        docket_data = extract_address_details(ocr_text, hrefs_to_scrape[index])
        if docket_data == None:
        	continue
        all_dockets.append(docket_data)


#Make sure below is uncommented before production
print("Enter start date for dockets below")
print("Date must be in format 09/10/2023")
start_date = input()
print("Enter end date for dockets below")
print("Date must be in format 09/10/2023")
end_date = input()

#Comment these out before production
# start_date = "09/14/2023"
# end_date = "09/14/2023"

search_string = f"https://caseinfo.arcourts.gov/cconnect/PROD/public/ck_public_qry_doct.cp_dktrpt_new_case_report?backto=C&case_id=&begin_date={start_date}&end_date={end_date}&county_code=60%20-%20PULASKI&cort_code=ALL&locn_code=CI%20-%20CIRCUIT&case_type=DI%20-%20FELONY&docket_code="
get_response = requests.get(search_string)

soup = BeautifulSoup(get_response.content, 'html.parser')
td_tags = soup.find_all('td')

href_values = []
for element in td_tags:
    a = element.find('a')
    if a:
        href_values.append(a.get('href'))

set_duplicate_checker()

hrefs_to_scrape = []
for href in href_values:
	if get_casenumber_from_href(href) not in case_numbers:
		hrefs_to_scrape.append(href)

quantity = len(hrefs_to_scrape)

print(f"Beginning scrape: {quantity} dockets")

all_dockets = []
index = 0
asyncio.run(main(quantity, hrefs_to_scrape))

check_for_duplicate_addresses(all_dockets)
driver.quit()
save_data_to_files()
print(' ')
print("Scraping job complete")
print("Excel file saved to disk")
quit()


