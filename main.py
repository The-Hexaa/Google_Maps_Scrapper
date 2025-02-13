from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from playwright.sync_api import sync_playwright
import pandas as pd
import os
from groq import Groq
from flask_cors import CORS
import requests
import time
from dotenv import load_dotenv
import psycopg2
import logging
from psycopg2 import sql
from model import db, User  # Import db and User model from model.py
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import json

# Load environment variables from the .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Load configuration from environment variables
app.config['SESSION_TYPE'] = 'filesystem'
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
CORS(app)

# Database configuration
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')


print(f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}')
# Construct the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy with the app
db.init_app(app)

# Ensure tables are created
with app.app_context():
    db.create_all()

criteria_F = "" 
question_F = ""
filtered_options_cache = None  # Global cache for best options

def extract_data(xpath, data_list, page, timeout=5000):
    try:
        if page.locator(xpath).count() > 0:
            data = page.locator(xpath).inner_text(timeout=timeout)
            data_list.append(data)
        else:
            data_list.append("N/A")  # Default value if element is missing
    except Exception as e:
        print(f"Skipping element at {xpath} due to timeout/error: {e}")
        data_list.append("N/A")  # Default value if data can't be fetched

def scrape_data(search_for, customer_number, total=10):
    names_list, address_list, website_list, phones_list = [], [], [], []
    reviews_c_list, reviews_a_list = [], []
    store_s_list, in_store_list, store_del_list = [], [], []
    place_t_list, open_list, intro_list = [], [], []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            print(f"Info: Browser launched for scraping.")

            try:
                page.goto("https://www.google.com/maps")
                page.wait_for_selector('//input[@id="searchboxinput"]')
                print(f"Info: Page loaded and search box found.")
            except Exception as e:
                print(f"Error loading the page or waiting for selector: {e}")
                return None

            page.locator('//input[@id="searchboxinput"]').fill(search_for)
            page.keyboard.press("Enter")
            page.wait_for_selector('//a[contains(@href, "https://www.google.com/maps/place")]')
            print(f"Info: Search term '{search_for}' entered and search started.")

            previously_counted = 0
            listings = []

            while True:
                page.mouse.wheel(0, 1000000)
                page.wait_for_selector('//a[contains(@href, "https://www.google.com/maps/place")]')

                if page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count() >= total:
                    listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()[:total]
                    listings = [listing.locator("xpath=..") for listing in listings]
                    print(f"Info: Retrieved {len(listings)} listings.")
                    break
                else:
                    current_count = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count()
                    if current_count == previously_counted:
                        listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()
                        print(f"Info: No more listings found. Retrieved {len(listings)} listings.")
                        break
                    previously_counted = current_count

            for listing in listings:
                try:
                    listing.click()
                    page.wait_for_selector('//div[@class="TIHn2 "]//h1[@class="DUwDvf lfPIob"]')

                    # Extract data for each field
                    extract_data('//div[@class="TIHn2 "]//h1[@class="DUwDvf lfPIob"]', names_list, page)
                    extract_data('//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]', address_list, page)
                    extract_data('//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]', website_list, page)
                    extract_data('//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]', phones_list, page)
                    extract_data('//div[@class="LBgpqf"]//button[@class="DkEaL "]', place_t_list, page)
                    extract_data('//div[@class="WeS02d fontBodyMedium"]//div[@class="PYvSYb "]', intro_list, page)

                    # Safe extraction for specific elements
                    try:
                        reviews_count = page.locator('//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span//span//span[@aria-label]').inner_text(timeout=5000) if page.locator('//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span//span//span[@aria-label]').count() > 0 else ""
                        reviews_c_list.append(reviews_count.replace('(', '').replace(')', '').replace(',', ''))

                        reviews_average = page.locator('//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span[@aria-hidden]').inner_text(timeout=5000) if page.locator('//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span[@aria-hidden]').count() > 0 else ""
                        reviews_a_list.append(reviews_average.replace(' ', '').replace(',', '.'))

                        store_s_list.append("Yes" if 'shop' in page.locator('//div[@class="LTs0Rc"][1]').inner_text(timeout=5000) else "No")
                        in_store_list.append("Yes" if 'pickup' in page.locator('//div[@class="LTs0Rc"][1]').inner_text(timeout=5000) else "No")
                        store_del_list.append("Yes" if 'delivery' in page.locator('//div[@class="LTs0Rc"][1]').inner_text(timeout=5000) else "No")
                    except Exception as e:
                        print(f"Error extracting store information: {e}")
                        store_s_list.append("No")
                        in_store_list.append("No")
                        store_del_list.append("No")

                    opening_time = page.locator('//button[contains(@data-item-id, "oh")]//div[contains(@class, "fontBodyMedium")]').inner_text(timeout=5000) if page.locator('//button[contains(@data-item-id, "oh")]//div[contains(@class, "fontBodyMedium")]').count() > 0 else ""
                    open_list.append(opening_time)

                except Exception as e:
                    print(f"Error processing listing: {e}")

            # DataFrame construction and CSV output
            df = pd.DataFrame({
                'Names': names_list, 'Website': website_list, 'Introduction': intro_list,
                'Phone Number': phones_list, 'Address': address_list, 'Review Count': reviews_c_list,
                'Average Review Count': reviews_a_list, 'Store Shopping': store_s_list,
                'In Store Pickup': in_store_list, 'Delivery': store_del_list,
                'Type': place_t_list, 'Opens At': open_list
            })

            # Add Questions, Answers, and "Meet Criteria" columns
            df['Questions'] = ""  # Initialize empty column
            df['Answers'] = ""    # Initialize empty column
            df['Meet Criteria'] = False  # Add new column, set to False for all rows
            df['Questions'] = df['Questions'].astype(str)
            df['Answers'] = df['Answers'].astype(str)

            # Add demo business row
            demo_row = {
                'Names': 'Demo Business',
                'Website': 'N/A',
                'Introduction': 'Demo Introduction',
                'Phone Number': customer_number,
                'Address': 'Demo Address',
                'Review Count': 'N/A',
                'Average Review Count': 'N/A',
                'Store Shopping': 'N/A',
                'In Store Pickup': 'N/A',
                'Delivery': 'N/A',
                'Type': 'N/A',
                'Opens At': 'N/A',
                'Questions': 'N/A',
                'Answers': 'N/A',
                'Meet Criteria': False  # Add Meet Criteria to demo row
            }
            df = pd.concat([pd.DataFrame([demo_row]), df], ignore_index=True)

            df.drop_duplicates(subset=['Names', 'Phone Number', 'Address'], inplace=True)
            df.dropna(axis=1, how='all', inplace=True)
            df.to_csv('result.csv', index=False)

            print(f"CSV file generated at: result.csv")
            print("CSV file contents:")
            print(df.to_string(index=False))

            browser.close()
            return df

    except Exception as e:
        print(f"Error during scraping: {e}")
        return None

@app.route('/submit-twilio-config', methods=['POST'])
def submit_twilio_config():
    try:
        data = request.get_json()  # Get JSON data from the request
        twilio_account_sid = data.get('twilioAccountSid')
        twilio_auth_token = data.get('twilioAuthToken')
        twilio_phone_number = data.get('twilioPhoneNumber')
        customer_number = data.get('customerPhoneNumber')

        # Validate the data (optional)
        if not (twilio_account_sid and twilio_auth_token and twilio_phone_number):
            return jsonify({'message': 'All fields are required!'}), 400

        # Store the configuration in the session
        session['twilio_config'] = {
            "twilioAccountSid": twilio_account_sid,
            "twilioAuthToken": twilio_auth_token,
            "twilioPhoneNumber": twilio_phone_number,
            "customerPhoneNumber": customer_number
        }

        # Redirect to the query page after successful submission
        return redirect(url_for('query'))  # Redirect to the 'query' route

    except Exception as e:
        # Handle exceptions and display error
        return render_template('twilio.html', error="Invalid credentials")

@app.before_request
def log_request():
    print(f"Request: {request.method} {request.url}")

def check_required_criteria(question, answer):
    # # Get the criteria from the session
    # print(f"Session in check_required_criteria: {session}")
    # query_config = session.get('query')
    # if not query_config:
    #     print("Error: Query configuration not found in session.")
    #     return jsonify({"error": "Query configuration is missing"}), 500
    global criteria_F
    try:
        print("criteria_F: ", criteria_F)
    except:
        print("criteria_F: not found")
    
    criteria = criteria_F
    if not criteria:
        print("Error: Query criteria is missing in configuration.")
        return jsonify({"error": "Invalid Query configuration"}), 500

    try:
        # Initialize the Groq client with the API key from the environment
        client = Groq(
            api_key="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",
        )

        # Prepare the prompt for the Groq API
        prompt = (
            f"Question: {question}, Answer: {answer}, Criteria: {criteria}. "
            "Now you have to check if the answer meets the criteria or not. "
            "If it meets the criteria then return True, and if it doesn't meet the criteria then return False. "
            "Only return True or False, no need of other text."
        )

        # Get the chat completion from the Groq API
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
        )

        # Get the response from the Groq API
        response = chat_completion.choices[0].message.content.strip().lower()

        print("Response = ", response)

        # Check if the response contains any positive indication (like True, Yes)
        if any(keyword in response for keyword in ["true", "yes", "correct", "affirmative", "valid"]):
            return True
        else:
            return False

    except Exception as e:
        print(f"Error: Found issue in Groq: {e}")
        return jsonify({"error": "An error occurred while processing the criteria check"}), 500

@app.route("/webhook", methods=["POST", "GET"])
def webhook():

    if request.method == "GET":
        # Dummy response for testing
        return jsonify({
            "message": "GET request successful",
            "best_options": [{"Name": "Example", "Details": "Test data"}]
        })

    try:
        # Initialize variables for storing question and answer
        global question_F 
        global first_question
        answer = None

        # Use a global variable to store the first question
        if 'first_question' not in globals():
            first_question = None

        # Get the JSON data sent by VAPI
        webhook_data = request.get_json()

        if not webhook_data:
            return jsonify({"error": "No data received"}), 400

        # Extract relevant information
        call_status = webhook_data.get("message", {}).get("call", {}).get("status", None)
        transcription = webhook_data.get("message", {}).get("artifact", {}).get("transcript", None)
        event_type = webhook_data.get("message", {}).get("type", None)
        customer_number = webhook_data.get("message", {}).get("call", {}).get("customer", {}).get("number", None)

        # Log extracted values for debugging
        print(f"Extracted Values:\nCall Status: {call_status}\nTranscription: {transcription}\nEvent Type: {event_type}\nCustomer Number: {customer_number}")

        # Extract first question and answer from the transcript (if available)
        if transcription:
            lines = transcription.split("\n")  # Split transcript into lines
            for line in lines:
                if line.startswith("AI:") and first_question is None:
                    first_question = line[3:].strip()  # Save AI's first question
                elif line.startswith("User:") and first_question:  # Only save answer if there's a first question
                    answer = line[5:].strip()

        # Use a global or session-based variable to track conversation updates
        global conversation_update_count
        if 'conversation_update_count' not in globals():
            conversation_update_count = 0
            print("Conversatioin update count: ", conversation_update_count)

        # Handle 'Conversation Update' events
        if event_type == "speech-update":
            conversation_update_count += 1
            print(f"Conversation update count: {conversation_update_count}")

        # Handle call status changes
        if event_type in ["end-of-call-report", "disconnected"]:
            print(f"Call status received: {call_status}")
            print("Call completed or disconnected.")

            # Update the CSV file with the question and answer
            if first_question and answer:
                try:
                    # Load the existing CSV into a DataFrame
                    csv_file_path = "result.csv"
                    df = pd.read_csv(csv_file_path)

                    # Identify the row based on the phone number
                    if customer_number:
                        row_index = df.index[df['Phone Number'] == customer_number].tolist()
                        if row_index:

                            

                            # Ensure columns are of object dtype
                            df['Questions'] = df['Questions'].astype('object')
                            df['Answers'] = df['Answers'].astype('object')

                            # Update the Question and Answer columns for the matched row

                            df.at[row_index[0], 'Questions'] = question_F
                            df.at[row_index[0], 'Answers'] = answer
                            df.at[row_index[0], 'Meet Criteria'] = check_required_criteria(question_F, answer)

                            # Save the updated DataFrame back to the CSV
                            df.to_csv(csv_file_path, index=False)
                            print(f"CSV updated with question and answer for phone number {customer_number}")

                            # Call the display_best_options function to filter the DataFrame
                            best_options = display_best_options(df)

                            global filtered_options_cache
                            filtered_options_cache = best_options.to_dict(orient='records')

                            # Return the filtered options
                            return jsonify({
                                "message": "Call has been completed or disconnected.",
                                "best_options": filtered_options_cache
                            }), 200

                            
                        else:
                            print(f"No matching row found for phone number {customer_number}")
                    else:
                        print("Customer phone number not available in session.")

                except Exception as e:
                    print(f"Error updating CSV: {e}")
            else:
                print("No question or answer to update.")

            return jsonify({"message": "Call has been completed or disconnected."}), 200

        # Default response for unexpected scenarios
        return jsonify({"message": "Waiting for user response or other event."}), 200

    except Exception as e:
        print(f"Error handling webhook: {e}")
        return jsonify({"error": "Internal server error"}), 500

    finally:
        # Print the first question and last answer at the end
        print(f"Question: {first_question}")
        print(f"Answer: {answer}")
        # display_best_options()

def display_best_options(df):
    print("display_best_Options is called.")
    
    # Filter rows where 'meet criteria' is True
    filtered_df = df[df['Meet Criteria'] == True]
    
    # Optionally, reset the index for a clean output
    filtered_df = filtered_df.reset_index(drop=True)

    # Replace NaN values with "N/A" or "demo" in the entire dataframe
    filtered_df = filtered_df.fillna("N/A")
    
    print("filtered_df after replacing NaN with 'N/A':")
    print(filtered_df)
    
    return filtered_df

@app.route("/get-best-options", methods=["GET"])
def get_best_options():
    global filtered_options_cache
    if filtered_options_cache is not None:
        return jsonify(filtered_options_cache), 200
    return jsonify({"message": "No best options available"}), 404

@app.route("/make_call", methods=["POST"])
def make_call(phone_number, customer_number, message):
    try:
        # Get Twilio credentials from session
        twilio_config = session.get('twilio_config')
        
        if not twilio_config:
            return {"error": "Twilio configuration not found. Please submit the configuration first."}
        
        # Extract credentials from session
        twilio_account_sid = twilio_config.get('twilioAccountSid')
        twilio_auth_token = twilio_config.get('twilioAuthToken')
        twilio_phone_number = twilio_config.get('twilioPhoneNumber')
        customer_number = twilio_config.get('customerPhoneNumber')

        # VAPI API endpoint and request payload
        payload = {
            "assistantId": os.getenv("VAPI_ASSISTANT_ID"),  # Your Assistant ID
            "name": os.getenv("VAPI_ASSISTANT_NAME"),  # Your Assistant name
            "assistant": {
                "transcriber": {
                    "provider": os.getenv("VAPI_TRANSCRIBER_PROVIDER")  # Transcriber provider
                },
                "model": {
                    "provider": os.getenv("VAPI_MODEL_PROVIDER"),  # Model provider
                    "model": os.getenv("VAPI_MODEL_NAME"),  # Your model name
                    "systemPrompt": os.getenv("VAPI_SYSTEM_PROMPT")
                },
                "firstMessage": message,
                "endCallFunctionEnabled": True,
                "endCallMessage": "Thankyou, bye"
            },
            "phoneNumber": {
                "twilioAccountSid": twilio_account_sid,
                "twilioAuthToken": twilio_auth_token,
                "twilioPhoneNumber": twilio_phone_number,
            },
            "customer": {
                "number": customer_number  # Customer phone number
            },
        }

        headers = {
            "Authorization": f"Bearer {os.getenv('VAPI_BEARER_TOKEN')}",  # VAPI Bearer token
            "Content-Type": "application/json"
        }

        # Make the API call to VAPI
        response = requests.post("https://api.vapi.ai/call", json=payload, headers=headers)
        
        # Check for errors in the response
        response.raise_for_status()

        # Print full response for debugging
        # print(f"API Response: {response.json()}")

        # Extract the ID (used as session ID)
        session_id = response.json().get("id")
        if not session_id:
            print("Error: 'id' not found in the response.")
            return {"error": "'id' not found in the response."}
        
        print(f"Call initiated successfully. Session ID: {session_id}")

        # Return the session ID
        return {"session_id": session_id, "message": "Call initiated successfully."}
    
    except requests.exceptions.RequestException as e:
        print(f"Error making call to {phone_number}: {e}")
        return {"error": str(e)}


# Example usage:
# customer_number = "+923116805861"  # Customer's phone number
# result = make_call("+19083864875", customer_number)
# print(result)

# def call_all_numbers_from_csv(csv_path):
#     try:
#         df = pd.read_csv(csv_path)
#         if 'Phone Number' not in df.columns:
#             print("No phone numbers found in the CSV.")
#             return {"message": "No phone numbers found."}

#         # Loop through unique phone numbers and make calls
#         for number in df['Phone Number'].dropna().unique():
#             result = make_call("+19083864875", number)  # Adjust parameters as needed
#             print(f"Call result for {number}: {result}")
#             time.sleep(2)  # Add a delay between calls to avoid API rate limits
#     except Exception as e:
#         print(f"Error reading CSV or making calls: {e}")

# Function to establish a connection to the database
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print("Error connecting to the database:", e)
        return None

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/authenticateUser', methods=['POST'])
def authenticateUser():
    try:
        # Get username and password from the form
        username = request.form.get('username')  # Email is passed as 'username'
        password = request.form.get('password')

        print(f"Debug: Received login request. Username: {username}, Password: {'*' * len(password) if password else 'None'}")

        if not username or not password:
            print("Debug: Missing username or password.")
            return render_template('login.html', error="Both username and password are required.")

        # Establish a database connection
        try:
            conn = get_db_connection()
            print("Debug: Database connection established.")
        except Exception as e:
            print(f"Debug: Error connecting to database: {e}")
            return render_template('login.html', error="An error occurred while connecting to the database. Please try again.")

        try:
            with conn.cursor() as cur:
                # Query the database for the user
                try:
                    cur.execute(
                        """
                        SELECT * FROM users WHERE email = %s
                        """,
                        (username,)
                    )
                    user = cur.fetchone()
                    print(f"Debug: Query executed for username: {username}. Query result: {user}")
                except Exception as e:
                    print(f"Debug: Error executing query for username '{username}': {e}")
                    return render_template('login.html', error="An error occurred during authentication. Please try again.")

                if user:
                    try:
                        # Assuming the password is the 3rd column in the tuple
                        stored_password_hash = user[3]  # Update index if table schema differs
                        print(f"Debug: User record retrieved. Stored password hash: {stored_password_hash}")

                        # Verify the password
                        if check_password_hash(stored_password_hash, password):
                            session['username'] = username  # Set session data
                            print(f"Debug: User '{username}' successfully authenticated.")
                            return render_template('twilio.html')
                        else:
                            print(f"Debug: Password mismatch for user '{username}'.")
                            return render_template('login.html', error="Invalid credentials.")
                    except Exception as e:
                        print(f"Debug: Error during password validation for username '{username}': {e}")
                        return render_template('login.html', error="An error occurred during authentication.")
                else:
                    print(f"Debug: No user found with username '{username}'.")
                    return render_template('login.html', error="Invalid credentials.")
        except Exception as e:
            print(f"Debug: Error during database operations: {e}")
            return render_template('login.html', error="An error occurred while processing your request.")
        finally:
            # Ensure the database connection is closed
            try:
                conn.close()
                print("Debug: Database connection closed.")
            except Exception as e:
                print(f"Debug: Error while closing database connection: {e}")

    except Exception as e:
        print(f"Debug: Unexpected error in authenticateUser function: {e}")
        return render_template('login.html', error="An unexpected error occurred. Please try again.")

@app.route('/query', methods=['GET', 'POST'])
def query():
    try:
        global filtered_options_cache
        filtered_options_cache = None
        # Get Twilio configuration from the session
        twilio_config = session.get('twilio_config')
        if not twilio_config:
            print("Error: Twilio configuration not found in session.")
            return jsonify({"error": "Twilio configuration is missing"}), 500

        twilio_phone_number = twilio_config.get('twilioPhoneNumber')
        customer_number = twilio_config.get('customerPhoneNumber')
        if not twilio_phone_number or not customer_number:
            print("Error: Twilio phone number or customer phone number is missing in configuration.")
            return jsonify({"error": "Invalid Twilio configuration"}), 500

        # Check if user is logged in
        if 'username' not in session:
            print("Error: User not logged in.")
            return redirect(url_for('index'))  # Redirect to login if not logged in

        if request.method == 'POST':
            try:
                # Extract data from the POST request
                search_term = request.json.get('search_term')
                message = request.json.get('message')
                criteria = request.json.get('criteria')

                if not search_term:
                    print("Error: Search term is missing in POST request.")
                    return jsonify({"error": "Search term is required"}), 400

                if not message:
                    print("Error: Message is missing in POST request.")
                    return jsonify({"error": "Message is required"}), 400
                
                if not criteria:
                    print("Error: Criteria is missing in POST request.")
                    return jsonify({"error": "Criteria is required"}), 400
                
                try:
                    global criteria_F
                    global question_F
                    criteria_F = criteria
                    question_F = message
                    # Store the configuration in the session
                    session['query'] = {
                        "search_term": search_term,
                        "question": message,
                        "criteria": criteria
                    }
                    print("Session data:", session)
                except Exception as e:
                    print(f"Error: couldn't enter query information in session: {e}")
                

                # Scrape data based on the search term
                try:
                    data = scrape_data(search_term, customer_number, total=10)
                    print(f"Info: Data scraped successfully for search term: {search_term}")
                except Exception as e:
                    print(f"Error scraping data for search term '{search_term}': {e}")
                    return jsonify({"error": "An error occurred during data scraping"}), 500

                # Make a call using the Twilio API
                try:
                    make_call(twilio_phone_number, customer_number, message)
                    print(f"Info: Call initiated successfully from {twilio_phone_number} to {customer_number}.")
                    return data.to_dict(orient='records')
                except Exception as e:
                    print(f"Error making call from {twilio_phone_number} to {customer_number}: {e}")
                    return jsonify({"error": "An error occurred while making the call"}), 500

                # Return the scraped data as JSON
                return data.to_dict(orient='records')

            except Exception as e:
                print(f"Error handling POST request: {e}")
                return jsonify({"error": "An error occurred while processing the request"}), 500

        # If the request method is GET, render the query page
        print("Info: Rendering query page.")
        return render_template('query.html')

    except Exception as e:
        print(f"Unexpected error in query function: {e}")
        return jsonify({"error": "An unexpected error occurred"}), 500

@app.route('/logout')
def logout():
    try:
        if 'username' not in session:
            print("Error: Attempt to log out without a user being logged in.")
            return "Error: No user is logged in.", 400  # Return a custom error message with HTTP 400 (Bad Request)

        username = session.pop('username', None)  # Remove user from session
        print(f"Info: User '{username}' has been successfully logged out.")
        return redirect(url_for('index'))  # Redirect to login page

    except Exception as e:
        print(f"Unexpected error in logout function: {e}")
        return "An unexpected error occurred during logout. Please try again.", 500  # Return HTTP 500 for server error

@app.route('/addUser', methods=['POST'])
def addUser():
    try:
        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            # Check if all fields are filled
            if not email or not password or not confirm_password or not name:
                error = "All fields are required!"
                print("Error: Missing required fields during registration.")
                return render_template('register.html', error=error)

            # Validate email format
            import re
            email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
            if not re.match(email_pattern, email):
                error = "Invalid email format!"
                print(f"Error: Invalid email format for email: {email}")
                return render_template('register.html', error=error)

            # Validate password conditions
            if password != confirm_password:
                error = "Passwords do not match!"
                print("Error: Passwords do not match.")
                return render_template('register.html', error=error)
            if len(password) < 8:
                error = "Password must be at least 8 characters long!"
                print("Error: Password is too short.")
                return render_template('register.html', error=error)

            # Hash the password before storing it
            try:
                hashed_password = generate_password_hash(password)
                print("Info: Password hashed successfully.")
            except Exception as e:
                print(f"Error hashing password: {e}")
                error = "An error occurred while processing your password. Please try again."
                return render_template('register.html', error=error)

            # Store user data in the database
            try:
                conn = get_db_connection()
                if not conn:
                    print("Error: Database connection failed.")
                    error = "Database connection error!"
                    return render_template('register.html', error=error)

                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO users (name, email, password)
                            VALUES (%s, %s, %s)
                            """,
                            (name, email, hashed_password)  # Insert the hashed password
                        )
                        conn.commit()
                        print(f"Info: User {email} registered successfully.")
                except Exception as e:
                    print(f"Error inserting data into the database: {e}")
                    error = "An error occurred while registering. Please try again."
                    return render_template('register.html', error=error)
                finally:
                    conn.close()
                    print("Info: Database connection closed.")
            except Exception as e:
                print(f"Error establishing database connection: {e}")
                error = "Database connection error. Please try again."
                return render_template('register.html', error=error)

            # Redirect to login after successful registration
            return redirect(url_for('index'))

    except Exception as e:
        print(f"Unexpected error in addUser function: {e}")
        error = "An unexpected error occurred. Please try again later."
        return render_template('register.html', error=error)

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/updateUserProfile', methods=['GET', 'POST'])
def updateUserProfile():
    try:
        if 'username' not in session:
            print("Warning: Username not in session. Redirecting to login page.")
            return redirect(url_for('index'))  # Redirect to login page if not logged in

        if request.method == 'POST':
            # Handle the form submission
            new_name = request.form.get('name')
            username = session['username']  # Retrieve the logged-in user's username (email)

            if not new_name:
                print("Error: Name field is empty.")
                flash('Name cannot be empty.', 'error')
                return redirect(url_for('getUserProfile'))

            # Establish database connection
            try:
                conn = get_db_connection()
                if not conn:
                    print("Error: Failed to establish database connection.")
                    flash('Database connection error.', 'error')
                    return redirect(url_for('getUserProfile'))

                try:
                    # Update the user's name in the database
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE users
                            SET name = %s
                            WHERE email = %s
                            """,
                            (new_name, username)
                        )
                        conn.commit()
                        print(f"Info: User profile updated successfully for {username}. New name: {new_name}")
                        flash('Profile updated successfully!', 'success')

                except Exception as e:
                    print(f"Error: Exception occurred during database update for user {username}. Details: {e}")
                    flash('An error occurred while updating your profile. Please try again.', 'error')

                finally:
                    conn.close()
                    print("Info: Database connection closed.")

            except Exception as e:
                print(f"Error: Could not connect to the database. Details: {e}")
                flash('Database connection error. Please try again.', 'error')
                return redirect(url_for('getUserProfile'))

            return redirect(url_for('getUserProfile'))  # Redirect to profile page after update

        # If it's a GET request, render the page with the current user profile information
        print(f"Info: Rendering profile update page for user {session['username']}.")
        return render_template('index.html')

    except Exception as e:
        print(f"Unexpected error in updateUserProfile function: {e}")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('getUserProfile'))

@app.route('/gotoResetPassword', methods=['POST'])
def gotoResetPassword():
    return render_template('resetpassword.html')

@app.route('/resetPassword', methods=['POST', 'GET'])
def resetPassword():
    try:
        if 'username' not in session:
            print("Warning: Username not in session. Redirecting to login page.")
            return redirect(url_for('index'))  # Redirect to login page if not logged in

        username = session['username']  # Get the logged-in user's username (email)

        # Handle the GET request to render the reset password form
        if request.method == 'GET':
            print(f"Rendering reset password form for user: {username}")
            return render_template('resetpassword.html')  # Render the reset password page

        # Handle the POST request for resetting the password
        if request.method == 'POST':
            # Get form data
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_new_password')

            # Check if all fields are filled
            if not old_password or not new_password or not confirm_password:
                print("Error: Not all fields are filled.")
                flash('All fields are required.', 'error')
                return redirect(url_for('resetPassword'))  # Stay on the reset page

            # Check if new password matches confirm password
            if new_password != confirm_password:
                print("Error: New password and confirm password do not match.")
                flash('New password and confirm password do not match.', 'error')
                return redirect(url_for('resetPassword'))  # Stay on the reset page

            # Check if the new password is at least 8 characters long
            if len(new_password) < 8:
                print("Error: New password is too short (less than 8 characters).")
                flash('New password must be at least 8 characters long.', 'error')
                return redirect(url_for('resetPassword'))  # Stay on the reset page

            # Handle password reset process
            try:
                # Query the User model to get the user by email (username)
                user = User.query.filter_by(email=username).first()

                if not user:
                    print(f"Error: User not found in the database for email: {username}")
                    flash('User not found. Please log in again.', 'error')
                    return redirect(url_for('index'))  # Redirect to login page if user not found

                # Check if the old password matches the hashed password in the database
                if not check_password_hash(user.password, old_password):  # This checks the hashed password
                    print(f"Error: Old password check failed for user: {username}")
                    flash('Old password is incorrect.', 'error')
                    return redirect(url_for('resetPassword'))  # Stay on the reset page

                # Hash the new password and update it in the database
                hashed_new_password = generate_password_hash(new_password)
                print(f"Info: Updating password for user: {username}")

                # Update the password in the database
                user.password = hashed_new_password
                db.session.commit()  # Commit the change to the database

                flash('Password updated successfully!', 'success')
                print(f"Success: Password updated for user: {username}")
                return redirect(url_for('getUserProfile'))  # Redirect to profile page after success

            except Exception as e:
                print(f"Error during password reset process: {e}")
                flash('An error occurred while resetting your password. Please try again.', 'error')
                return redirect(url_for('resetPassword'))  # Stay on the reset page

    except Exception as e:
        print(f"Unexpected error in resetPassword function: {e}")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('resetPassword'))  # Stay on the reset page
        
@app.route('/profile')
def getUserProfile():
    try:
        # Check if the user is logged in by verifying if 'username' exists in the session
        if 'username' not in session:
            print("Warning: Username not in session. Redirecting to login page.")
            return redirect(url_for('index'))  # Redirect to login page if not logged in
        
        username = session['username']  # Retrieve the username (email) from the session

        # Fetch the user from the database using the username (email)
        user = User.query.filter_by(email=username).first()

        if not user:
            print(f"Error: User not found in the database for email: {username}")
            return render_template('error.html', error="User not found")  # Error if user not found in the database
        
        # Pass user data to the profile template
        print(f"Info: Profile data successfully retrieved for user: {username}")
        return render_template('profile.html', user=user)

    except Exception as e:
        print("Exception: An unexpected error occurred while retrieving the user profile.")
        print(f"Details: {e}")
        return render_template('error.html', error="An unexpected error occurred. Please try again later.")

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)

    
