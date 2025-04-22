
USE chatbot_db;

CREATE TABLE responses (
    id INT IDENTITY(1,1) PRIMARY KEY,
    user_input TEXT NOT NULL,
    bot_response TEXT NOT NULL
);

INSERT INTO responses (id, user_input, bot_response) VALUES
('1', 'hello', 'Hi there! How can I assist you today?'),
('2', 'how are you', 'I am just a bot, but I am doing great! How can I help?');

ALTER TABLE responses
ALTER COLUMN user_input NVARCHAR(MAX);

