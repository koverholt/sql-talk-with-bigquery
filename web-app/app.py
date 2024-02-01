import time
import streamlit as st
from google.cloud import bigquery
from vertexai.preview.generative_models import (
    FunctionDeclaration,
    GenerativeModel,
    Part,
    Tool,
)

sql_query_func = FunctionDeclaration(
    name="sql_query",
    description="Get information from data in BigQuery using SQL queries",
    parameters={
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "SQL query that will help answer the user's question when run on a BigQuery dataset and table. In the SQL query, always use the fully qualified dataset and table names."
        }
    },
         "required": [
            "query",
      ]
  },
)

list_datasets_func = FunctionDeclaration(
    name="list_datasets",
    description="Get a list of datasets that will help answer the user's question",
    parameters={
    "type": "object",
    "properties": {
  },
},
)

list_tables_func = FunctionDeclaration(
    name="list_tables",
    description="List tables in a dataset that will help answer the user's question",
    parameters={
    "type": "object",
    "properties": {
        "dataset_id": {
            "type": "string",
            "description": "Fully qualified ID of the dataset to fetch tables from"
        }
    },
         "required": [
            "dataset_id",
      ]
  },
)

get_table_func = FunctionDeclaration(
    name="get_table",
    description="Get information about a table, including the description, schema, and number of rows that will help answer the user's question.",
    parameters={
    "type": "object",
    "properties": {
        "table_id": {
            "type": "string",
            "description": "Fully qualified ID of the table to get information about"
        }
    },
         "required": [
            "query",
      ]
  },
)

sql_query_tool = Tool(
    function_declarations=[
        sql_query_func,
        list_datasets_func,
        list_tables_func,
        get_table_func,
    ],
)

model = GenerativeModel(
    "gemini-pro", generation_config={"temperature": 0}, tools=[sql_query_tool]
)

st.set_page_config(
    page_title="SQL Talk with BigQuery",
    page_icon="vertex-ai.png",
    layout="wide",
)

col1, col2 = st.columns([8, 1])
with col1:
   st.title("SQL Talk with BigQuery")
with col2:
   st.image("vertex-ai.png")

st.subheader("Powered by Function Calling in Gemini")

with st.expander("Sample prompts"):
    st.write("""
        - What kind of data is in this database?
        - How many distribution centers are there?
        - What are the top 5 product categories that we sell the most of?
        - What is the average price and number of items that customers order?
        - Can you give me a summary with percentages of where users are coming to our website from?
    """)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        try:
            with st.expander("Function calls, parameters, and responses"):
                st.markdown(message["backend_details"])
        except:
            pass

if prompt := st.chat_input("Ask me about information in the database..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        chat = model.start_chat()
        client = bigquery.Client()

        prompt += """
            Please give a concise, high-level summary followed by detail in
            plain language about where the information in your response is
            coming from in the database. Only use information that you learn
            from BigQuery, do not make up information.
            """

        response = chat.send_message(prompt)
        response = response.candidates[0].content.parts[0]

        print(response)

        api_requests_and_responses = []
        backend_details = ""

        function_calling_in_process = True
        while function_calling_in_process:
            try:
                params = {}
                for key, value in response.function_call.args.items():
                    params[key] = value

                print(response.function_call.name)
                print(params)

                if response.function_call.name == "list_datasets":
                    api_response = client.list_datasets()
                    api_response = str([dataset.dataset_id for dataset in api_response])
                    api_requests_and_responses.append([response.function_call.name, params, api_response])

                if response.function_call.name == "list_tables":
                    api_response = client.list_tables(params["dataset_id"])
                    api_response = str([table.table_id for table in api_response])
                    api_requests_and_responses.append([response.function_call.name, params, api_response])

                if response.function_call.name == "get_table":
                    api_response = client.get_table(params["table_id"])
                    api_response = api_response.to_api_repr()
                    api_requests_and_responses.append([response.function_call.name, params, [str(api_response["description"]), str([column["name"] for column in api_response["schema"]["fields"]]) ]])
                    api_response = str(api_response)

                if response.function_call.name == "sql_query":
                    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=100000000)  # Data limit per query job
                    query_job = client.query(params["query"], job_config=job_config)
                    api_response = query_job.result()
                    api_response = str([row for row in api_response])
                    api_requests_and_responses.append([response.function_call.name, params, api_response])

                print(api_response)

                response = chat.send_message(
                    Part.from_function_response(
                        name=response.function_call.name,
                        response={
                            "content": api_response,
                        },
                    ),
                )
                response = response.candidates[0].content.parts[0]

                backend_details += "- Function call:\n"
                backend_details += "   - Function name: ```" + str(api_requests_and_responses[-1][0]) + "```"
                backend_details += "\n\n"
                backend_details += "   - Function parameters: ```" + str(api_requests_and_responses[-1][1]) + "```"
                backend_details += "\n\n"
                backend_details += "   - API response: ```" + str(api_requests_and_responses[-1][2]) + "```"
                backend_details += "\n\n"
                with message_placeholder.container():
                    st.markdown(backend_details)

            except AttributeError:
                function_calling_in_process = False

        time.sleep(3)

        full_response = (response.text)
        with message_placeholder.container():
            st.markdown(full_response)
            with st.expander("Function calls, parameters, and responses:"):
                st.markdown(backend_details)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": full_response,
                "backend_details": backend_details,
                }
        )
