import pyodbc
import requests
import os
import re
from datetime import datetime
import threading # Keep threading if you plan background tasks, otherwise optional
from flask import Flask, render_template, request, jsonify, session
import uuid
import json

# --- Create Flask App ---
app = Flask(__name__)
# Replace with a strong, securely generated key, ideally from environment variables
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'bookswagon_secret_key_2025_replace_me')

# --- Configuration ---
# Load sensitive keys from environment variables for security
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', 'YOUR_DEEPSEEK_API_KEY') # Placeholder
DEEPSEEK_MODEL = "deepseek-chat" # Update to specific model name if needed

# Database placeholder credentials (load securely!)
DB_DRIVER = '{SQL Server}'
DB_SERVER_ENV = os.environ.get('DB_SERVER', 'YOUR_SERVER_IP_OR_NAME') # Placeholder
DB_DATABASE_ENV = os.environ.get('DB_DATABASE', 'BooksBay') # Placeholder from your code
DB_UID_ENV = os.environ.get('DB_USER', 'YOUR_DB_USER') # Placeholder
DB_PWD_ENV = os.environ.get('DB_PASSWORD', 'YOUR_DB_PASSWORD') # Placeholder

# --- Exit Commands ---
EXIT_COMMANDS = ["exit", "quit", "bye", "goodbye", "thanks", "thank you", "धन्यवाद", "अलविदा", "बाय", "tata", "ta ta", "ok bye", "close"]

# --- FAQ Knowledge Base ---
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

# --- Database Functions ---
def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        conn_str = (
            f'DRIVER={{{DB_DRIVER}}};' # Note the double braces for literal braces in f-string
            f'SERVER={DB_SERVER_ENV};'
            f'DATABASE={DB_DATABASE_ENV};'
            f'UID={DB_UID_ENV};'
            f'PWD={DB_PWD_ENV};'
        )
        # print(f"Attempting DB connection to SERVER={DB_SERVER_ENV}, DATABASE={DB_DATABASE_ENV} with UID={DB_UID_ENV}") # Debug

        # Add a connection timeout
        connection = pyodbc.connect(conn_str, timeout=5)
        cursor = connection.cursor()
        # print("DB connection successful.") # Optional success message
        return connection, cursor
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        print(f"Database connection error (pyodbc State: {sqlstate}):")
        print(ex)
        return None, None
    except Exception as e:
        print(f"Unexpected database connection error: {e}")
        return None, None

def fetch_order_data(cursor, order_id):
    """Fetches all order information using the comprehensive query."""
    # Validate order_id format roughly before querying
    if not order_id or not isinstance(order_id, str) or len(order_id) < 5:
         print(f"Invalid order ID format provided: {order_id}")
         return None
    try:
        # Ensure you are using the correct View and Table names for your database
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
            FROM View_GetOrderDetailListUpdatedNew v1 WITH (NOLOCK) /* Consider NOLOCK carefully */
            INNER JOIN Table_OrderSummary os WITH (NOLOCK) ON v1.Order_Number = os.Order_Number
            LEFT JOIN Table_OrderCancellationReason oc WITH (NOLOCK) ON os.ID_CancellationReason = oc.ID_OrderCancellationReason
            INNER JOIN Table_OrderShippingAddress sa WITH (NOLOCK) ON os.ID_OrderSummary = sa.ID_OrderSummary
            -- Using INNER JOIN for v2 if product details are essential per row,
            -- Or LEFT JOIN if an order row might exist without a product match in v2
            INNER JOIN View_Order_Customer_Product v2 WITH (NOLOCK) ON v1.Order_Number = v2.Order_Number
            WHERE v1.Order_Number = ?;
        """
        # Using OUTER APPLY can sometimes be less efficient than JOINs if v2 always matches.
        # Test performance with JOIN vs OUTER APPLY if needed.
        # The previous OUTER APPLY version:
        # OUTER APPLY (
        #     SELECT Product_Title, ISBN13
        #     FROM View_Order_Customer_Product v2 WITH (NOLOCK)
        #     WHERE v2.Order_Number = v1.Order_Number
        # ) v2

        cursor.execute(query, (order_id,))
        results = cursor.fetchall()

        if not results:
            print(f"No results found for Order ID: {order_id}")
            return None

        # Extract order details (common to all rows - assumes these are consistent)
        # Check results[0] has enough columns before accessing
        if len(results[0]) < 19:
             print(f"Error: Unexpected number of columns ({len(results[0])}) returned for order {order_id}.")
             return None

        order_details = {
            'order_number': results[0][0],
            'order_summary_id': results[0][1],
            'purchase_date': results[0][4],
            'promise_date': results[0][5],
            'order_status': results[0][6],
            'cancellation_reason': results[0][7], # Store cancellation reason
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
            'tracking_number': results[0][18] # Assuming tracking is same for all parts?
        }

        # Extract distinct books/products
        books = {} # Use dict to avoid duplicates based on ISBN or Title
        for row in results:
             if len(row) > 3 and row[2]: # Check Product title exists and row length
                 # Create a unique key, e.g., ISBN or title if ISBN missing
                 book_key = row[3] if row[3] else row[2]
                 if book_key not in books:
                     books[book_key] = {
                         'product_name': row[2],
                         'isbn': row[3],
                         'tracking_number': row[18] # This might be product specific if query changes
                     }

        return {
            'order_details': order_details,
            'books': list(books.values()) # Convert back to list
        }
    except pyodbc.Error as db_err:
         print(f"Database query error for order {order_id}: {db_err}")
         return None
    except Exception as e:
        print(f"Error processing fetched order data for {order_id}: {e}")
        return None


# --- DeepSeek API Function ---
def query_deepseek(messages, temperature=0.1, max_retries=2):
    """Send messages to DeepSeek API and return the response with retries."""
    attempt = 0
    while attempt <= max_retries:
        attempt += 1
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
                "max_tokens": 1024 # Adjust as needed
            }
            response = requests.post(url, headers=headers, json=payload, timeout=20) # Added timeout
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

            response_data = response.json()
            if response_data and "choices" in response_data and response_data["choices"]:
                choice = response_data["choices"][0]
                if choice and "message" in choice and "content" in choice["message"]:
                     return choice["message"]["content"]
                else:
                     print(f"Warning: Unexpected DeepSeek response structure (choice/message): {choice}")
            else:
                print(f"Warning: Unexpected DeepSeek response structure (choices): {response_data}")

            return "Sorry, I received an unexpected response from the AI. Could you rephrase?" # Fallback

        except requests.exceptions.Timeout:
             print(f"Error: DeepSeek API request timed out (Attempt {attempt}/{max_retries+1}).")
             if attempt > max_retries:
                 return "I'm having trouble connecting right now due to a timeout. Please try again later."
        except requests.exceptions.RequestException as e:
            print(f"Error with DeepSeek API (Attempt {attempt}/{max_retries+1}): {e}")
            # Check for specific status codes if needed (e.g., 401 Unauthorized, 429 Rate Limit)
            if attempt > max_retries:
                return "I'm having trouble connecting right now. Please try again."
        except Exception as e:
             print(f"Unexpected error during DeepSeek query (Attempt {attempt}/{max_retries+1}): {e}")
             if attempt > max_retries:
                 return "An unexpected error occurred while contacting the AI. Please try again."
        # Optional: time.sleep(1) # Wait before retrying

    return "I'm having trouble reaching the AI service after multiple attempts. Please try again later."


def extract_order_id(text):
    """Extract a Bookswagon order ID (UR or BW format) from text."""
    # Prioritize specific formats with expected lengths first
    # BW + 12 digits (adjust length if needed)
    pattern_bw = r'\b([Bb][Ww]\d{12})\b'
    match_bw = re.search(pattern_bw, text, re.IGNORECASE)
    if match_bw:
        return match_bw.group(0).upper()

    # UR + 10+ digits (adjust length if needed)
    pattern_ur = r'\b([Uu][Rr]\d{10,})\b'
    match_ur = re.search(pattern_ur, text, re.IGNORECASE)
    if match_ur:
        return match_ur.group(0).upper()

    # General BW/UR followed by digits if specific lengths fail
    pattern_general = r'\b([Bb][Ww]\d+)\b|\b([Uu][Rr]\d+)\b'
    match_general = re.search(pattern_general, text, re.IGNORECASE)
    if match_general:
        # Return the first matched group that's not None
        return next(g for g in match_general.groups() if g is not None).upper()

    # --- AI Fallback (Use sparingly due to cost/latency) ---
    # Consider if AI extraction is truly needed or if regex covers most cases
    # ai_extract_enabled = False # Set to True to enable AI fallback
    # if ai_extract_enabled:
    #     print("Info: Using AI to extract Order ID.")
    #     messages = [
    #         {"role": "system", "content": "Extract a Bookswagon order ID (starts with UR or BW followed by digits) from the user text. Return only the ID (e.g., BW123456789012 or UR1234567890) or the word 'None'."},
    #         {"role": "user", "content": f"Extract order ID from this text: \"{text}\""}
    #     ]
    #     result = query_deepseek(messages, temperature=0.0).strip() # Zero temp for extraction
    #     # Validate AI result format
    #     if result.upper() != "NONE" and (re.match(r'^(BW|UR)\d+$', result, re.IGNORECASE)):
    #         print(f"Info: Order ID extracted by AI: {result.upper()}")
    #         return result.upper()
    #     else:
    #         print(f"Info: AI could not extract a valid Order ID (Result: {result}).")

    return None # Return None if no ID found by regex (and AI if enabled)


def format_order_response(order_data):
    """Format full order details for display."""
    # This function provides a simple text dump.
    # Consider using the generate_order_summary for natural language.
    if not order_data:
        return "Order details not found."

    order_details = order_data['order_details']
    books = order_data['books']

    # Format dates safely
    def format_date(date_obj):
        if isinstance(date_obj, datetime):
            return date_obj.strftime("%d %b %Y") # E.g., 18 Apr 2025
        elif date_obj:
            return str(date_obj) # Return as string if not datetime
        return "N/A"

    purchase_date = format_date(order_details.get('purchase_date'))
    promise_date = format_date(order_details.get('promise_date'))

    response_lines = [
        f"--- Order Summary ({order_details.get('order_number', 'N/A')}) ---",
        f"Customer: {order_details.get('customer_name', 'N/A')}",
        f"Purchased: {purchase_date}",
        f"Expected Delivery: {promise_date}",
        f"Status: {order_details.get('order_status', 'N/A')}",
        f"Payment: {order_details.get('payment_status', 'N/A')}",
        f"Amount: {order_details.get('order_amount', 'N/A')}",
        f"Tracking: {order_details.get('tracking_number') or 'Not yet available'}",
    ]

    if order_details.get('order_status', '').lower() == 'cancelled' and order_details.get('cancellation_reason'):
        response_lines.append(f"Cancellation Reason: {order_details.get('cancellation_reason')}")

    response_lines.extend([
        "\n--- Shipping Details ---",
        f"{order_details.get('shipping_address', 'N/A')}",
        f"{order_details.get('shipping_city', '')}, {order_details.get('shipping_state', '')} {order_details.get('shipping_zip', '')}",
        f"{order_details.get('shipping_country', '')}",
        f"Mobile: {order_details.get('shipping_mobile', 'N/A')}",
        "\n--- Products ---"
    ])

    if books:
        for i, book in enumerate(books, 1):
            response_lines.append(f"{i}. {book['product_name']} (ISBN: {book['isbn'] or 'N/A'})")
    else:
        response_lines.append("No products listed for this order.")

    return "\n".join(response_lines)


def format_single_book_response(order_data, book_index):
    """Format response for a single book within an order."""
    # This function provides a simple text dump.
    # Consider using generate_order_summary tailored for single book.
    if not order_data or not order_data.get('books') or book_index >= len(order_data['books']):
        return "Book details not found for the specified item."

    order_details = order_data['order_details']
    book = order_data['books'][book_index]

    def format_date(date_obj):
         if isinstance(date_obj, datetime):
             return date_obj.strftime("%d %b %Y")
         elif date_obj:
             return str(date_obj)
         return "N/A"

    purchase_date = format_date(order_details.get('purchase_date'))
    promise_date = format_date(order_details.get('promise_date'))

    # Tracking might be per book or per order, adjust based on `Workspace_order_data` logic
    # Assuming tracking_number in book dict if available per book, else use order level
    tracking_num = book.get('tracking_number') or order_details.get('tracking_number') or 'Not available'

    response_lines = [
        f"--- Details for Item in Order {order_details.get('order_number', 'N/A')} ---",
        f"Product: {book['product_name']}",
        f"ISBN: {book['isbn'] or 'N/A'}",
        f"Order Status: {order_details.get('order_status', 'N/A')}", # Status usually applies to whole order or shipment part
        f"Expected Delivery: {promise_date}",
        f"Tracking: {tracking_num}",
        f"Payment Status: {order_details.get('payment_status', 'N/A')}",
    ]

    if order_details.get('order_status', '').lower() == 'cancelled' and order_details.get('cancellation_reason'):
        response_lines.append(f"Cancellation Reason: {order_details.get('cancellation_reason')}")

    return "\n".join(response_lines)


def detect_language(text):
    """Detect if text likely contains Hindi/Hinglish using AI. Fallback to english."""
    # Simple heuristic: Check for Devanagari script characters
    if any('\u0900' <= char <= '\u097f' for char in text):
        # print("Info: Detected Hindi script.")
        return True # Directly return True if Hindi script found

    # Use AI for more nuanced detection (Hinglish) if no script found
    # Reduce API calls: Only call AI if text seems potentially non-English
    # Very basic check: Presence of common Hinglish words or non-ASCII chars (excluding common punctuation)
    potential_non_english = False
    common_hinglish = ['mera', 'kya', 'kyu', 'kab', 'kaise', 'kar', 'hai', 'nahi', 'order', 'book'] # Add more
    if not text.isascii() or any(word in text.lower() for word in common_hinglish):
         potential_non_english = True

    if not potential_non_english:
        # print("Info: Assuming English based on basic check.")
        return False

    # print("Info: Potential non-English, checking with AI...")
    prompt = f"""Analyze the following text. Does it contain Hindi words mixed with English (Hinglish), or is it purely English?

    Text: "{text}"

    Return ONLY the word 'hindi' if it contains Hindi or Hinglish. Otherwise, return ONLY the word 'english'."""

    try:
        # Use low temperature for classification
        result = query_deepseek([{"role": "user", "content": prompt}], temperature=0.1).strip().lower()
        if result not in ['hindi', 'english']:
             print(f"Warning: Unexpected lang detect result '{result}'. Defaulting English.")
             return False
        # print(f"Info: AI language detection result: {result}")
        return result == "hindi"
    except Exception as e:
        print(f"Error during AI language detection: {e}. Defaulting to English.")
        return False # Default to False (English) on error


def get_response_in_language(response, is_hindi):
    """Translate or adjust the response based on the detected language. Fallback to English."""
    if not is_hindi:
        return response # Return original English if not Hindi detected

    # print(f"Info: Translating response to Hindi/Hinglish: {response[:50]}...")
    translation_prompt = f"""Translate the following English customer service response to conversational Hindi or Hinglish (a natural mix of Hindi and English). Adapt it to sound like a helpful support agent.

    English Response:
    "{response}"

    Provide ONLY the translated text."""
    try:
        # Use a slightly higher temperature for more natural translation
        translated_response = query_deepseek([{"role": "user", "content": translation_prompt}], temperature=0.5).strip()
        if translated_response:
            # print(f"Debug: Translated response: {translated_response[:50]}...")
            return translated_response
        else:
            print("Warning: Translation returned empty response. Using original.")
            return response # Fallback to English
    except Exception as e:
        print(f"Error translating response: {e}")
        return response # Fallback to English response


def generate_order_summary(order_data, user_query, is_hindi):
    """Generate a natural language response about the order using AI and FAQ."""
    if not order_data:
        # Should not happen if called correctly, but handle defensively
        return get_response_in_language("I couldn't retrieve the details for that order.", is_hindi)

    order_details = order_data['order_details']
    books = order_data['books']

    # Format dates safely
    def format_date(date_obj):
        if isinstance(date_obj, datetime): return date_obj.strftime("%d %b %Y")
        elif date_obj: return str(date_obj)
        return "N/A"

    purchase_date = format_date(order_details.get('purchase_date'))
    promise_date = format_date(order_details.get('promise_date'))

    # Prepare a concise summary for the AI context
    order_summary_context = {
        "Order Number": order_details.get('order_number'),
        "Purchase Date": purchase_date,
        "Expected Delivery": promise_date,
        "Status": order_details.get('order_status'),
        "Payment Status": order_details.get('payment_status'),
        "Tracking": order_details.get('tracking_number') or "Not yet available",
        "Products": [book['product_name'] for book in books]
    }

    # Add cancellation reason specifically if relevant
    cancellation_reason = ""
    if order_details.get('order_status', '').lower() == 'cancelled':
        cancellation_reason = f"Cancellation Reason: {order_details.get('cancellation_reason', 'Not specified')}"

    # Determine primary user question type (status, tracking, cancellation, general)
    query_lower = user_query.lower()
    query_type = "general"
    if any(kw in query_lower for kw in ["status", "where is", "kab tak", "kahan hai"]): query_type = "status"
    if any(kw in query_lower for kw in ["track", "tracking"]): query_type = "tracking"
    if any(kw in query_lower for kw in ["cancel", "cancelled", "रद्द", "kyu", "why"]): query_type = "cancellation"

    # Language instruction for AI
    lang_instruct = "Respond in Hindi or Hinglish." if is_hindi else "Respond in English."

    # AI Prompt Construction
    prompt = f"""You are 'Paige', a helpful Bookswagon support agent.
Use the provided Order Details and FAQ Knowledge to answer the customer's query concisely and accurately.
{lang_instruct}

FAQ Knowledge (Use relevant parts):
{FAQ_KNOWLEDGE}

Order Details:
{json.dumps(order_summary_context, indent=2)}
{cancellation_reason}

Customer Query: "{user_query}"

Instructions:
- Directly answer the customer's specific question based on their query type ({query_type}).
- If query is about cancellation ({query_type == 'cancellation'}) and the order IS cancelled, state the cancellation reason from the details. If no reason is available, say so.
- If query is about cancellation ({query_type == 'cancellation'}) and the order IS NOT cancelled, state the current status and briefly mention the cancellation policy from the FAQ (must be done before shipping via account/support).
- If query is about status ({query_type == 'status'}), provide the current 'Status' from the order details.
- If query is about tracking ({query_type == 'tracking'}), provide the 'Tracking' number if available, mention it's 'Not yet available' if null/empty, or refer to the 'Shipped' status from the FAQ if applicable.
- For general queries about the order, provide the most relevant information (like status and expected delivery).
- Keep the response brief (1-3 sentences usually).
- If the order details clearly contradict the user's premise (e.g., asking why cancelled when it's shipped), politely state the actual status.
- Do not offer to perform actions like cancellation yourself.

Response:"""

    messages = [
        # System prompt defines the persona and general task
        {"role": "system", "content": "You are 'Paige', a Bookswagon customer support assistant. You answer user queries based on provided order details and FAQ knowledge."},
        # User prompt contains the specifics for this query
        {"role": "user", "content": prompt}
    ]

    # Query the AI
    ai_response = query_deepseek(messages, temperature=0.3) # Slightly more flexible temperature

    # Although the prompt asks AI to respond in the correct language,
    # we explicitly translate here as a fallback or primary method if needed.
    # If the AI consistently follows the language instruction, this outer translation might be redundant.
    # return get_response_in_language(ai_response, is_hindi)
    return ai_response # Trusting AI's language instruction for now


# --- Session Management ---
def get_session_data():
    """Get current session data or initialize new session"""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        session['context'] = [] # Stores limited history: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        session['active_order_data'] = None
        session['active_order_id'] = None
        session['last_lang_is_hindi'] = False # Track language preference
    # Ensure keys exist even if session was created before adding new keys
    context = session.setdefault('context', [])
    active_order_data = session.setdefault('active_order_data', None)
    active_order_id = session.setdefault('active_order_id', None)
    last_lang_is_hindi = session.setdefault('last_lang_is_hindi', False)

    return context, active_order_data, active_order_id, last_lang_is_hindi


def update_session_data(context, active_order_data, active_order_id, last_lang_is_hindi):
    """Update session with latest conversation data"""
    # Limit context size to avoid overly large sessions/API calls
    MAX_CONTEXT = 6 # Keep last 3 user/assistant pairs
    session['context'] = context[-MAX_CONTEXT:]
    session['active_order_data'] = active_order_data
    session['active_order_id'] = active_order_id
    session['last_lang_is_hindi'] = last_lang_is_hindi
    session.modified = True # Ensure session is saved


# --- API Routes ---
@app.route('/')
def index():
    """Serve the main chat interface"""
    # Clear session on new page load? Optional.
    # session.clear()
    return render_template('index.html')


@app.route('/api/message', methods=['POST'])
def process_message():
    """Process incoming chat messages"""
    connection, cursor = None, None # Initialize
    try:
        data = request.json
        user_input = data.get('message', '').strip()
        if not user_input:
            return jsonify({"response": "Please enter a message.", "follow_up": None})

        # Get session data
        context, active_order_data, active_order_id, last_lang_is_hindi = get_session_data()

        response = "Sorry, I couldn't process that. Can you rephrase?" # Default fallback
        follow_up = None
        query_resolved_this_turn = False # Track if we provided a definitive answer

        # --- Core Logic ---
        # 1. Detect Language
        is_hindi = detect_language(user_input)
        last_lang_is_hindi = is_hindi # Update session language preference

        # 2. Check for Exit Commands
        if any(cmd in user_input.lower() for cmd in EXIT_COMMANDS):
            farewell_message = "Thank you for using Bookswagon support! Goodbye."
            response = get_response_in_language(farewell_message, is_hindi)
            session.clear() # Clear session on exit
            return jsonify({"response": response, "follow_up": None})

        # 3. Update context (user message)
        context.append({"role": "user", "content": user_input})

        # 4. Extract Order ID
        order_id_extracted = extract_order_id(user_input)

        # 5. Database Interaction (only if needed)
        if order_id_extracted or (not active_order_data and active_order_id):
             # Fetch data if new ID found, or if we have an ID but no data loaded
            connection, cursor = get_db_connection()
            if not connection or not cursor:
                return jsonify({"response": "System error: Unable to connect to the database.", "follow_up": None})

            current_target_id = order_id_extracted if order_id_extracted else active_order_id
            print(f"Fetching data for Order ID: {current_target_id}")
            fetched_data = fetch_order_data(cursor, current_target_id)

            if fetched_data:
                 active_order_id = current_target_id # Update active ID only if fetch successful
                 active_order_data = fetched_data
                 print(f"Data fetched successfully for {active_order_id}")
            elif order_id_extracted: # Only respond if user provided a new, invalid ID
                 response_text = f"I couldn't find order details for ID {order_id_extracted}. Please check the number."
                 response = get_response_in_language(response_text, is_hindi)
                 active_order_id = None # Clear active ID if lookup failed
                 active_order_data = None
                 query_resolved_this_turn = True # We answered the ID lookup request

        # 6. Generate Response based on context and data
        if not query_resolved_this_turn: # Only generate if not already handled (e.g., bad order ID)
            if active_order_data:
                # Generate summary based on order data and user query
                response = generate_order_summary(active_order_data, user_input, is_hindi)
                query_resolved_this_turn = True
            else:
                 # No active order - use general knowledge / FAQ
                 system_prompt = f"""You are 'Paige', a customer service assistant for Bookswagon. Respond to general inquiries using the FAQ Knowledge. If asked about orders, ask for the Order ID. {('Respond in Hindi/Hinglish.' if is_hindi else 'Respond in English.')}

                 FAQ Knowledge:
                 {FAQ_KNOWLEDGE}"""
                 # Keep limited context for general chat
                 messages_for_ai = [{"role": "system", "content": system_prompt}]
                 messages_for_ai.extend(context[-3:]) # Last user message + potentially previous turn
                 response = query_deepseek(messages_for_ai, temperature=0.5)
                 query_resolved_this_turn = True # General query is considered handled

        # 7. Add Assistant Response to Context
        context.append({"role": "assistant", "content": response})

        # 8. Determine Follow-up (Optional)
        # Simple follow-up after providing specific order info
        if query_resolved_this_turn and active_order_data:
             follow_up_text = "Is there anything else I can help you with regarding this order?"
             follow_up = get_response_in_language(follow_up_text, is_hindi)
             # Append follow-up to context *if* you want the LLM to be aware of it next turn
             # context.append({"role": "assistant", "content": follow_up})


        # 9. Update Session
        update_session_data(context, active_order_data, active_order_id, last_lang_is_hindi)

        # 10. Return Response
        return jsonify({"response": response, "follow_up": follow_up})

    except Exception as e:
        print(f"Error processing message: {e}")
        # Log the full exception traceback here in production for debugging
        import traceback
        traceback.print_exc()
        # Provide a generic error to the user
        error_msg = "I'm sorry, an unexpected error occurred. Please try again."
        # Attempt to translate error message if language was detected
        try:
            error_lang = detect_language(user_input) # Re-detect just in case
            final_error_msg = get_response_in_language(error_msg, error_lang)
        except:
            final_error_msg = error_msg # Fallback if translation fails
        return jsonify({"response": final_error_msg, "follow_up": None}), 500 # Internal Server Error status

    finally:
        # Ensure DB connection is closed
        if cursor:
            cursor.close()
        if connection:
            connection.close()
            # print("DB connection closed.") # Optional debug


@app.route('/api/reset', methods=['POST'])
def reset_session():
    """Reset the user's session"""
    session.clear()
    print("Session cleared by user.")
    return jsonify({"status": "success", "message": "Session reset successfully"})


# --- Function to Create Frontend Files ---
# (Keep the create_templates_and_static function as previously defined)
def create_templates_and_static():
    """Create necessary templates and static files for the application"""
    templates_dir = 'templates'
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
        print(f"Created directory: {templates_dir}")

    index_html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bookswagon Customer Support</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        .chat-container {
            height: calc(100vh - 150px); max-height: 70vh; display: flex; flex-direction: column;
        }
        .message-container { flex-grow: 1; overflow-y: auto; padding: 1rem; }
        .message-wrapper { display: flex; flex-direction: column; margin-bottom: 0.5rem; }
        .user-message { background-color: #DCF8C6; border-radius: 18px 18px 0 18px; align-self: flex-end; margin-left: auto; }
        .bot-message { background-color: #f1f0f0; border-radius: 18px 18px 18px 0; align-self: flex-start; margin-right: auto; }
        .message { max-width: 85%; padding: 10px 15px; word-wrap: break-word; white-space: pre-line; font-size: 0.95rem; line-height: 1.4; }
        .typing-indicator { display: none; padding: 10px 15px; align-self: flex-start; }
        .typing-indicator span { height: 8px; width: 8px; background-color: #9ca3af; border-radius: 50%; display: inline-block; margin: 0 2px; animation: bounce 1.4s infinite ease-in-out both; }
        .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
        .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1.0); } }
        .input-area { padding: 1rem; border-top: 1px solid #e5e7eb; }
        /* Scrollbar styling */
        .message-container::-webkit-scrollbar { width: 8px; }
        .message-container::-webkit-scrollbar-track { background: #f1f1f1; }
        .message-container::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }
        .message-container::-webkit-scrollbar-thumb:hover { background: #999; }
    </style>
</head>
<body class="bg-gray-100 flex flex-col items-center justify-center min-h-screen p-4">
    <div class="w-full max-w-2xl bg-white rounded-lg shadow-xl chat-container">
        <header class="bg-blue-600 text-white p-4 rounded-t-lg flex justify-between items-center">
            <h1 class="text-xl font-semibold">Bookswagon Support</h1>
            <button id="resetButton" title="Reset Chat Session" class="bg-red-500 hover:bg-red-600 text-white text-xs font-bold py-1 px-2 rounded">
                Reset Chat
            </button>
        </header>
        <div id="chatbox" class="message-container">
            <div class="message-wrapper">
                <div class="bot-message message">
                    Hello! How can I help you with your Bookswagon order today?
                </div>
            </div>
        </div>
        <div id="typing-indicator" class="typing-indicator">
            <span></span><span></span><span></span>
        </div>
        <div class="input-area flex items-center">
            <input type="text" id="userInput" class="flex-grow border rounded-l-md p-2 focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Type your message...">
            <button id="sendButton" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-r-md">Send</button>
        </div>
    </div>
    <script>
        const chatbox = document.getElementById('chatbox');
        const userInput = document.getElementById('userInput');
        const sendButton = document.getElementById('sendButton');
        const resetButton = document.getElementById('resetButton');
        const typingIndicator = document.getElementById('typing-indicator');

        function escapeHtml(unsafe) {
             // Basic escaping, consider a library for production
             if (typeof unsafe !== 'string') return '';
             return unsafe
                  .replace(/&/g, "&amp;")
                  .replace(/</g, "&lt;")
                  .replace(/>/g, "&gt;")
                  .replace(/"/g, "&quot;")
                  .replace(/'/g, "&#039;");
        }

        function addMessage(message, sender = 'bot') {
            const messageWrapper = document.createElement('div');
            messageWrapper.classList.add('message-wrapper');
            const messageDiv = document.createElement('div');
            messageDiv.classList.add('message');
            messageDiv.classList.add(sender === 'user' ? 'user-message' : 'bot-message');
            // Use basic escaping instead of textContent to allow line breaks from \n
            messageDiv.innerHTML = escapeHtml(message).replace(/\n/g, '<br>');
            messageWrapper.appendChild(messageDiv);
            chatbox.appendChild(messageWrapper);
            chatbox.scrollTop = chatbox.scrollHeight;
        }

        function showTyping(show = true) {
            typingIndicator.style.display = show ? 'flex' : 'none'; // Use flex for alignment
            if (show) {
                chatbox.scrollTop = chatbox.scrollHeight;
            }
        }

        async function sendMessage() {
            const messageText = userInput.value.trim();
            if (!messageText) return;
            addMessage(messageText, 'user');
            userInput.value = '';
            showTyping(true);
            userInput.disabled = true; // Disable input while processing
            sendButton.disabled = true;

            try {
                const response = await fetch('/api/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', },
                    body: JSON.stringify({ message: messageText }),
                });
                showTyping(false);
                if (!response.ok) {
                     const errorData = await response.json().catch(() => ({ response: "An unknown error occurred on the server." }));
                     throw new Error(errorData.response || `HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                if (data.response) { addMessage(data.response, 'bot'); }
                if (data.follow_up) {
                    setTimeout(() => addMessage(data.follow_up, 'bot'), 300);
                }
            } catch (error) {
                showTyping(false);
                console.error('Error sending message:', error);
                addMessage(error.message || 'Sorry, I encountered an error. Please try again.', 'bot');
            } finally {
                 userInput.disabled = false; // Re-enable input
                 sendButton.disabled = false;
                 userInput.focus(); // Set focus back to input
            }
        }

        async function resetChat() {
             const confirmed = confirm("Are you sure you want to reset the chat session?");
             if (!confirmed) return;
            try {
                const response = await fetch('/api/reset', { method: 'POST' });
                if (response.ok) {
                    chatbox.innerHTML = '';
                    addMessage('Session reset. How can I assist you now?', 'bot');
                    console.log('Session reset successfully');
                } else { throw new Error('Failed to reset session'); }
            } catch (error) {
                console.error('Error resetting session:', error);
                addMessage('Could not reset the session. Please refresh the page.', 'bot');
            }
        }

        sendButton.addEventListener('click', sendMessage);
        userInput.addEventListener('keypress', (event) => { if (event.key === 'Enter') { sendMessage(); } });
        resetButton.addEventListener('click', resetChat);
        userInput.focus(); // Initial focus
    </script>
</body>
</html>
"""
    index_file_path = os.path.join(templates_dir, 'index.html')
    try:
        with open(index_file_path, 'w', encoding='utf-8') as f:
            f.write(index_html_content)
        print(f"Created/Updated file: {index_file_path}")
    except IOError as e:
        print(f"Error writing {index_file_path}: {e}")


# --- Main Execution ---
if __name__ == '__main__':
    # Ensure API key and DB creds are set (using placeholders here)
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == 'YOUR_DEEPSEEK_API_KEY':
        print("Warning: DEEPSEEK_API_KEY not set or is a placeholder.")
    if DB_SERVER_ENV == 'YOUR_SERVER_IP_OR_NAME' or DB_UID_ENV == 'YOUR_DB_USER' or DB_PWD_ENV == 'YOUR_DB_PASSWORD':
        print("Warning: Database credentials seem to be placeholders.")
        print("Please set DB_SERVER, DB_USER, DB_PASSWORD environment variables or update script.")

    # Create frontend files if they don't exist
    create_templates_and_static()

    # Run the Flask app
    print("Starting Flask server...")
    # Use debug=False in production for security and performance
    # host='0.0.0.0' makes it accessible on your local network
    app.run(debug=False, host='0.0.0.0', port=5000)
