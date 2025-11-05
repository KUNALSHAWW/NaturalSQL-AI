"""
Configuration file for the AI SQL Chat Assistant
Store your configuration settings here for better code organization
"""

# LLM Models Configuration
AVAILABLE_MODELS = {
    "Llama3-8b-8192": {
        "name": "Llama3 8B",
        "description": "Fast and efficient - Best for simple queries",
        "max_tokens": 8192,
        "recommended_use": "Quick queries, simple data retrieval"
    },
    "Llama3-70b-8192": {
        "name": "Llama3 70B", 
        "description": "High accuracy - Best for complex reasoning",
        "max_tokens": 8192,
        "recommended_use": "Complex joins, analytical queries"
    },
    "Mixtral-8x7b-32768": {
        "name": "Mixtral 8x7B",
        "description": "Large context - Best for extensive data",
        "max_tokens": 32768,
        "recommended_use": "Large context queries, multiple tables"
    }
}

# Database Configuration
DB_CONFIG = {
    "sqlite": {
        "mode": "ro",  # read-only mode for safety
        "timeout": 10,
        "check_same_thread": False
    },
    "mysql": {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True
    }
}

# Agent Configuration
AGENT_CONFIG = {
    "default_max_iterations": 15,
    "min_iterations": 5,
    "max_iterations": 20,
    "default_temperature": 0.1,
    "verbose": True,
    "handle_parsing_errors": True
}

# UI Configuration
UI_CONFIG = {
    "theme": {
        "primaryColor": "#1f77b4",
        "backgroundColor": "#ffffff",
        "secondaryBackgroundColor": "#f0f2f6",
        "textColor": "#262730"
    },
    "query_history_limit": 10,
    "cache_ttl": "2h"
}

# Sample Queries for different domains
SAMPLE_QUERIES = {
    "education": [
        "How many students are in the database?",
        "Show me all students with marks greater than 85",
        "What is the average marks by class?",
        "List all students in Data Science class",
        "Who has the highest marks?",
        "Count students by section"
    ],
    "business": [
        "What are the total sales for this month?",
        "Show top 10 customers by revenue",
        "What's the average order value?",
        "List products with low inventory",
        "Show sales trend by region"
    ],
    "hr": [
        "How many employees are in each department?",
        "What's the average salary by position?",
        "Show employees hired in the last year",
        "List employees due for performance review",
        "What's the employee retention rate?"
    ]
}

# Error Messages
ERROR_MESSAGES = {
    "no_api_key": "⚠️ Please enter your Groq API key in the sidebar to continue.",
    "no_db_uri": "⚠️ Please select a database and provide connection details.",
    "mysql_incomplete": "⚠️ Please provide all MySQL connection details (host, user, password, database).",
    "connection_failed": "❌ Failed to connect to the database. Please check your connection details.",
    "query_failed": "❌ Query execution failed. Please try rephrasing your question.",
    "timeout": "⏱️ Query timeout. Try increasing max iterations or simplifying your query."
}

# Success Messages
SUCCESS_MESSAGES = {
    "connected": "✅ Successfully connected to the database!",
    "query_executed": "✅ Query executed successfully!",
    "schema_loaded": "✅ Database schema loaded!"
}
