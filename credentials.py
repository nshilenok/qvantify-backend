import os

# Supabase Database Configuration
# Using direct connection with IPv4
db_config = {
    'host': os.environ.get('DB_HOST', 'db.lwwyepvurqddbcbggdvm.supabase.co'),
    'database': os.environ.get('DB_NAME', 'postgres'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', 'UkjI7gBAgA6p4MGI'),
    'port': int(os.environ.get('DB_PORT', 5432))
}

# OpenAI API Keys - Use environment variables
openaiapi_key = os.environ.get('OPENAI_API_KEY', 'placeholder')
openaiapi_panda_key = os.environ.get('OPENAI_PANDA_KEY', 'placeholder')
azureopenai_key = os.environ.get('AZURE_OPENAI_KEY', 'placeholder')

# Project configuration
panda_project = "your_panda_project_id"
default_prompt = "Default system prompt"
