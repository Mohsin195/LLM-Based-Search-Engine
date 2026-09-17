import os
import streamlit as st
from openai import OpenAI
import new_main_4 as nm
import Schema_expert as se

# Set up the page title and configuration
st.set_page_config(page_title="Database Q&A Chat", layout="wide")
st.title("💬 sa: Database Q&A Chat")

def configure_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and api_key != nm.OPENAI_API_KEY:
        nm.client = OpenAI(api_key=api_key)

# Initialize session state for chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar with chat controls
with st.sidebar:
    st.header("Chat Controls")
    st.caption(f"📚 Tables loaded: {len(se.SCHEMA_PROFILE)}")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    
    st.divider()
    st.caption(f"💬 Messages in history: {len(st.session_state.messages)}")
    
    if st.session_state.messages:
        st.caption("📝 Conversation available for context")

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # Display SQL, data, and chart if available (for assistant messages)
        if message["role"] == "assistant" and "metadata" in message:
            metadata = message["metadata"]
            
            # Show SQL query
            if "sql" in metadata and metadata["sql"]:
                st.caption("**Generated SQL Query:**")
                st.code(metadata["sql"], language="sql")
                st.divider()
            
            # Show data table
            if "dataframe" in metadata and metadata["dataframe"] is not None:
                st.caption("**Query Results:**")
                st.dataframe(metadata["dataframe"], use_container_width=True)
                st.divider()
            
            # Show chart
            if "chart" in metadata and metadata["chart"] is not None:
                st.plotly_chart(metadata["chart"], use_container_width=True)
                st.divider()
        
        # Display the message content
        st.markdown(message["content"])

# Chat input
if question := st.chat_input("Ask a question about the database..."):
    configure_openai_client()
    
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": question})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(question)
    
    # Generate assistant response
    with st.chat_message("assistant"):
        try:
            # Get conversation history for context
            conversation_history = [
                {"role": msg["role"], "content": msg["content"]} 
                for msg in st.session_state.messages[:-1]  # Exclude current question
            ]
            
            with st.spinner("Loading schema..."):
                schema = nm.get_schema()

            with st.spinner("Generating SQL..."):
                sql = nm.generate_sql(question, schema, conversation_history)
                st.caption("**Generated SQL Query:**")
                st.code(sql, language="sql")
                st.divider()

            with st.spinner("Running query..."):
                df = nm.run_query(sql)
                df_display = nm.normalize_dataframe_for_display(df)
                st.caption("**Query Results:**")
                st.dataframe(df_display, use_container_width=True)
                st.divider()

            # Generate chart
            fig = None
            chart_message = None
            with st.spinner("Generating chart..."):
                fig, chart_message = nm.generate_chart(question, df_display)
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True)
                    st.divider()

            with st.spinner("Generating answer..."):
                answer = nm.generate_answer(question, df_display, conversation_history)

            st.markdown(answer)
            
            # Store assistant message with metadata
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "metadata": {
                    "sql": sql,
                    "dataframe": df_display,
                    "chart": fig
                }
            })
            
        except Exception as exc:
            error_msg = f"❌ Error: {exc}"
            st.error(error_msg)
            st.session_state.messages.append({
                "role": "assistant",
                "content": error_msg
            })



