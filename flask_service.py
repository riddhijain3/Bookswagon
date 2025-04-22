import win32serviceutil
import win32service
import win32event
import sys
import os
import time
import logging
import servicemanager
from app import app 

# Import for loading environment variables
from dotenv import load_dotenv

# --- Service Configuration ---
SERVICE_NAME = "BookswagonFlaskChatbot"
SERVICE_DISPLAY_NAME = "Bookswagon Flask Chatbot Service"
SERVICE_DESCRIPTION = "Runs the Bookswagon customer service chatbot Flask application."

# --- Waitress Configuration ---
# These should ideally come from environment variables loaded by load_dotenv()
FLASK_HOST = os.environ.get("FLASK_HOST", "0.0.0.0") 
FLASK_PORT = int(os.environ.get("FLASK_PORT", 5000))

# --- Logging Setup ---
# Services don't print to console, set up file logging
log_file = os.path.join(os.path.dirname(__file__), f"{SERVICE_NAME}.log")
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class FlaskService(win32serviceutil.ServiceFramework):
    # --- Required Attributes ---
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        # Event to signal the service to stop
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = True # Flag to control the main loop

    def SvcStop(self):
        """Called by the Service Control Manager to stop the service."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        logging.info(f"{SERVICE_DISPLAY_NAME} service is stopping...")
        self.is_running = False # Signal the main loop to exit
        win32event.SetEvent(self.stop_event) # Signal the waiting thread

        logging.info(f"{SERVICE_DISPLAY_NAME} service stopped.")
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)

    def SvcDoRun(self):
        """Called by the Service Control Manager when the service is started."""
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
        logging.info(f"{SERVICE_DISPLAY_NAME} service is starting...")

        try:
            dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
            if os.path.exists(dotenv_path):
                load_dotenv(dotenv_path)
                logging.info(".env file loaded.")
            else:
                logging.warning(".env file not found. Using existing environment variables.")

            # Ensure Flask Secret Key is loaded/set
            if not app.secret_key or app.secret_key == 'your_super_secret_fallback_key':
                 # You MUST set a strong secret key in your environment or .env
                 logging.error("Flask SECRET_KEY is not set! Session security is compromised.")

            # --- Start the Waitress WSGI Server ---
            from waitress import serve
            logging.info(f"Starting Waitress server on {FLASK_HOST}:{FLASK_PORT}")

            # Report service status as running
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            logging.info(f"{SERVICE_DISPLAY_NAME} service is running.")
            serve(app, host=FLASK_HOST, port=FLASK_PORT)

            # This line is reached when serve() stops (e.g., due to shutdown signal)
            logging.info("Waitress server stopped.")

        except Exception as e:
            logging.error(f"Service encountered an error: {e}", exc_info=True)
            self.SvcStop() # Signal stop on error
# --- Main Execution Block for Service Management ---
if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostService(FlaskService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(FlaskService)