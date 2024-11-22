import streamlit as st
import time
from twelvelabs import TwelveLabs
import torch
from torchvision import models, transforms
from PIL import Image
import pandas as pd
from urllib.parse import urlparse
import uuid
from dotenv import load_dotenv
import os
from pymilvus import MilvusClient
from pymilvus import connections
from pymilvus import (
    FieldSchema, DataType, 
    CollectionSchema, Collection,
    utility
)
from openai import OpenAI
import json

# Load environment variables
load_dotenv()
TWELVELABS_API_KEY = os.getenv('TWELVELABS_API_KEY')
MILVUS_DB_NAME = os.getenv('MILVUS_DB_NAME')
COLLECTION_NAME = os.getenv('COLLECTION_NAME')
MILVUS_HOST = os.getenv('MILVUS_HOST')
MILVUS_PORT = os.getenv('MILVUS_PORT')
URL = os.getenv('URL')
TOKEN = os.getenv('TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Initialize OpenAI client
openai_client = OpenAI()

# Milvus Connection
connections.connect(
    uri=URL,
    token=TOKEN
)

# Define fields for schema
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=False),
    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),
]

# Create schema with dynamic fields for metadata
schema = CollectionSchema(
    fields=fields,
    enable_dynamic_field=True
)

# Check if collection exists
if utility.has_collection(COLLECTION_NAME):
    collection = Collection(COLLECTION_NAME)
    print(f"Using existing collection: {COLLECTION_NAME}")
else:
    collection = Collection(COLLECTION_NAME, schema)
    print(f"Created new collection: {COLLECTION_NAME}")
    
    if not collection.has_index():
        collection.create_index(
            field_name="vector",
            index_params={
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
        )
        print("Created index for the new collection")

collection.load()
milvus_client = collection

# Function to generate embeddings
def emb_text(text):
    return (
        openai_client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        .data[0]
        .embedding
    )

# Function to get RAG response
def get_rag_response(question):
    # Search for similar content in Milvus
    search_res = milvus_client.search(
        data=[emb_text(question)],
        limit=3,
        search_params={"metric_type": "IP", "params": {}},
        output_fields=["text"]
    )

    # Extract retrieved documents
    retrieved_lines_with_distances = [
        (res["entity"]["text"], res["distance"])
        for res in search_res[0]
    ]

    # Convert retrieved documents to context string
    context = "\n".join(
        [line_with_distance[0] for line_with_distance in retrieved_lines_with_distances]
    )

    # Define prompts
    SYSTEM_PROMPT = """
    You are an AI assistant. You are able to find answers to the questions from the contextual passage snippets provided.
    """

    USER_PROMPT = f"""
    Use the following pieces of information enclosed in <context> tags to provide an answer to the question enclosed in <question> tags.
    <context>
    {context}
    </context>
    <question>
    {question}
    </question>
    """

    # Generate response using OpenAI
    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
    )

    return response.choices[0].message.content

# Streamlit UI
st.title("📚 RAG Chatbot")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ask a question..."):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display assistant response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = get_rag_response(prompt)
            st.markdown(response)
    
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})

# Sidebar with info
with st.sidebar:
    st.title("About")
    st.markdown("""
    Ask questions about Fashion Related to get informed responses
    """)
