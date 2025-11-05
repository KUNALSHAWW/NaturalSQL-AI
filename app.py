import streamlit as st
from pathlib import Path
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain.agents import AgentType
from langchain_community.callbacks import StreamlitCallbackHandler
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from sqlalchemy import create_engine
import sqlite3
from langchain_groq import ChatGroq
import pandas as pd
from datetime import datetime
import json

st.set_page_config(
    page_title="AI-Powered SQL Chat Assistant", 
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<p class="main-header">🤖 AI-Powered SQL Database Chat Assistant</p>', unsafe_allow_html=True)
st.markdown("---")

LOCALDB="USE_LOCALDB"
MYSQL="USE_MYSQL"

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Database Selection
    st.subheader("📊 Database Connection")
    radio_opt=["Use SQLLite 3 Database- Student.db","Connect to your MySQL Database"]
    selected_opt=st.radio(label="Choose the DB which you want to chat",options=radio_opt)

if radio_opt.index(selected_opt)==1:
    db_uri=MYSQL
    mysql_host=st.sidebar.text_input("Provide MySQL Host")
    mysql_user=st.sidebar.text_input("MYSQL User")
    mysql_password=st.sidebar.text_input("MYSQL password",type="password")
    mysql_db=st.sidebar.text_input("MySQL database")
else:
    db_uri=LOCALDB

    st.sidebar.markdown("---")
    
    # API Configuration
    st.sidebar.subheader("🔑 API Settings")
api_key=st.sidebar.text_input(label="Groq API Key",type="password")

# Additional Settings
with st.sidebar.expander("🔧 Advanced Settings"):
    model_name = st.selectbox(
        "Select LLM Model",
        ["Llama3-8b-8192", "Llama3-70b-8192", "Mixtral-8x7b-32768"],
        index=0
    )
    max_iterations = st.slider("Max Agent Iterations", 5, 20, 15)
    temperature = st.slider("Temperature", 0.0, 1.0, 0.1)

# Database Schema Display
with st.sidebar.expander("📋 View Database Schema"):
    if st.button("Show Schema"):
        st.session_state['show_schema'] = True

if not db_uri:
    st.info("Please enter the database information and uri")

if not api_key:
    st.info("Please add the groq api key")

## LLM model
llm=ChatGroq(groq_api_key=api_key,model_name=model_name,streaming=True,temperature=temperature)

@st.cache_resource(ttl="2h")
def configure_db(db_uri,mysql_host=None,mysql_user=None,mysql_password=None,mysql_db=None):
    if db_uri==LOCALDB:
        dbfilepath=(Path(__file__).parent/"student.db").absolute()
        print(dbfilepath)
        creator = lambda: sqlite3.connect(f"file:{dbfilepath}?mode=ro", uri=True)
        return SQLDatabase(create_engine("sqlite:///'", creator=creator))
    elif db_uri==MYSQL:
        if not (mysql_host and mysql_user and mysql_password and mysql_db):
            st.error("Please provide all MySQL connection details.")
            st.stop()
        return SQLDatabase(create_engine(f"mysql+mysqlconnector://{mysql_user}:{mysql_password}@{mysql_host}/{mysql_db}"))   

if db_uri==MYSQL:
    db=configure_db(db_uri,mysql_host,mysql_user,mysql_password,mysql_db)
else:
    db=configure_db(db_uri)

## toolkit
toolkit=SQLDatabaseToolkit(db=db,llm=llm)

agent=create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    max_iterations=max_iterations,
    handle_parsing_errors=True
)

# Display database schema if requested
if st.session_state.get('show_schema', False):
    st.subheader("📊 Database Schema")
    try:
        with st.expander("Tables and Structure", expanded=True):
            tables = db.get_usable_table_names()
            for table in tables:
                st.markdown(f"**Table: {table}**")
                schema_info = db.run(f"SELECT * FROM {table} LIMIT 0")
                st.code(schema_info)
    except Exception as e:
        st.error(f"Error displaying schema: {e}")
    st.session_state['show_schema'] = False

# Main chat interface
st.subheader("💬 Chat Interface")

# Display sample queries
with st.expander("💡 Sample Queries"):
    st.markdown("""
    - How many students are in the database?
    - Show me all students with marks greater than 85
    - What is the average marks by class?
    - List all students in Data Science class
    - Who has the highest marks?
    - Count students by section
    """)

# Query history tracking
if "query_history" not in st.session_state:
    st.session_state["query_history"] = []

if "messages" not in st.session_state or st.sidebar.button("Clear message history"):
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

user_query=st.chat_input(placeholder="Ask anything from the database")

if user_query:
    st.session_state.messages.append({"role": "user", "content": user_query})
    st.chat_message("user").write(user_query)
    
    # Add to query history
    st.session_state.query_history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "query": user_query
    })

    with st.chat_message("assistant"):
        streamlit_callback=StreamlitCallbackHandler(st.container())
        try:
            response=agent.run(user_query,callbacks=[streamlit_callback])
            st.session_state.messages.append({"role":"assistant","content":response})
            st.write(response)
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            st.error(error_msg)
            st.session_state.messages.append({"role":"assistant","content":error_msg})

# Display query history in sidebar
if st.session_state.query_history:
    with st.sidebar.expander("📜 Query History"):
        for i, item in enumerate(reversed(st.session_state.query_history[-10:])):
            st.text(f"{item['timestamp']}")
            st.caption(f"{item['query']}")
            st.divider()
