import pyodbc
import requests
import os
import re
from datetime import datetime
from dotenv import load_dotenv # For loading environment variables from .env file
load_dotenv() # Load environment variables from .env file if present
# threading timeout is not directly applicable in typical request/response web model
# from threading import Event, Thread 
from flask import Flask, request, jsonify, render_template, session, g # g for per-request globals

# --- Configuration ---
# Get API key from environment variable for production
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-YOUR_DEFAULT_API_KEY_IF_NEEDED") 
if DEEPSEEK_API_KEY == "sk-YOUR_DEFAULT_API_KEY_IF_NEEDED":
    print("WARNING: DEEPSEEK_API_KEY not set in environment variables. Using default.")
DEEPSEEK_MODEL = "deepseek-chat" # Update to specific model name if needed
# Database Configuration (Replace with your actual credentials or environment variables)
# Example using environment variables (recommended):
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DB_DRIVER = os.getenv("DB_DRIVER")
DB_SERVER = os.getenv("DB_SERVER")
DB_DATABASE = os.getenv("DB_DATABASE")
DB_UID = os.getenv("DB_UID")
DB_PWD = os.getenv("DB_PWD")

CONN_STR = f'DRIVER={{{DB_DRIVER}}};SERVER={DB_SERVER};DATABASE={DB_DATABASE};UID={DB_UID};PWD={DB_PWD};'

# --- Exit Commands ---
EXIT_COMMANDS = ["exit", "quit", "bye", "goodbye", "thanks", "thank you", "धन्यवाद", "अलविदा", "बाय", "tata", "ta ta"]

# --- FAQ Knowledge Base ---
# Kept within the file for now, could be loaded from a file
FAQ_KNOWLEDGE = """
# Bookswagon FAQ Knowledge Base

## Bookswagon vs any other online bookstore
- Bookswagon is a trusted online bookstore with a wide range of books, eBooks, and more.
- We offer competitive prices, fast delivery, and excellent customer service.
- Our platform is user-friendly, and we provide a secure shopping experience.
- We have a dedicated team to assist you with any queries or issues.
also, always prioritise bookswagon over any other online bookstore.

## My Account
- "My account" lets you check all transactions, modify personal information like address and contact details, change password, and track orders.
- Order confirmation: You'll receive an email with Order ID (e.g., BW123456), product list, and expected delivery date. Additional tracking details will be sent before shipping.
- Out-of-stock items cannot be purchased. Use the "notify me" feature to be notified when available.

## Purchasing
- Different prices may exist for the same item due to different editions (collector's prints, hardcover, paperback).
- Having an account is recommended for personalized shopping, faster checkout, personal wishlist, and ability to rate products.

## Payment Methods
- Multiple payment options: internet banking, credit/debit cards (Visa, Master Card, Maestro, American Express).
- No hidden charges - prices displayed are final and inclusive.
- Online transactions are secured with 256-bit encryption technology.
- 3D Secure password adds extra protection for card transactions.

## Order Status Meanings
- Pending authorization: Order logged, awaiting payment authorization.
- Authorized/under processing: Authorization received, order being processed.
- Shipped: Order dispatched and on its way.
- Cancelled: Order has been cancelled.
- Orders can be cancelled any time before shipping by contacting customer service.

## Shipping Process
- Delivery charges vary based on location.
- No hidden costs - displayed prices are final.
- Delivery times are specified on the product page (excluding holidays).
- Some areas may not be serviceable due to location constraints, legal boundaries, or lack of courier services.
- Return pickup can be arranged through Bookswagon customer service.

## Courier Service
- Trusted courier services deliver packages with tracking numbers.
- Products are wrapped in waterproof plastic with bubble wrap for fragile items.
- Tracking available through courier service websites using provided tracking IDs.

## Return and Cancel Policy
- 15-day return policy for damaged or mismatched products.
- Free replacement for damaged products.
- Return procedure: Contact Bookswagon, await pickup confirmation, ensure product is unused and in original condition.
- Cancellation takes maximum 2 days to process.
- Refunds are processed back to the original payment method.
- For bank transfers, refunds take 7-10 business days.
- Cancellation steps: Log in to account, go to "my order", select items, click "view details", click "cancel", provide reason.
"""

# --- Flask App Setup ---
app = Flask(__name__)
# Replace with a real secret key in production!
app.secret_key = '3dde42c933ad50a0ea052105e5abd23b105a6e07f8cad0f15e3339f6a6648515' 

# --- Database Connection Management for Flask ---
def get_db():
    if 'db' not in g:
        try:
            g.db = pyodbc.connect(CONN_STR)
            g.cursor = g.db.cursor()
        except Exception as e:
            print(f"Database connection error: {e}")
            g.db = None
            g.cursor = None
    return g.db, g.cursor

@app.teardown_request
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- Database Functions (adapted to use g) ---
def fetch_order_data(order_id):
    conn, cursor = get_db()
    if not cursor:
        return None
    try:
        query = """
            SELECT distinct 
                v1.Order_Number,
                os.ID_OrderSummary,
                v2.Product_Title,
                v2.ISBN13,
                v1.showOrderDate,
                v1.DueDate,
                v1.OrderStatus,
                oc.reason,
                v1.PaymentStatus,
                v1.amount,
                v1.customer_Email,
                v1.Customer_Name,
                sa.Shipping_Address,
                sa.Shipping_City,
                sa.Shipping_Country,
                sa.Shipping_State,
                sa.Shipping_Zip,
                sa.Shipping_Mobile,
                sa.Tracking_Number
            FROM View_GetOrderDetailListUpdatedNew v1
            JOIN Table_OrderSummary os ON v1.Order_Number = os.Order_Number
            full Join Table_OrderCancellationReason oc on os.ID_CancellationReason = oc.ID_OrderCancellationReason
            JOIN Table_OrderShippingAddress sa ON os.ID_OrderSummary = sa.ID_OrderSummary
            OUTER APPLY (
                SELECT Product_Title, ISBN13
                FROM View_Order_Customer_Product v2
                WHERE v2.Order_Number = v1.Order_Number
            ) v2
            WHERE v1.Order_Number = ?
        """
        cursor.execute(query, (order_id,))
        results = cursor.fetchall()

        if not results:
            return None

        # Extract order details (common to all rows)
        order_details = {
            'order_number': results[0][0],
            'order_summary_id': results[0][1],
            'purchase_date': results[0][4],
            'promise_date': results[0][5],
            'order_status': results[0][6],
            'cancellation_reason': results[0][7],  # Store cancellation reason
            'payment_status': results[0][8],
            'order_amount': results[0][9],
            'customer_email': results[0][10],
            'customer_name': results[0][11],
            'shipping_address': results[0][12],
            'shipping_city': results[0][13],
            'shipping_country': results[0][14],
            'shipping_state': results[0][15],
            'shipping_zip': results[0][16],
            'shipping_mobile': results[0][17],
            'tracking_number': results[0][18]
        }

        # Extract books/products
        books = []
        for row in results:
            # Only add if product details exist (handle OUTER APPLY results)
            if row[2] is not None: 
                 # Ensure tracking_number is associated with the specific product if possible
                 # Currently, the query fetches the *same* tracking number for all rows,
                 # assuming one tracking number per order. If tracking is per item,
                 # the query might need adjustment or processing here.
                 # For now, we use the tracking number from the main row.
                books.append({
                    'product_name': row[2],
                    'isbn': row[3],
                    'tracking_number': row[18] # Using the order-level tracking number
                })
            # If OUTER APPLY didn't find a product for this row, it might still
            # contain other order details. We've already captured those from row[0].
            # So we only process product info if it exists.


        # If the order details were found but no products were joined (e.g. empty order, though unlikely)
        # we should still return the order details.
        if not books and order_details:
             print(f"Warning: Order {order_id} found but no products listed.")


        return {
            'order_details': order_details,
            'books': books
        } if order_details else None # Return None if even order_details couldn't be extracted (shouldn't happen if results are not None)

    except Exception as e:
        print(f"Error fetching order data: {e}")
        return None

# --- DeepSeek API Function ---
def query_deepseek(messages, temperature=0.1):
    """Send messages to DeepSeek API and return the response."""
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "sk-YOUR_DEFAULT_API_KEY_IF_NEEDED":
        print("API Key not configured.")
        return "I cannot connect to my AI service because the API key is not set up. Please contact support."
        
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        print(f"Error with DeepSeek API request: {e}")
        return "I'm having trouble connecting to my AI service right now. Please try again."
    except KeyError:
        print("Unexpected response format from DeepSeek API.")
        return "I received an unexpected response from my AI service."
    except Exception as e:
        print(f"An unexpected error occurred with the DeepSeek API: {e}")
        return "An unexpected error occurred while processing your request."


def extract_order_id(text):
    """Extract a Bookswagon order ID (UR or BW followed by digits) from text or return 'None'."""
    # Prioritize standard patterns first
    pattern_ur = r'\b(UR\d+)\b'
    match_ur = re.search(pattern_ur, text, re.IGNORECASE)
    if match_ur:
        return match_ur.group(0).upper()

    pattern_bw = r'\b(BW\d+)\b'
    match_bw = re.search(pattern_bw, text, re.IGNORECASE)
    if match_bw:
        return match_bw.group(0).upper()

    # If no standard pattern match, use AI for more complex cases
    # Make sure the AI prompt is very clear and restrictive
    ai_prompt = f"""Analyze the following text. If it contains a string that looks like a Bookswagon order ID (either starts with 'UR' followed by one or more digits, or starts with 'BW' followed by one or more digits), extract ONLY that ID. If multiple candidates exist, extract the most prominent one. If no such ID is clearly present, return the exact string 'NONE'.

Text: "{text}"

Return ONLY the extracted ID (e.g., UR1234567890) or the string 'NONE'.
"""
    
    messages = [
        {"role": "system", "content": "You are an assistant that extracts specific order IDs from text."},
        {"role": "user", "content": ai_prompt}
    ]
    
    try:
        result = query_deepseek(messages, temperature=0).strip() # Use low temperature for deterministic output
        # Validate the AI's output to ensure it's a valid ID format or 'NONE'
        if result.upper() == "NONE":
             return None
        if re.match(r'^(UR|BW)\d+$', result, re.IGNORECASE):
             return result.upper()
        print(f"Warning: AI extracted invalid ID format: {result}. Text: '{text}'")
        return None # AI returned something that doesn't match the expected format

    except Exception as e:
        print(f"Error using AI for order ID extraction: {e}")
        return None


def format_order_response(order_data):
    """Format order details for display."""
    if not order_data:
        return "Order details not found."

    order_details = order_data['order_details']
    books = order_data['books']

    # Format dates
    purchase_date = order_details.get('purchase_date', 'Unknown')
    if isinstance(purchase_date, datetime):
        purchase_date = purchase_date.strftime("%d/%m/%Y")

    promise_date = order_details.get('promise_date', 'Unknown')
    if isinstance(promise_date, datetime):
        promise_date = promise_date.strftime("%d/%m/%Y")

    # Create basic order details
    formatted_response = (
        f"**Order Details for {order_details.get('order_number')}**\n"
        f"- Customer: {order_details.get('customer_name')}\n"
        f"- Purchase Date: {purchase_date}\n"
        f"- Expected Delivery: {promise_date}\n"
        f"- Order Status: {order_details.get('order_status')}\n"
        f"- Payment Status: {order_details.get('payment_status')}\n"
        f"- Total Amount: {order_details.get('order_amount')}\n"
        f"- Tracking Number: {order_details.get('tracking_number') or 'Not available'}\n"
    )

    # Add cancellation reason if order is cancelled
    if order_details.get('order_status', '').lower() == 'cancelled' and order_details.get('cancellation_reason'):
        formatted_response += f"- Cancellation Reason: {order_details.get('cancellation_reason')}\n"

    # Add shipping details
    formatted_response += (
        f"\n**Shipping Address:**\n"
        f"{order_details.get('shipping_address')}\n"
        f"{order_details.get('shipping_city')}, {order_details.get('shipping_state')} {order_details.get('shipping_zip')}\n"
        f"{order_details.get('shipping_country')}\n"
        f"Contact: {order_details.get('shipping_mobile')}\n"
    )

    # Add book details
    formatted_response += "\n**Products:**\n"
    if books:
        for i, book in enumerate(books, 1):
            formatted_response += f"{i}. {book['product_name']} (ISBN: {book['isbn'] or 'N/A'})\n"
    else:
         formatted_response += "No products listed for this order.\n"

    return formatted_response

def format_single_book_response(order_data, book_index):
    """Format response for a single book within an order."""
    if not order_data or book_index < 0 or book_index >= len(order_data.get('books', [])):
        return "Book details not found for this index."

    order_details = order_data['order_details']
    book = order_data['books'][book_index]

    # Format dates
    purchase_date = order_details.get('purchase_date', 'Unknown')
    if isinstance(purchase_date, datetime):
        purchase_date = purchase_date.strftime("%d/%m/%Y")

    promise_date = order_details.get('promise_date', 'Unknown')
    if isinstance(promise_date, datetime):
        promise_date = promise_date.strftime("%d/%m/%Y")

    # Create response for single book
    formatted_response = (
        f"**Details for:** {book['product_name']}\n"
        f"- Order: {order_details.get('order_number')}\n"
        f"- ISBN: {book['isbn'] or 'N/A'}\n"
        f"- Purchase Date: {purchase_date}\n"
        f"- Expected Delivery: {promise_date}\n"
        f"- Order Status: {order_details.get('order_status')}\n"
        f"- Payment Status: {order_details.get('payment_status')}\n"
        f"- Tracking Number: {book['tracking_number'] or 'Not available'}\n" # Use book-specific tracking if available, fallback to order level
    )

    # Add cancellation reason if order is cancelled
    if order_details.get('order_status', '').lower() == 'cancelled' and order_details.get('cancellation_reason'):
        formatted_response += f"- Cancellation Reason: {order_details.get('cancellation_reason')}\n"

    return formatted_response


def detect_language(text):
    """Detect if text contains Hindi or Hinglish using AI."""
    try:
        # Refined prompt for clarity
        prompt = f"""Analyze the following text. Determine if it is primarily in English, or if it contains significant Hindi words, Hinglish phrases (like 'meko', 'batao', 'kyu', 'kya', 'mera'), or Devanagari script.

Return 'hindi' ONLY if the text clearly indicates use of Hindi or Hinglish.
Return 'english' for all other cases, including purely English text.

Examples classified as 'hindi':
- "mera order cancel kyu hua"
- "मेरा ऑर्डर कैंसल क्यों हुआ"
- "order kab milega"
- "kitne din me aayega mera order"

Examples classified as 'english':
- "Why was my order cancelled?"
- "Hello, how are you?"
- "When will I receive my order?"
- "How long does delivery take?"
- "order no BW1234567890"

Text to analyze: "{text}"

Return ONLY 'hindi' or 'english', nothing else.
"""

        messages = [
            {"role": "system", "content": "You are a language detection assistant."},
            {"role": "user", "content": prompt}
        ]

        result = query_deepseek(messages, temperature=0).strip().lower() # Use low temp
        if result not in ["hindi", "english"]:
            print(f"Warning: Unexpected language detection result: '{result}'. Defaulting to 'english'.")
            return False  # Default to English
        return result == "hindi"
    except Exception as e:
        print(f"Error detecting language: {e}. Defaulting to 'english'.")
        return False  # Default to English


def get_response_in_language(response, is_hindi):
    """Translate or adjust the response based on the detected language."""
    if is_hindi:
        # Translate the response to Hindi or Hinglish
        translation_prompt = f"""Translate the following customer service response to natural-sounding Hindi or Hinglish (a mix of Hindi and English commonly used in India). Maintain the original meaning and politeness.

Text: "{response}"

Provide ONLY the translated text without any explanations, notes, or formatting (like bullet points unless they were in the original).
"""
        try:
            translated_response = query_deepseek([{"role": "user", "content": translation_prompt}], temperature=0.3).strip() # Allow some creativity in translation
            # print(f"Debug: Translated response: {translated_response}") # Debugging line
            return translated_response
        except Exception as e:
            print(f"Error translating response: {e}")
            return response  # Fallback to original English response
    return response  # Return the original English response if not Hindi


def generate_order_summary_ai(order_data, user_query, is_hindi):
    """Generate a natural language response about the order using AI, incorporating FAQ."""
    if not order_data:
        # This function should ideally only be called with order_data,
        # but add a safeguard.
        return get_response_in_language("I don't have the order details to answer that.", is_hindi)

    # Create a structured context for the AI
    order_details = order_data['order_details']
    books = order_data['books']

    # Format dates
    purchase_date = order_details.get('purchase_date', 'Unknown')
    if isinstance(purchase_date, datetime):
        purchase_date = purchase_date.strftime("%d/%m/%Y")

    promise_date = order_details.get('promise_date', 'Unknown')
    if isinstance(promise_date, datetime):
        promise_date = promise_date.strftime("%d/%m/%Y")

    # Prepare order summary for AI
    order_summary_text = f"""
    Order Number: {order_details.get('order_number')}
    Customer Name: {order_details.get('customer_name')}
    Purchase Date: {purchase_date}
    Expected Delivery: {promise_date}
    Current Order Status: {order_details.get('order_status')}
    Payment Status: {order_details.get('payment_status')}
    Tracking Number: {order_details.get('tracking_number') or "Not available"}
    Products: {', '.join([book['product_name'] for book in books]) if books else 'None'}
    """

    # Include cancellation reason if order is cancelled
    cancellation_info = ""
    if order_details.get('order_status', '').lower() == 'cancelled':
        if order_details.get('cancellation_reason'):
            cancellation_info = f"This order was cancelled. Reason: {order_details.get('cancellation_reason')}."
        else:
            cancellation_info = "This order was cancelled, but no specific reason was recorded."
        order_summary_text += f"\n{cancellation_info}"


    # Create language instruction based on detected language
    language_instruction = "Respond in Hindi or Hinglish (mix of Hindi and English)." if is_hindi else "Respond in English only."

    # Create AI prompt with FAQ knowledge and specific instructions
    prompt = f"""
    You are a helpful customer service assistant for Bookswagon online bookstore. Your goal is to assist the customer based on their query, the provided order details, and the FAQ knowledge base.

    Order Details:
    ---
    {order_summary_text}
    ---

    FAQ Knowledge Base Snippet (relevant to general queries):
    ---
    {FAQ_KNOWLEDGE}
    ---

    Customer Query: "{user_query}"

    Instructions:
    1. Address the customer's query directly using the provided Order Details and FAQ knowledge.
    2. If the query is about the order status or tracking, provide the relevant information from the Order Details.
    3. If the query is about a cancelled order and a reason is available, state the reason clearly.
    4. If the query is a general question (e.g., about shipping, payment, returns) and the answer is in the FAQ, summarize the relevant point concisely.
    5. If the query cannot be answered with the provided information, politely state that and suggest contacting customer service.
    6. Keep your response concise, ideally under 3 sentences, unless more detail is requested or necessary.
    7. Do NOT attempt to perform actions like cancelling orders.
    8. {language_instruction}

    Provide a helpful and polite response.
    """

    messages = [
        {"role": "system", "content": "You are a customer service assistant for Bookswagon."},
        {"role": "user", "content": prompt}
    ]

    # Query the AI for response. Language is handled by the prompt instructions.
    return query_deepseek(messages)


# --- Flask Routes ---
@app.route('/')
def index():
    # Clear session for a fresh start when accessing the main page
    session.clear()
    # Add initial context/greeting to session
    if 'chat_history' not in session:
        session['chat_history'] = []
        welcome_message = "Hello! How can I assist you with your Bookswagon order today? You can provide your order number or ask a general question."
        session['chat_history'].append({"role": "assistant", "content": welcome_message})
    
    return render_template('index.html', chat_history=session.get('chat_history', []))

@app.route('/api/message', methods=['POST'])
def api_message():
    user_input = request.json.get('message')
    if not user_input:
        return jsonify({"response": "Please enter a message."}), 400

    # Retrieve state from session
    chat_history = session.get('chat_history', [])
    active_order_id = session.get('active_order_id', None)
    active_order_data = session.get('active_order_data', None) # This stores the fetched data

    # Check for exit commands first
    if any(cmd in user_input.lower() for cmd in EXIT_COMMANDS):
        farewell_message = "Thank you for using Bookswagon support. Have a good day!"
        # Detect language before translating farewell
        is_hindi = detect_language(user_input)
        translated_farewell = get_response_in_language(farewell_message, is_hindi)
        
        # Clear session on exit
        session.clear() 
        chat_history.append({"role": "user", "content": user_input}) # Add user's final message
        chat_history.append({"role": "assistant", "content": translated_farewell}) # Add bot's farewell
        
        return jsonify({"response": translated_farewell, "end_chat": True, "chat_history": chat_history})


    # Add user input to history
    chat_history.append({"role": "user", "content": user_input})

    # Detect language for the current user input
    is_hindi = detect_language(user_input)
    # print(f"Debug: User input language: {'Hindi/Hinglish' if is_hindi else 'English'}") # Debugging line


    response_text = ""
    new_active_order_id = None

    # 1. Try to extract a NEW order ID from the current input
    extracted_id = extract_order_id(user_input)

    if extracted_id:
        # A new order ID was found, potentially override previous active order
        new_active_order_id = extracted_id
        order_data = fetch_order_data(new_active_order_id)

        if not order_data:
            # Order not found
            response_text = f"I couldn't find any order with ID {new_active_order_id}. Please check the order number and try again."
            # Keep previous active_order_data/id if any, but don't store the not-found order
            active_order_data = session.get('active_order_data', None)
            active_order_id = session.get('active_order_id', None) # Revert to previous if exists
        else:
            # Order found - set it as the active order
            active_order_id = new_active_order_id
            active_order_data = order_data
            session['active_order_id'] = active_order_id
            session['active_order_data'] = active_order_data # Store the fetched data

            # If the found order is cancelled and the query is about cancellation, respond directly
            order_details = active_order_data.get('order_details', {})
            is_cancellation_query = any(kw in user_input.lower() for kw in ["cancel", "cancelled", "cancellation", "why", "kyu", "kyun", "रद्द"])
            if order_details.get('order_status', '').lower() == 'cancelled' and is_cancellation_query:
                 reason = order_details.get('cancellation_reason')
                 if reason:
                      response_text = f"Your order {active_order_id} was cancelled due to: {reason}."
                 else:
                      response_text = f"Your order {active_order_id} was cancelled, but no specific reason was recorded in our system."
            elif active_order_data['books']:
                # Order found, now determine response based on the query context and number of books
                books = active_order_data['books']
                if len(books) == 1:
                    # Single book order - display details directly
                    response_text = format_single_book_response(active_order_data, 0)
                    # Add a follow-up question
                    follow_up = " Is there anything else you'd like to know about this order?"
                    response_text += follow_up # Append follow-up in English, language model handles translation if needed
                else: # len(books) > 1
                    # Multiple books - display summary and ask for specific book
                    response_text = format_order_response(active_order_data)
                    follow_up = " Which specific book would you like more details about? Please respond with the book number or name."
                    response_text += follow_up # Append follow-up
            else:
                 # Order found, but no books listed (unusual)
                 response_text = f"Your order {active_order_id} was found but doesn't have any products listed. This is unusual. Please contact customer support for assistance."


    elif active_order_data:
        # No new order ID, but there is an active order from a previous interaction
        books = active_order_data.get('books', [])
        order_details = active_order_data.get('order_details', {})

        # Check if user is asking about cancellation for the active order
        is_cancellation_query = any(kw in user_input.lower() for kw in ["cancel", "cancelled", "cancellation", "why", "kyu", "kyun", "रद्द"])
        if is_cancellation_query:
             if order_details.get('order_status', '').lower() == 'cancelled':
                 reason = order_details.get('cancellation_reason')
                 if reason:
                      response_text = f"Your order {active_order_id} was cancelled due to: {reason}."
                 else:
                      response_text = f"Your order {active_order_id} was cancelled, but no specific reason was recorded in our system."
             else:
                  response_text = f"Your order {active_order_id} is not cancelled. Its current status is: {order_details.get('order_status')}."

        # Check if user is selecting a specific book from a multi-book order
        elif len(books) > 1:
            book_index = -1
            try:
                # Try to match by number first
                if user_input.isdigit():
                    num = int(user_input)
                    if 1 <= num <= len(books):
                        book_index = num - 1
            except ValueError:
                pass # Not a number, try matching by name

            if book_index == -1: # If not matched by number, try matching by name
                user_input_lower = user_input.lower()
                for i, book in enumerate(books):
                    if user_input_lower in book['product_name'].lower():
                        book_index = i
                        break # Take the first match

            if book_index >= 0:
                # Found a matching book
                response_text = format_single_book_response(active_order_data, book_index)
            else:
                # User input wasn't a book selection or cancellation query for the active order
                # Use AI to generate a response based on the active order and the new query
                 response_text = generate_order_summary_ai(active_order_data, user_input, is_hindi)

        else:
            # Active order has 1 or 0 books, and the query isn't cancellation specific or book selection
            # Use AI to generate a response based on the active order and the new query
             response_text = generate_order_summary_ai(active_order_data, user_input, is_hindi)

    else:
        # No order ID found in the current input, and no active order in session
        # Treat as a general query, using conversation history and FAQ
        # Prepare messages for the AI model, including system prompt and context
        messages_for_ai = [{"role": "system", "content": f"""
        You are a helpful customer service assistant for Bookswagon, an online bookstore.
        Respond to customer queries about general information or their orders if an order number is provided in the conversation history or current message.
        
        Use the following FAQ knowledge to answer general questions:
        ---
        {FAQ_KNOWLEDGE}
        ---
        
        If the query is about an order, you must ask for the order number (e.g., "Could you please provide your order number (like UR1234567890) so I can assist you?") unless one is already in the conversation history.
        Do NOT hallucinate order details if no order number is known.
        Keep your responses concise.
        
        Respond in Hindi or Hinglish ONLY if the user's message contains Hindi words or is in Hinglish. Otherwise, always respond in English only.
        """}]
        # Add recent conversation history (limit to prevent context window issues)
        messages_for_ai.extend(chat_history[-5:]) # Use last 5 messages as context

        # Add the current user message to the context for the AI
        messages_for_ai.append({"role": "user", "content": user_input})

        response_text = query_deepseek(messages_for_ai)

        # The general query AI call needs explicit translation if input was Hindi/Hinglish
        # The generate_order_summary_ai function handles translation internally.
        if not active_order_data and not extracted_id: # Only translate if it was a general query handled by the main AI prompt
             response_text = get_response_in_language(response_text, is_hindi)


    # If a response was generated directly (not by the AI summary function which handles language)
    # ensure it is translated if needed. This catches the specific cancellation reason messages etc.
    if 'generate_order_summary_ai' not in response_text and 'format_order_response' not in response_text and 'format_single_book_response' not in response_text:
         # This is a bit of a heuristic to check if a specific formatting function was called.
         # A more robust way might be to have these functions return structured data
         # and format/translate at the very end. But for this structure, we check.
         # Simple direct responses need translation.
         if response_text and not ('**Order Details**' in response_text or '**Details for**' in response_text):
              response_text = get_response_in_language(response_text, is_hindi)


    # Add bot response to history
    chat_history.append({"role": "assistant", "content": response_text})
    session['chat_history'] = chat_history

    # Return the response and updated history
    return jsonify({"response": response_text, "chat_history": chat_history})

# --- Run the Flask App ---
if __name__ == '__main__':
    # Set environment variables if not using a .env file
    # os.environ['DEEPSEEK_API_KEY'] = 'YOUR_API_KEY'
    # os.environ['DB_SERVER'] = 'your_server_name'
    # os.environ['DB_DATABASE'] = 'your_db_name'
    # os.environ['DB_UID'] = 'your_user_id'
    # os.environ['DB_PWD'] = 'your_password'
    
    # In production, use a production-ready web server like Gunicorn or uWSGI
    # app.run(debug=True) # debug=True is good for development
    app.run(host='0.0.0.0', port=5000) # Listen on all interfaces