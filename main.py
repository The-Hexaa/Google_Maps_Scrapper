from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from playwright.sync_api import sync_playwright
import pandas as pd
import os
from flask_cors import CORS
import requests
import time
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql
from model import db, User  # Import db and User model from model.py
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

# Load environment variables from the .env file
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Load configuration from environment variables
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
CORS(app)

# Database configuration
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Construct the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy with the app
db.init_app(app)




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

def scrape_data(search_for, total=10):
    names_list, address_list, website_list, phones_list = [], [], [], []
    reviews_c_list, reviews_a_list = [], []
    store_s_list, in_store_list, store_del_list = [], [], []
    place_t_list, open_list, intro_list = [], [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.google.com/maps")
        page.wait_for_selector('//input[@id="searchboxinput"]')

        page.locator('//input[@id="searchboxinput"]').fill(search_for)
        page.keyboard.press("Enter")
        page.wait_for_selector('//a[contains(@href, "https://www.google.com/maps/place")]')

        previously_counted = 0
        while True:
            page.mouse.wheel(0, 1000000)
            page.wait_for_selector('//a[contains(@href, "https://www.google.com/maps/place")]')
            if page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count() >= total:
                listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()[:total]
                listings = [listing.locator("xpath=..") for listing in listings]
                break
            else:
                current_count = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count()
                if current_count == previously_counted:
                    listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()
                    break
                previously_counted = current_count

        for listing in listings:
            listing.click()
            page.wait_for_selector('//div[@class="TIHn2 "]//h1[@class="DUwDvf lfPIob"]')

            name_xpath = '//div[@class="TIHn2 "]//h1[@class="DUwDvf lfPIob"]'
            address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
            website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
            phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
            reviews_count_xpath = '//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span//span//span[@aria-label]'
            reviews_average_xpath = '//div[@class="TIHn2 "]//div[@class="fontBodyMedium dmRWX"]//div//span[@aria-hidden]'
            info1 = '//div[@class="LTs0Rc"][1]'
            opens_at_xpath = '//button[contains(@data-item-id, "oh")]//div[contains(@class, "fontBodyMedium")]'
            place_type_xpath = '//div[@class="LBgpqf"]//button[@class="DkEaL "]'
            intro_xpath = '//div[@class="WeS02d fontBodyMedium"]//div[@class="PYvSYb "]'

            extract_data(name_xpath, names_list, page)
            extract_data(address_xpath, address_list, page)
            extract_data(website_xpath, website_list, page)
            extract_data(phone_number_xpath, phones_list, page)
            extract_data(place_type_xpath, place_t_list, page)
            extract_data(intro_xpath, intro_list, page)

            # Safe extraction for specific elements
            try:
                reviews_count = page.locator(reviews_count_xpath).inner_text(timeout=5000) if page.locator(reviews_count_xpath).count() > 0 else ""
                reviews_c_list.append(reviews_count.replace('(', '').replace(')', '').replace(',', ''))

                reviews_average = page.locator(reviews_average_xpath).inner_text(timeout=5000) if page.locator(reviews_average_xpath).count() > 0 else ""
                reviews_a_list.append(reviews_average.replace(' ', '').replace(',', '.'))

                store_s_list.append("Yes" if 'shop' in page.locator(info1).inner_text(timeout=5000) else "No")
                in_store_list.append("Yes" if 'pickup' in page.locator(info1).inner_text(timeout=5000) else "No")
                store_del_list.append("Yes" if 'delivery' in page.locator(info1).inner_text(timeout=5000) else "No")
            except Exception as e:
                print(f"Skipping store info due to timeout error: {e}")
                store_s_list.append("No")
                in_store_list.append("No")
                store_del_list.append("No")

            opening_time = page.locator(opens_at_xpath).inner_text(timeout=5000) if page.locator(opens_at_xpath).count() > 0 else ""
            open_list.append(opening_time)

        # DataFrame construction and CSV output
        df = pd.DataFrame({
            'Names': names_list, 'Website': website_list, 'Introduction': intro_list,
            'Phone Number': phones_list, 'Address': address_list, 'Review Count': reviews_c_list,
            'Average Review Count': reviews_a_list, 'Store Shopping': store_s_list,
            'In Store Pickup': in_store_list, 'Delivery': store_del_list,
            'Type': place_t_list, 'Opens At': open_list
        })

        df.drop_duplicates(subset=['Names', 'Phone Number', 'Address'], inplace=True)
        df.dropna(axis=1, how='all', inplace=True)
        df.to_csv('result.csv', index=False)

        csv_file_path = 'result.csv'

        print(f"CSV file generated at: {csv_file_path}")
        print("CSV file contents:")
        print(df.to_string(index=False))
        browser.close()
        return df



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
            },
            "phoneNumber": {
                "twilioAccountSid": twilio_account_sid,
                "twilioAuthToken": twilio_auth_token,
                "twilioPhoneNumber": twilio_phone_number,
            },
            "customer": {
                "number": customer_number  # Customer phone number
            }
        }

        headers = {
            "Authorization": f"Bearer {os.getenv('VAPI_BEARER_TOKEN')}",  # VAPI Bearer token
            "Content-Type": "application/json"
        }

        # Make the API call to VAPI
        response = requests.post("https://api.vapi.ai/call", json=payload, headers=headers)
        
        # Check for errors in the response
        response.raise_for_status()

        # Return response JSON
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(f"Error making call to {phone_number}: {e}")
        return {"error": str(e)}
# # Example usage:
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
    username = request.form.get('username')
    password = request.form.get('password')

    conn = get_db_connection()
    if not conn:
        return render_template('login.html', error="Database connection error!")

    try:
        with conn.cursor() as cur:
            # Retrieve the user's record based on email
            cur.execute(
                """
                SELECT * FROM users WHERE email = %s
                """,
                (username,)
            )
            user = cur.fetchone()

        if user:
            # Assuming the password is the 3rd column in the tuple
            stored_password_hash = user[3]  # Change the index if your columns are in a different order
            
            # Check if the entered password matches the stored hashed password
            if check_password_hash(stored_password_hash, password):
                session['username'] = username  # Set session data
                return render_template('twilio.html')
            else:
                return render_template('login.html', error="Invalid credentials")
        else:
            return render_template('login.html', error="Invalid credentials")
    except Exception as e:
        print("Error querying database:", e)
        return render_template('login.html', error="An error occurred. Please try again.")
    finally:
        conn.close()

@app.route('/query', methods=['GET', 'POST'])
def query():
    twilio_config = session.get('twilio_config')
    twilio_phone_number = twilio_config.get('twilioPhoneNumber')
    customer_number = twilio_config.get('customerPhoneNumber')

    if 'username' not in session:
        return redirect(url_for('index'))  # Redirect to login if not logged in

    if request.method == 'POST':
        search_term = request.json.get('search_term')
        message = request.json.get('message')
        # prompt = request.json.get('prompt')
        if not search_term:
            return jsonify({"error": "Search term is required"}), 400
        data = scrape_data(search_term, total=10)
        # csv_file_path = 'result.csv'
        # call_all_numbers_from_csv(csv_file_path)  # Call VAPI numbers from the CSV

        make_call(twilio_phone_number, customer_number, message)
        return data.to_dict(orient='records')
        
    return render_template('query.html')


# @app.route('/logout')
# def logout():
#     session.pop('email', None)  # Remove user from session
#     return redirect(url_for('index'))  # Redirect to login page

@app.route('/logout')
def logout():
    if 'username' not in session:
        # If 'email' is not in the session, raise an error or handle it
        return "Error: No user is logged in.", 400  # Return a custom error message with HTTP 400 (Bad Request)
    
    session.pop('username', None)  # Remove user from session
    return redirect(url_for('index'))  # Redirect to login page


@app.route('/addUser', methods=['POST'])
def addUser():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Check if all fields are filled
        if not email or not password or not confirm_password or not name:
            error = "All fields are required!"
            return render_template('register.html', error=error)

        # Validate email format
        import re
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_pattern, email):
            error = "Invalid email format!"
            return render_template('register.html', error=error)

        # Validate password conditions
        if password != confirm_password:
            error = "Passwords do not match!"
            return render_template('register.html', error=error)
        if len(password) < 8:
            error = "Password must be at least 8 characters long!"
            return render_template('register.html', error=error)

        # Hash the password before storing it
        hashed_password = generate_password_hash(password)

        # Store user data in the database
        conn = get_db_connection()
        if not conn:
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
        except Exception as e:
            print("Error inserting data into the database:", e)
            error = "An error occurred while registering. Please try again."
            return render_template('register.html', error=error)
        finally:
            conn.close()

        # Redirect to login after successful registration
        return redirect(url_for('index'))


@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/updateUserProfile', methods=['GET', 'POST'])
def updateUserProfile():
    if 'username' not in session:
        return redirect(url_for('index'))  # Redirect to login page if not logged in

    if request.method == 'POST':
        # Handle the form submission
        new_name = request.form.get('name')
        username = session['username']  # Retrieve the logged-in user's username (email)

        if not new_name:
            flash('Name cannot be empty.', 'error')
            return redirect(url_for('getUserProfile'))

        # Update the user's name in the database
        conn = get_db_connection()
        if not conn:
            flash('Database connection error.', 'error')
            return redirect(url_for('getUserProfile'))

        try:
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
                flash('Profile updated successfully!', 'success')
        except Exception as e:
            print(f"Error updating user profile: {e}")
            flash('An error occurred while updating your profile. Please try again.', 'error')
        finally:
            conn.close()

        return redirect(url_for('getUserProfile'))  # Redirect to profile page after update

    # If it's a GET request, render the page with the current user profile information
    return render_template('index.html')

@app.route('/gotoResetPassword', methods=['POST'])
def gotoResetPassword():
    return render_template('resetpassword.html')

@app.route('/resetPassword', methods=['POST', 'GET'])
def resetPassword():
    if 'username' not in session:
        return redirect(url_for('index'))  # Redirect to login page if not logged in

    username = session['username']  # Get the logged-in user's username (email)

    # Handle the GET request to render the reset password form
    if request.method == 'GET':
        return render_template('resetpassword.html')  # Render the reset password page
    
    # Handle the POST request for resetting the password
    if request.method == 'POST':
        # Get form data
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_new_password')

        # Check if all fields are filled
        if not old_password or not new_password or not confirm_password:
            flash('All fields are required.', 'error')
            return redirect(url_for('resetPassword'))  # Stay on the reset page

        # Check if new password matches confirm password
        if new_password != confirm_password:
            flash('New password and confirm password do not match.', 'error')
            return redirect(url_for('resetPassword'))  # Stay on the reset page

        # Check if the new password is at least 8 characters long
        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'error')
            return redirect(url_for('resetPassword'))  # Stay on the reset page

        try:
            # Query the User model to get the user by email (username)
            user = User.query.filter_by(email=username).first()

            if not user:
                flash('User not found. Please log in again.', 'error')
                return redirect(url_for('index'))  # Redirect to login page if user not found

            # Debugging: Print the inputs and the password from the database
            # print(f"Old password entered by user: {old_password}")
            # print(f"New password entered by user: {new_password}")
            # print(f"Confirm new password entered by user: {confirm_password}")
            # print(f"Password stored in DB (hashed): {user.password}")

            # Debugging: Manually hash the old password and print it
            manually_hashed_old_password = generate_password_hash(old_password)
            # print(f"Manually hashed old password: {manually_hashed_old_password}")

            # Check if the old password matches the hashed password in the database
            if not check_password_hash(user.password, old_password):  # This will check the hashed password
                print(f"Old password check failed!")  # Log if the check failed
                flash('Old password is incorrect.', 'error')
                return redirect(url_for('resetPassword'))  # Stay on the reset page

            # Debugging: Print the password comparison
            print(f"Password comparison result: {check_password_hash(user.password, old_password)}")

            # Hash the new password and update it in the database
            hashed_new_password = generate_password_hash(new_password)
            # print(f"New password to be stored (hashed): {hashed_new_password}")

            # Update the password in the database
            user.password = hashed_new_password
            db.session.commit()  # Commit the change to the database

            flash('Password updated successfully!', 'success')
            return redirect(url_for('getUserProfile'))  # Redirect to profile page after success

        except Exception as e:
            print(f"Error resetting password: {e}")
            flash('An error occurred while resetting your password. Please try again.', 'error')
            return redirect(url_for('resetPassword'))  # Stay on the reset page


        
@app.route('/profile')
def getUserProfile():
    # Check if the user is logged in by verifying if 'username' exists in the session
    if 'username' not in session:
        print("email not in session.")
        return redirect(url_for('index'))  # Redirect to login page if not logged in
    
    username = session['username']  # Retrieve the username (email) from the session

    # Fetch the user from the database using the username (email)
    user = User.query.filter_by(email=username).first()

    if not user:
        return render_template('error.html', error="User not found")  # Error if user not found in the database
    
    # Pass user data to the profile template
    return render_template('profile.html', user=user)
    # return render_template('profile.html')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

    
