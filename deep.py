import pyodbc
import requests
import os
import re
from datetime import datetime

# --- Configuration ---
DEEPSEEK_API_KEY = "sk-d93b060eda3647fda2f72cf4029ff7a5"
DEEPSEEK_MODEL = "deepseek-chat"  # Update to specific model name if needed

# --- Exit Commands ---
EXIT_COMMANDS = ["exit", "quit", "bye", "goodbye", "thanks", "thank you", "धन्यवाद", "अलविदा", "बाय", "tata", "ta ta"]

# --- Database Functions ---
def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        conn_str = 'DRIVER={SQL Server};SERVER=192.168.4.31;DATABASE=Bookswagon;UID=sa;PWD=U2canb$$;'
        
        connection = pyodbc.connect(conn_str) 
        cursor = connection.cursor()
        return connection, cursor
    except Exception as e:
        print(f"Database connection error: {e}")
        return None, None

def fetch_order_data(cursor, order_id):
    """Fetches all order information using the new comprehensive query."""
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
            JOIN Table_OrderShippingAddress sa ON os.ID_OrderSummary = sa.ID_OrderSummary
            OUTER APPLY (
                SELECT distinct Product_Title, ISBN13
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
            'payment_status': results[0][7],
            'order_amount': results[0][8],
            'customer_email': results[0][9],
            'customer_name': results[0][10],
            'shipping_address': results[0][11],
            'shipping_city': results[0][12],
            'shipping_country': results[0][13],
            'shipping_state': results[0][14],
            'shipping_zip': results[0][15],
            'shipping_mobile': results[0][16],
            'tracking_number': results[0][17]
        }
        
        # Extract books/products
        books = []
        for row in results:
            if row[2]:  # Product title exists
                books.append({
                    'product_name': row[2],
                    'isbn': row[3],
                    'tracking_number': row[17]
                })
        
        return {
            'order_details': order_details,
            'books': books
        }
    except Exception as e:
        print(f"Error fetching order data: {e}")
        return None

# --- DeepSeek API Function ---
def query_deepseek(messages, temperature=0.1):
    """Send messages to DeepSeek API and return the response."""
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
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error with DeepSeek API: {e}")
        return "I'm having trouble connecting right now. Please try again."

def extract_order_id(text):
    """Extract a Bookswagon order ID from text."""
    # Look for UR format order IDs as shown in the screenshot
    pattern = r'\b(UR\d{10,})\b'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(0)
    
    # Continue with BW format if needed
    pattern = r'\b([Bb][Ww]\d{10,})\b'
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(0)
    
    # Use AI for complex extraction
    messages = [
        {"role": "system", "content": "Extract Bookswagon order ID (UR or BW followed by digits) from text or return 'None'."},
        {"role": "user", "content": f"Extract order ID from: {text}"}
    ]
    result = query_deepseek(messages).strip()
    if result.upper() != "NONE" and (re.match(r'^UR\d+$', result, re.IGNORECASE) or re.match(r'^BW\d+$', result, re.IGNORECASE)):
        return result.upper()
    return None

def format_order_response(order_data):
    """Format order details for display in a subtle, concise manner."""
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
        f"Order: {order_details.get('order_number')}\n"
        f"Customer: {order_details.get('customer_name')}\n"
        f"Purchase Date: {purchase_date}\n"
        f"Expected Delivery: {promise_date}\n"
        f"Order Status: {order_details.get('order_status')}\n"
        f"Payment Status: {order_details.get('payment_status')}\n"
        f"Total Amount: {order_details.get('order_amount')}\n"
        f"Tracking Number: {order_details.get('tracking_number') or 'Not available'}\n"
    )
    
    # Add shipping details
    formatted_response += (
        f"\nShipping Address:\n"
        f"{order_details.get('shipping_address')}\n"
        f"{order_details.get('shipping_city')}, {order_details.get('shipping_state')} {order_details.get('shipping_zip')}\n"
        f"{order_details.get('shipping_country')}\n"
        f"Contact: {order_details.get('shipping_mobile')}\n"
    )
    
    # Add book details
    formatted_response += "\nProducts:\n"
    for i, book in enumerate(books, 1):
        formatted_response += f"{i}. {book['product_name']} (ISBN: {book['isbn'] or 'N/A'})\n"
    
    return formatted_response

def format_single_book_response(order_data, book_index):
    """Format response for a single book within an order."""
    if not order_data or book_index >= len(order_data['books']):
        return "Book details not found."
    
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
        f"Order: {order_details.get('order_number')}\n"
        f"Product: {book['product_name']}\n"
        f"ISBN: {book['isbn'] or 'N/A'}\n"
        f"Purchase Date: {purchase_date}\n"
        f"Expected Delivery: {promise_date}\n"
        f"Order Status: {order_details.get('order_status')}\n"
        f"Payment Status: {order_details.get('payment_status')}\n"
        f"Tracking Number: {book['tracking_number'] or 'Not available'}\n"
    )
    
    return formatted_response

def detect_language(text):
    """Detect if text contains Hindi or Hinglish using AI."""
    prompt = f"""Determine if the following text contains Hindi words or is written in Hinglish.
    Return 'hindi' if it contains Hindi or Hinglish, otherwise return 'english'.
    
    Text: "{text}"
    
    Return ONLY 'hindi' or 'english', nothing else."""
    
    result = query_deepseek([{"role": "user", "content": prompt}]).strip().lower()
    return result == "hindi"

def get_response_in_language(response, is_hindi):
    """Translate or adjust the response based on the detected language."""
    if is_hindi:
        # Translate the response to Hindi or Hinglish
        translation_prompt = f"""Translate the following text to Hindi or Hinglish:
        
        Text: "{response}"
        
        Return ONLY the translated text."""
        try:
            translated_response = query_deepseek([{"role": "user", "content": translation_prompt}]).strip()
            return translated_response
        except Exception as e:
            print(f"Error translating response: {e}")
            return response  # Fallback to English response
    return response  # Return the original English response if not Hindi

def generate_order_summary(order_data, user_query):
    """Generate a natural language response about the order using AI."""
    if not order_data:
        return "Order details not found."
    
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
    order_summary = {
        "order_number": order_details.get('order_number'),
        "customer_name": order_details.get('customer_name'),
        "purchase_date": purchase_date,
        "expected_delivery": promise_date,
        "order_status": order_details.get('order_status'),
        "payment_status": order_details.get('payment_status'),
        "tracking_number": order_details.get('tracking_number') or "Not available",
        "products": [book['product_name'] for book in books]
    }
    
    # Create AI prompt
    prompt = f"""
    Based on the following order details from Bookswagon, answer the customer's query:
    
    Order Details:
    {order_summary}
    
    Customer Query: "{user_query}"
    
    Provide a helpful, concise response addressing the customer's specific question.
    Keep your response under 3 sentences unless detailed information is absolutely necessary.
    For cancellation queries, mention the standard policy: "Orders can only be cancelled if they haven't been shipped yet. 
    Cancellation takes 24 hours to process. Please visit your account on Bookswagon.com for assistance."
    """
    
    # Query the AI for response
    messages = [
        {"role": "system", "content": "You are a helpful customer service assistant for Bookswagon online bookstore."},
        {"role": "user", "content": prompt}
    ]
    
    return query_deepseek(messages)
import threading

def main():
    connection, cursor = get_db_connection()
    if not connection or not cursor:
        print("System error: Unable to connect to the database.")
        return

    # System prompt that defines the bot's behavior
    system_prompt = """You are a customer service assistant for Bookswagon, an online bookstore.
    Respond to customer queries about their orders. Be helpful, friendly, and concise.
    If you detect Hindi or Hinglish, include a Hindi or Hinglish response.
    Keep responses under 3 sentences unless details are needed.
    For order cancellation queries, provide information about the cancellation policy:
    "Orders can only be cancelled if they haven't been shipped yet. Cancellation takes 24 hours to process.
    Please visit your account on Bookswagon.com or contact customer service for assistance with cancellation."
    Never attempt to cancel orders yourself."""

    # Initial greeting
    welcome_message = "Hello! How can I assist you with your Bookswagon order today?"
    print(f"\nBookswagon: {welcome_message}")

    # Conversation context
    context = []
    active_order_data = None
    active_order_id = None

    # Timeout flag
    timeout_flag = threading.Event()

    def timeout_handler():
        """Handle timeout if the user doesn't respond within 300 seconds."""
        if not timeout_flag.wait(300):  # Wait for 300 seconds
            farewell_message = "I didn't receive any response. Have a great day! Thank you for using Bookswagon support."
            print(f"\nBookswagon: {farewell_message}")
            exit(0)

    try:
        while True:
            # Start the timeout thread
            timeout_thread = threading.Thread(target=timeout_handler)
            timeout_thread.daemon = True
            timeout_thread.start()

            # Get user input
            user_input = input("\nUser: ")
            timeout_flag.set()  # Reset the timeout flag if the user responds
            timeout_flag.clear()  # Clear the flag for the next iteration

            # Detect language
            is_hindi = detect_language(user_input)

            # Check for exit commands
            if any(cmd in user_input.lower() for cmd in EXIT_COMMANDS):
                farewell_message = "Thank you for using Bookswagon support. Have a good day!"
                farewell_message = get_response_in_language(farewell_message, is_hindi)
                print(f"\nBookswagon: {farewell_message}")
                break

            # Update context with user input
            context.append({"role": "user", "content": user_input})

            # Extract order ID if present
            order_id = extract_order_id(user_input)
            
            if order_id:
                active_order_id = order_id
                active_order_data = fetch_order_data(cursor, active_order_id)
                
                if not active_order_data:
                    response = f"I couldn't find any order with ID {active_order_id}. Please check the order number and try again."
                    response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
                    active_order_id = None
                    continue
                
                books = active_order_data['books']
                
                if len(books) == 1:
                    # Single book order - display details directly
                    response = format_single_book_response(active_order_data, 0)
                    response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
                    
                    # Ask follow-up
                    follow_up = "Is there anything else you'd like to know about this order?"
                    follow_up = get_response_in_language(follow_up, is_hindi)
                    print(f"\nBookswagon: {follow_up}")
                    
                elif len(books) > 1:
                    # Format full order response with all books
                    response = format_order_response(active_order_data)
                    response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
                    
                    # Ask which book they want details for
                    follow_up = "Which specific book would you like more details about? Please respond with the book number or name."
                    follow_up = get_response_in_language(follow_up, is_hindi)
                    print(f"\nBookswagon: {follow_up}")
                    
                else:
                    # No books found in order (unusual case)
                    response = f"Your order {active_order_id} was found but doesn't have any products listed. This is unusual. Please contact customer support for assistance."
                    response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
            
            elif active_order_data and active_order_id:
                # User has an active order context
                books = active_order_data['books']
                
                if len(books) > 1:
                    # Check if user is selecting a specific book
                    try:
                        # First try to match by number
                        if user_input.isdigit() and 1 <= int(user_input) <= len(books):
                            book_index = int(user_input) - 1
                            response = format_single_book_response(active_order_data, book_index)
                            response = get_response_in_language(response, is_hindi)
                            print(f"\nBookswagon: {response}")
                            continue
                        
                        # Try to match by name
                        best_match = -1
                        user_input_lower = user_input.lower()
                        for i, book in enumerate(books):
                            if user_input_lower in book['product_name'].lower():
                                best_match = i
                                break
                        
                        if best_match >= 0:
                            response = format_single_book_response(active_order_data, best_match)
                            response = get_response_in_language(response, is_hindi)
                            print(f"\nBookswagon: {response}")
                            continue
                    except (ValueError, IndexError):
                        # Failed to parse as book selection, continue to general query handling
                        pass
                
                # Handle as general query about the active order
                response = generate_order_summary(active_order_data, user_input)
                response = get_response_in_language(response, is_hindi)
                print(f"\nBookswagon: {response}")
                
            else:
                # Handle general queries without order context
                full_context = [{"role": "system", "content": system_prompt}]
                full_context.extend(context[-3:])  # Keep conversation context limited to last 3 exchanges
                
                response = query_deepseek(full_context)
                response = get_response_in_language(response, is_hindi)
                print(f"\nBookswagon: {response}")
                context.append({"role": "assistant", "content": response})

    except KeyboardInterrupt:
        farewell_message = "Thank you for using Bookswagon support. Have a good day!"
        farewell_message = get_response_in_language(farewell_message, is_hindi)
        print(f"\nBookswagon: {farewell_message}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == "__main__":
    main()