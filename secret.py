from flask import Flask, request, jsonify
from deep2 import main  # import your chatbot logic

app = Flask(__name__)

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message")
    response = main(user_input)  # Your chatbot function
    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(debug=True)

