import pyodbc
import requests
import os
import re
from datetime import datetime
import threading

# --- Configuration ---
DEEPSEEK_API_KEY = "sk-d93b060eda3647fda2f72cf4029ff7a5"
DEEPSEEK_MODEL = "deepseek-chat"  # Update to specific model name if needed

# --- Exit Commands ---
EXIT_COMMANDS = ["exit", "quit", "bye", "goodbye", "thanks", "thank you", "धन्यवाद", "अलविदा", "बाय", "tata", "ta ta"]

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
        conn_str = 'DRIVER={SQL Server};SERVER=103.181.20.253;DATABASE=BooksBay;UID=sa;PWD=db@123qaz;'
        
        connection = pyodbc.connect(conn_str) 
        cursor = connection.cursor()
        return connection, cursor
    except Exception as e:
        print(f"Database connection error: {e}")
        return None, None

def fetch_order_data(cursor, order_id):
    """Fetches all order information using the comprehensive query."""
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
            if row[2]:  # Product title exists
                books.append({
                    'product_name': row[2],
                    'isbn': row[3],
                    'tracking_number': row[18]
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
    # Look for UR format order IDs
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
    
    # Add cancellation reason if order is cancelled
    if order_details.get('order_status', '').lower() == 'cancelled' and order_details.get('cancellation_reason'):
        formatted_response += f"Cancellation Reason: {order_details.get('cancellation_reason')}\n"
    
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
    
    # Add cancellation reason if order is cancelled
    if order_details.get('order_status', '').lower() == 'cancelled' and order_details.get('cancellation_reason'):
        formatted_response += f"Cancellation Reason: {order_details.get('cancellation_reason')}\n"
    
    return formatted_response

def detect_language(text):
    """Detect if text contains Hindi or Hinglish using AI."""
    try:
        prompt = f"""Analyze if the following text contains Hindi words, is written in Hinglish, or uses Devanagari script.
        Return 'hindi' ONLY if it contains Hindi words, Hinglish phrases (like 'meko', 'batao', 'kyu', 'kya', 'mera'), or Devanagari script.
        Return 'english' for all other cases, including when the text is fully in English.
        
        Example texts that should be classified as 'hindi':
        - "mera order cancel kyu hua"
        - "मेरा ऑर्डर कैंसल क्यों हुआ"
        - "order kab milega"
        - "kitne din me aayega mera order"
        
        xample texts that should be classified as 'english':
        - "Why my order got cancelled?"
        - "Hey, Hie, yo, wassup"
        - "When will I receive my order?"
        - "How long does it take to deliver my order"?
        - "order no BW1234567890"
        
        Text: "{text}"
        
        Return ONLY 'hindi' or 'english', nothing else."""
        
        result = query_deepseek([{"role": "user", "content": prompt}]).strip().lower()
        if result not in ["hindi", "english"]:
            print(f"Warning: Unexpected language detection result: {result}. Defaulting to 'english'.")
            return False  # Default to English
        
        return result == "hindi"
    except Exception as e:
        print(f"Error detecting language: {e}. Defaulting to 'english'.")
        return False  # Default to English

def get_response_in_language(response, is_hindi):
    """Translate or adjust the response based on the detected language."""
    if is_hindi:
        # Translate the response to Hindi or Hinglish
        translation_prompt = f"""Translate the following customer service response to Hindi or Hinglish (mix of Hindi and English):
        
        Text: "{response}"
        
        Provide ONLY the translated text without any explanations or notes."""
        try:
            translated_response = query_deepseek([{"role": "user", "content": translation_prompt}]).strip()
            print(f"Debug: Translated response: {translated_response}")
            return translated_response
        except Exception as e:
            print(f"Error translating response: {e}")
            return response  # Fallback to English response
    return response  # Return the original English response if not Hindi

def generate_order_summary(order_data, user_query, is_hindi):
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
    
    # Check if the query is about cancellation
    is_cancellation_query = False
    cancel_keywords = ["cancel", "cancelled", "cancellation", "why cancel", "cancel kyu", "cancel kyun", "cancel kyon", "रद्द"]
    
    if any(keyword in user_query.lower() for keyword in cancel_keywords):
        is_cancellation_query = True
    
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
    
    # Include cancellation reason if order is cancelled and query is about cancellation
    cancellation_info = ""
    if order_details.get('order_status', '').lower() == 'cancelled':
        if order_details.get('cancellation_reason'):
            cancellation_info = f"Cancellation Reason: {order_details.get('cancellation_reason')}"
        else:
            cancellation_info = "This order was cancelled, but no specific reason was recorded in our system."
    
    # Create language instruction based on detected language
    language_instruction = ""
    if is_hindi:
        language_instruction = "Respond in Hindi or Hinglish (mix of Hindi and English)."
    else:
        language_instruction = "Respond in English only."
    
    # Create AI prompt with FAQ knowledge incorporated
    prompt = f"""
    Based on the following order details from Bookswagon and our FAQ knowledge base, answer the customer's query:
    
    Order Details:
    {order_summary}
    
    {cancellation_info}
    
    FAQ Knowledge Base:
    {FAQ_KNOWLEDGE}
    
    Customer Query: "{user_query}"
    
    {language_instruction}
    
    Provide a helpful, concise response addressing the customer's specific question.
    Keep your response under 3 sentences unless detailed information is absolutely necessary.
    
    If the query is about order cancellation and the order is cancelled, clearly explain the reason for cancellation.
    For general cancellation queries, mention the standard policy: "Orders can only be cancelled if they haven't been shipped yet. 
    Cancellation takes 24 hours to process. Please visit your account on Bookswagon.com for assistance."
    """
    
    # Query the AI for response
    messages = [
        {"role": "system", "content": "You are a helpful customer service assistant for Bookswagon online bookstore."},
        {"role": "user", "content": prompt}
    ]
    
    return query_deepseek(messages)

def main():
    connection, cursor = get_db_connection()
    if not connection or not cursor:
        print("System error: Unable to connect to the database.")
        return

    # System prompt that defines the bot's behavior, now incorporating FAQ knowledge
    system_prompt = f"""You are a customer service assistant for Bookswagon, an online bookstore.
    Respond to customer queries about their orders and general inquiries based on our FAQ knowledge.
    
    FAQ Knowledge Base:
    {FAQ_KNOWLEDGE}
    
    Be helpful, friendly, and concise.
    IMPORTANT: Only respond in Hindi or Hinglish if the user's message contains Hindi words or is in Hinglish.
    Otherwise, always respond in English only.
    
    Keep responses under 3 sentences unless details are needed.
    For order cancellation queries, provide information about the cancellation policy:
    "Orders can only be cancelled if they haven't been shipped yet. Cancellation takes 24 hours to process.
    if customer asking why their order gets cancelled, ask for their order number and provide the reason from the database.
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
            if cursor:
                cursor.close()
            if connection:
                connection.close()
            os._exit(0)

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
            #print(f"Debug: Detected language is {'Hindi/Hinglish' if is_hindi else 'English'}")

            # Check for exit commands
            if any(cmd in user_input.lower() for cmd in EXIT_COMMANDS):
                farewell_message = "Thank you for using Bookswagon support. Have a good day!"
                if is_hindi:
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
                    if is_hindi:
                        response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
                    active_order_id = None
                    continue
                
                books = active_order_data['books']
                
                # Check if order is cancelled and if user is asking about cancellation
                order_details = active_order_data['order_details']
                if order_details.get('order_status', '').lower() == 'cancelled' and any(kw in user_input.lower() for kw in ["cancel", "cancelled", "cancellation", "why", "kyu", "kyun"]):
                    # Respond directly about cancellation
                    if order_details.get('cancellation_reason'):
                        response = f"Your order {active_order_id} was cancelled due to: {order_details.get('cancellation_reason')}"
                    else:
                        response = f"Your order {active_order_id} was cancelled, but no specific reason was recorded in our system."
                    
                    if is_hindi:
                        response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
                    continue
                
                if len(books) == 1:
                    # Single book order - display details directly
                    response = format_single_book_response(active_order_data, 0)
                    if is_hindi:
                        response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
                    
                    # Ask follow-up
                    follow_up = "Is there anything else you'd like to know about this order?"
                    if is_hindi:
                        follow_up = get_response_in_language(follow_up, is_hindi)
                    print(f"\nBookswagon: {follow_up}")
                    
                elif len(books) > 1:
                    # Format full order response with all books
                    response = format_order_response(active_order_data)
                    if is_hindi:
                        response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
                    
                    # Ask which book they want details for
                    follow_up = "Which specific book would you like more details about? Please respond with the book number or name."
                    if is_hindi:
                        follow_up = get_response_in_language(follow_up, is_hindi)
                    print(f"\nBookswagon: {follow_up}")
                    
                else:
                    # No books found in order (unusual case)
                    response = f"Your order {active_order_id} was found but doesn't have any products listed. This is unusual. Please contact customer support for assistance."
                    if is_hindi:
                        response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
            
            elif active_order_data and active_order_id:
                # User has an active order context
                books = active_order_data['books']
                
                # Check if the user is asking about cancellation
                if any(kw in user_input.lower() for kw in ["cancel", "cancelled", "cancellation", "why", "kyu", "kyun"]):
                    if active_order_id:
        # Fetch the cancellation reason from the database
                        order_details = active_order_data['order_details']
                        if order_details.get('order_status', '').lower() == 'cancelled':
                            if order_details.get('cancellation_reason'):
                                response = f"Your order {active_order_id} was cancelled due to: {order_details.get('cancellation_reason')}."
                            else:
                                response = f"Your order {active_order_id} was cancelled, but no specific reason was recorded in our system."
                        else:
                            response = f"Your order {active_order_id} is not cancelled. Its current status is: {order_details.get('order_status')}."
                    else:
        # Ask the user for the order number
                        response = "Could you please provide your order number so I can check the cancellation reason for you?"
                    if is_hindi:
                        response = get_response_in_language(response, is_hindi)
                    print(f"\nBookswagon: {response}")
                    continue
                if len(books) > 1:
                    # Check if user is selecting a specific book
                    try:
                        # First try to match by number
                        if user_input.isdigit() and 1 <= int(user_input) <= len(books):
                            book_index = int(user_input) - 1
                            response = format_single_book_response(active_order_data, book_index)
                            if is_hindi:
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
                            if is_hindi:
                                response = get_response_in_language(response, is_hindi)
                            print(f"\nBookswagon: {response}")
                            continue
                    except (ValueError, IndexError):
                        # Failed to parse as book selection, continue to general query handling
                        pass
                
                # Handle as general query about the active order
                response = generate_order_summary(active_order_data, user_input, is_hindi)
                # No need to translate response here as generate_order_summary already handles language
                print(f"\nBookswagon: {response}")
                
            else:
                # Handle general queries without order context, incorporating FAQ knowledge
                full_context = [{"role": "system", "content": system_prompt}]
                full_context.extend(context[-3:])  # Keep conversation context limited to last 3 exchanges
                
                response = query_deepseek(full_context)
                # Only translate if the input was in Hindi/Hinglish
                if is_hindi:
                    response = get_response_in_language(response, is_hindi)
                print(f"\nBookswagon: {response}")
                context.append({"role": "assistant", "content": response})

    except KeyboardInterrupt:
        farewell_message = "Thank you for using Bookswagon support. Have a good day!"
        if is_hindi:
            farewell_message = get_response_in_language(farewell_message, is_hindi)
        print(f"\nBookswagon: {farewell_message}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == "__main__":
    main()
