# Google-Maps-Scrapper
This Python script utilizes the Playwright library to perform web scraping and data extraction from Google Maps. It is particularly designed for obtaining information about businesses, including their name, address, website, phone number, reviews, and more.
## Table of Contents

- [Prerequisite](#prerequisite)
- [Key Features](#key-features)
- [Installation](#installation)
- [How to Use](#how-to-use)

## Prerequisite
- This code requires a python version below 3.10
- Any version of python beyond 3.9 may cause issues and may not work properly

## Key Features
- Data Scraping: The script scrapes data from Google Maps listings, extracting valuable information about businesses, such as their name, address, website, and contact details.

- Review Analysis: It extracts review counts and average ratings, providing insights into businesses' online reputation.

- Business Type Detection: The script identifies whether a business offers in-store shopping, in-store pickup, or delivery services.

- Operating Hours: It extracts information about the business's operating hours.

- Introduction Extraction: The script also scrapes introductory information about the businesses when available.

- Data Cleansing: It cleanses and organizes the scraped data, removing redundant or unnecessary columns.

- CSV Export: The cleaned data is exported to a CSV file for further analysis or integration with other tools.

## Installation

1. Clone this repository:

   ```bash
   git clone git@github.com-personal:dilawaizkhan08/Google_Maps_Scraper.git
2. Navigate to the project directory:
   ```bash
   cd Google_Maps-Scrapper

3. 3. Set up a virtual environment (optional but recommended):
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

4. Install the required Python packages:
    ```bash
    pip install -r requirements.txt

## How to Use:

To use this script, follow these steps:

1. Run the script with Python:
    ```bash
     python main.py
    ```
2. The script will launch a browser, perform the search, and start scraping information. It will display the progress and save the results to a CSV file called result.csv.
