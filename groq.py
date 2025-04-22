import pyodbc
import requests
import os
import re
from datetime import datetime
from functools import wraps
from typing import Dict, List, Optional, Tuple, Union, Any
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, session, g

# Load environment variables
load_dotenv()

# Configuration
class Config:
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = "deepseek-chat"
    DB_DRIVER = os.getenv("DB_DRIVER")
    DB_SERVER = os.getenv("DB_SERVER")
    DB_DATABASE = os.getenv("DB_DATABASE")
    DB_UID = os.getenv("DB_UID")
    DB_PWD = os.getenv("DB_PWD")
    
    @classmethod
    def get_connection_string(cls) -> str:
        return f'DRIVER={{{cls.DB_DRIVER}}};SERVER={cls.DB_SERVER};DATABASE={cls.DB_DATABASE};UID={cls.DB_UID};PWD={cls.DB_PWD};'

    # Exit commands for multiple languages
    EXIT_COMMANDS = ["exit", "quit", "bye", "goodbye", "thanks", "thank you", 
                    "धन्यवाद", "अलविदा", "बाय", "tata", "ta ta"]

# FAQ Knowledge Base - could be moved to a separate file
class KnowledgeBase:
    FAQ = """
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

# Flask App Setup
app = Flask(__name__)
app.secret_key = '3dde42c933ad50a0ea052105e5abd23b105a6e07f8cad0f15e3339f6a6648515'

# Database Connection Management
class DatabaseManager:
    @staticmethod
    def get_db() -> Tuple[Any, Any]:
        """Get database connection and cursor"""
        if 'db' not in g:
            try:
                g.db = pyodbc.connect(Config.get_connection_string())
                g.cursor = g.db.cursor()
            except Exception as e:
                print(f"Database connection error: {e}")
                g.db = None
                g.cursor = None
        return g.db, g.cursor
    
    @staticmethod
    def close_db(e=None) -> None:
        """Close database connection"""
        db = g.pop('db', None)
        if db is not None:
            db.close()
    
    @staticmethod
    def fetch_order_data(order_id: str) -> Optional[Dict]:
        """Fetch order details from database"""
        conn, cursor = DatabaseManager.get_db()
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
                FULL JOIN Table_OrderCancellationReason oc ON os.ID_CancellationReason = oc.ID_OrderCancellationReason
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

            # Extract order details
            order_details = {
                'order_number': results[0][0],
                'order_summary_id': results[0][1],
                'purchase_date': results[0][4],
                'promise_date': results[0][5],
                'order_status': results[0][6],
                'cancellation_reason': results[0][7],
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
                if row[2] is not None:
                    books.append({
                        'product_name': row[2],
                        'isbn': row[3],
                        'tracking_number': row[18]
                    })

            return {
                'order_details': order_details,
                'books': books
            } if order_details else None

        except Exception as e:
            print(f"Error fetching order data: {e}")
            return None

# DeepSeek API Service
class DeepSeekService:
    @staticmethod
    def query_deepseek(messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
        """Send messages to DeepSeek API and return the response."""
        if not Config.DEEPSEEK_API_KEY or Config.DEEPSEEK_API_KEY == "sk-YOUR_DEFAULT_API_KEY_IF_NEEDED":
            return "I cannot connect to my AI service because the API key is not set up. Please contact support."
            
        try:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {Config.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": Config.DEEPSEEK_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1024
            }
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error with DeepSeek API: {e}")
            return "I'm having trouble connecting to my AI service right now. Please try again."

# Helper utilities for order processing
class OrderUtils:
    @staticmethod
    def extract_order_id(text: str) -> Optional[str]:
        """Extract a Bookswagon order ID from text."""
        # Check for standard patterns
        pattern_ur = r'\b(UR\d+)\b'
        pattern_bw = r'\b(BW\d+)\b'
        
        match_ur = re.search(pattern_ur, text, re.IGNORECASE)
        if match_ur:
            return match_ur.group(0).upper()

        match_bw = re.search(pattern_bw, text, re.IGNORECASE)
        if match_bw:
            return match_bw.group(0).upper()

        # Use AI for complex cases
        ai_prompt = f"""
        Analyze this text and extract a Bookswagon order ID (starts with 'UR' or 'BW' followed by digits).
        If no clear ID exists, return 'NONE'.
        
        Text: "{text}"
        
        Return ONLY the extracted ID (e.g., UR1234567890) or 'NONE'.
        """
        
        messages = [
            {"role": "system", "content": "You extract order IDs from text."},
            {"role": "user", "content": ai_prompt}
        ]
        
        try:
            result = DeepSeekService.query_deepseek(messages, temperature=0).strip()
            if result.upper() == "NONE":
                return None
            if re.match(r'^(UR|BW)\d+$', result, re.IGNORECASE):
                return result.upper()
            return None
        except Exception as e:
            print(f"Error extracting order ID: {e}")
            return None
    
    @staticmethod
    def format_order_response(order_data: Dict) -> str:
        """Format order details for display."""
        if not order_data:
            return "Order details not found."

        order_details = order_data['order_details']
        books = order_data['books']

        # Format dates
        purchase_date = OrderUtils.format_date(order_details.get('purchase_date', 'Unknown'))
        promise_date = OrderUtils.format_date(order_details.get('promise_date', 'Unknown'))

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
    
    @staticmethod
    def format_specific_books_response(order_data: Dict, book_indices: List[int]) -> str:
        """Format response for specific books within an order."""
        if not order_data:
            return "Order details not found."
        
        order_details = order_data['order_details']
        books = order_data['books']
        
        if not books:
            return "No products found in this order."
        
        # Format dates
        purchase_date = OrderUtils.format_date(order_details.get('purchase_date', 'Unknown'))
        promise_date = OrderUtils.format_date(order_details.get('promise_date', 'Unknown'))
        
        # Create response header
        formatted_response = (
            f"**Selected Products from Order {order_details.get('order_number')}**\n"
            f"- Order Status: {order_details.get('order_status')}\n"
            f"- Purchase Date: {purchase_date}\n"
            f"- Expected Delivery: {promise_date}\n\n"
        )
        
        # Add details for each selected book
        for index in book_indices:
            if 0 <= index < len(books):
                book = books[index]
                formatted_response += (
                    f"**Product {index+1}: {book['product_name']}**\n"
                    f"- ISBN: {book['isbn'] or 'N/A'}\n"
                    f"- Tracking Number: {book['tracking_number'] or 'Not available'}\n\n"
                )
        
        return formatted_response
    
    @staticmethod
    def format_date(date_value: Any) -> str:
        """Format date values consistently"""
        if isinstance(date_value, datetime):
            return date_value.strftime("%d/%m/%Y")
        return str(date_value)
    
    @staticmethod
    def parse_book_indices(user_input: str, total_books: int) -> List[int]:
        """Extract book indices from user input like '1,2,3' or '1 2 3'."""
        # Handle comma-separated values
        if ',' in user_input:
            parts = user_input.split(',')
        # Handle space-separated values
        else:
            parts = user_input.split()
        
        indices = []
        for part in parts:
            try:
                # Convert to zero-based index
                idx = int(part.strip()) - 1
                if 0 <= idx < total_books:
                    indices.append(idx)
            except ValueError:
                continue
        
        return indices

# Language processing utilities
class LanguageUtils:
    @staticmethod
    def detect_language(text: str) -> bool:
        """Detect if text contains Hindi or Hinglish using AI."""
        try:
            prompt = f"""
            Analyze this text. If it contains significant Hindi words, Hinglish phrases, or Devanagari script, return 'hindi'.
            Otherwise, return 'english'.
            
            Text: "{text}"
            
            Return ONLY 'hindi' or 'english'.
            """

            messages = [
                {"role": "system", "content": "You detect language in text."},
                {"role": "user", "content": prompt}
            ]

            result = DeepSeekService.query_deepseek(messages, temperature=0).strip().lower()
            return result == "hindi"
        except Exception as e:
            print(f"Error detecting language: {e}")
            return False
    
    @staticmethod
    def get_response_in_language(response: str, is_hindi: bool) -> str:
        """Translate response based on detected language."""
        if is_hindi:
            translation_prompt = f"""
            Translate this customer service response to natural-sounding Hindi or Hinglish.
            Maintain the original meaning and politeness.
            
            Text: "{response}"
            
            Provide ONLY the translated text.
            """
            try:
                return DeepSeekService.query_deepseek([{"role": "user", "content": translation_prompt}], temperature=0.3).strip()
            except Exception as e:
                print(f"Error translating: {e}")
                return response
        return response

# AI Response Generator
class AIResponseGenerator:
    @staticmethod
    def generate_order_summary(order_data: Dict, user_query: str, is_hindi: bool) -> str:
        """Generate AI response about an order incorporating FAQ knowledge."""
        if not order_data:
            return LanguageUtils.get_response_in_language("I don't have order details to answer that.", is_hindi)

        # Prepare order context for AI
        order_details = order_data['order_details']
        books = order_data['books']

        # Format dates
        purchase_date = OrderUtils.format_date(order_details.get('purchase_date', 'Unknown'))
        promise_date = OrderUtils.format_date(order_details.get('promise_date', 'Unknown'))

        # Create book list
        book_list = ', '.join([f"{i+1}. {book['product_name']}" for i, book in enumerate(books)])

        # Build AI prompt with all context
        prompt = f"""
        You are a Bookswagon customer service assistant. Answer based on this order info and FAQ knowledge.

        ORDER INFO:
        Order: {order_details.get('order_number')}
        Customer: {order_details.get('customer_name')}
        Purchased: {purchase_date}
        Expected Delivery: {promise_date}
        Status: {order_details.get('order_status')}
        Payment: {order_details.get('payment_status')}
        Tracking: {order_details.get('tracking_number') or "Not available"}
        Products: {book_list}
        {f"Cancellation Reason: {order_details.get('cancellation_reason')}" if order_details.get('order_status', '').lower() == 'cancelled' and order_details.get('cancellation_reason') else ""}

        FAQ KNOWLEDGE: {KnowledgeBase.FAQ}

        CUSTOMER QUERY: "{user_query}"

        INSTRUCTIONS:
        1. Answer directly using order details and FAQ knowledge
        2. If query is about status or tracking, provide relevant information
        3. For cancelled orders with reasons, state them clearly
        4. Keep response concise (3 sentences if possible)
        5. Don't attempt actions like cancelling orders
        6. Respond in {"Hindi or Hinglish" if is_hindi else "English"}
        """

        messages = [
            {"role": "system", "content": "You are a customer service assistant."},
            {"role": "user", "content": prompt}
        ]

        return DeepSeekService.query_deepseek(messages)
    
    @staticmethod
    def handle_general_query(user_input: str, is_hindi: bool, chat_history: List[Dict[str, str]]) -> str:
        """Handle general queries without order context"""
        system_prompt = f"""
        You are a Bookswagon customer service assistant. Use this FAQ knowledge to answer questions:
        
        {KnowledgeBase.FAQ}
        
        If query is about an order, ask for the order number unless already provided.
        Do NOT invent order details.
        Keep responses concise but helpful.
        
        Respond in {"Hindi or Hinglish" if is_hindi else "English"}.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            # Include limited chat history for context
            *chat_history[-5:]
        ]
        
        return DeepSeekService.query_deepseek(messages)

# Session Manager
class SessionManager:
    @staticmethod
    def get_chat_history() -> List[Dict[str, str]]:
        """Get chat history from session"""
        return session.get('chat_history', [])
    
    @staticmethod
    def get_active_order_id() -> Optional[str]:
        """Get active order ID from session"""
        return session.get('active_order_id', None)
    
    @staticmethod
    def get_active_order_data() -> Optional[Dict]:
        """Get active order data from session"""
        return session.get('active_order_data', None)
    
    @staticmethod
    def update_session(chat_history: List[Dict[str, str]], 
                       active_order_id: Optional[str] = None, 
                       active_order_data: Optional[Dict] = None) -> None:
        """Update session data"""
        session['chat_history'] = chat_history
        if active_order_id is not None:
            session['active_order_id'] = active_order_id
        if active_order_data is not None:
            session['active_order_data'] = active_order_data
    
    @staticmethod
    def clear_session() -> None:
        """Clear all session data"""
        session.clear()

# Request handling decorator for error catching
def handle_request_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print(f"Error processing request: {e}")
            return jsonify({"response": "Sorry, I encountered an error processing your request. Please try again."}), 500
    return decorated_function

# Register teardown handler
@app.teardown_request
def teardown_request(exception=None):
    DatabaseManager.close_db(exception)

# Flask Routes
@app.route('/')
def index():
    # Clear session for fresh start
    SessionManager.clear_session()
    # Add initial greeting
    initial_chat = [{"role": "assistant", "content": "Hello! How can I assist you with your Bookswagon order today? You can provide your order number or ask a general question."}]
    SessionManager.update_session(initial_chat)
    
    return render_template('index.html', chat_history=initial_chat)

@app.route('/api/message', methods=['POST'])
@handle_request_errors
def api_message():
    user_input = request.json.get('message')
    if not user_input:
        return jsonify({"response": "Please enter a message."}), 400

    # Retrieve state from session
    chat_history = SessionManager.get_chat_history()
    active_order_id = SessionManager.get_active_order_id()
    active_order_data = SessionManager.get_active_order_data()

    # Check for exit commands
    if any(cmd in user_input.lower() for cmd in Config.EXIT_COMMANDS):
        is_hindi = LanguageUtils.detect_language(user_input)
        farewell = LanguageUtils.get_response_in_language("Thank you for using Bookswagon support. Have a good day!", is_hindi)
        
        SessionManager.clear_session()
        chat_history.append({"role": "user", "content": user_input})
        chat_history.append({"role": "assistant", "content": farewell})
        
        return jsonify({"response": farewell, "end_chat": True, "chat_history": chat_history})

    # Add user input to history
    chat_history.append({"role": "user", "content": user_input})

    # Detect language
    is_hindi = LanguageUtils.detect_language(user_input)
    response_text = ""

    # Process the message
    response_text = ChatProcessor.process_message(user_input, is_hindi, chat_history, active_order_id, active_order_data)

    # Add bot response to history
    chat_history.append({"role": "assistant", "content": response_text})
    
    # Update session
    SessionManager.update_session(chat_history)

    # Return response and updated history
    return jsonify({"response": response_text, "chat_history": chat_history})

# Message processor
class ChatProcessor:
    @staticmethod
    def process_message(user_input: str, is_hindi: bool, 
                       chat_history: List[Dict[str, str]], 
                       active_order_id: Optional[str], 
                       active_order_data: Optional[Dict]) -> str:
        """Process user message and generate appropriate response"""
        # Try to extract order ID from input
        extracted_id = OrderUtils.extract_order_id(user_input)

        if extracted_id:
            return ChatProcessor.handle_order_id_query(extracted_id, user_input, is_hindi)
        elif active_order_data:
            return ChatProcessor.handle_active_order_query(active_order_data, user_input, is_hindi)
        else:
            return AIResponseGenerator.handle_general_query(user_input, is_hindi, chat_history)
    
    @staticmethod
    def handle_order_id_query(order_id: str, user_input: str, is_hindi: bool) -> str:
        """Process query containing an order ID"""
        order_data = DatabaseManager.fetch_order_data(order_id)

        if not order_data:
            return f"I couldn't find any order with ID {order_id}. Please check the order number and try again."
        
        # Set new active order in session
        SessionManager.update_session(
            SessionManager.get_chat_history(),
            active_order_id=order_id,
            active_order_data=order_data
        )

        # Check if cancelled order and query about cancellation
        order_details = order_data.get('order_details', {})
        is_cancellation_query = any(kw in user_input.lower() for kw in ["cancel", "cancelled", "cancellation", "why", "kyu", "kyun", "रद्द"])
        
        if order_details.get('order_status', '').lower() == 'cancelled' and is_cancellation_query:
            reason = order_details.get('cancellation_reason')
            return f"Your order {order_id} was cancelled due to: {reason}." if reason else f"Your order {order_id} was cancelled, but no specific reason was recorded."
        elif order_data['books']:
            response = OrderUtils.format_order_response(order_data)
            if len(order_data['books']) > 1:
                response += " Which specific book would you like more details about? You can specify by number (like '1') or multiple books (like '1,2,3')."
            else:
                response += " Is there anything else you'd like to know about this order?"
            return response
        else:
            return f"Your order {order_id} was found but doesn't have any products listed. This is unusual. Please contact customer support."
    
    @staticmethod
    def handle_active_order_query(active_order_data: Dict, user_input: str, is_hindi: bool) -> str:
        """Process query related to active order"""
        books = active_order_data.get('books', [])
        order_details = active_order_data.get('order_details', {})
        active_order_id = order_details.get('order_number')

        # Check for multiple book selections like "1,2,3" or "1 2 3"
        if len(books) > 1 and (re.search(r'\d+,\s*\d+', user_input) or re.search(r'\b\d+\s+\d+\b', user_input) or user_input.strip() == "all"):
            # Handle "all" selection
            if user_input.strip().lower() == "all":
                book_indices = list(range(len(books)))
            else:
                book_indices = OrderUtils.parse_book_indices(user_input, len(books))
            
            if book_indices:
                return OrderUtils.format_specific_books_response(active_order_data, book_indices)
            else:
                return AIResponseGenerator.generate_order_summary(active_order_data, user_input, is_hindi)
            
        # Check for single book selection
        elif len(books) > 1 and user_input.isdigit():
            book_index = int(user_input) - 1
            if 0 <= book_index < len(books):
                book = books[book_index]
                response = f"**Details for: {book['product_name']}**\n"
                response += f"- ISBN: {book['isbn'] or 'N/A'}\n"
                response += f"- Part of Order: {active_order_id}\n"
                response += f"- Order Status: {order_details.get('order_status')}\n"
                response += f"- Tracking Number: {book['tracking_number'] or 'Not available'}\n"
                return response
            else:
                return f"Please select a valid book number between 1 and {len(books)}."
        else:
            # General query about the active order
            return AIResponseGenerator.generate_order_summary(active_order_data, user_input, is_hindi)

# Run the Flask App
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)