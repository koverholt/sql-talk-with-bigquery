import vertexai
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from vertexai.preview.generative_models import (Content,
                                                FunctionDeclaration,
                                                GenerativeModel,
                                                Part,
                                                Tool
                                               )

from google.cloud import aiplatform
from google.cloud.aiplatform.private_preview import llm_extension
from vertexai.language_models import TextGenerationModel

################################################################################
# Sample prompts
################################################################################
# What is the exchange rate from USD to EUR?
# What was the exchange rate of Canadian dollars to Swedish Krona as of Jan 31, 2022?
# How much would $1000 in Australia be worth in Japanese yen as of mid 2020?
################################################################################

app = Flask(__name__)
cors = CORS(app)

PROJECT_ID = "koverholt-devrel-355716"
LOCATION = "us-central1"

vertexai.init(project=PROJECT_ID, location=LOCATION)

TOOL_SELECTION_PROMPT = """ You need to select one of the tools which can resolve this user query.
You should output the tool_name that you select.

TOOLs: {tool_descriptions}

USER QUERY: {query}
SELECTED tool_name:
"""

TOOL_INVOCATION_PROMPT = """ Given a user query and a tool, you need to predict input parameters as a JSON to trigger this tool which can answer this user query.

TOOL INPUT FORMAT:
{input_params}

{invocation_examples}
USER QUERY: {query}
RESPONSE:
"""

RESPONSE_PROMPT = """You should understand the format of this json OUTPUT by the following TOOL OUTPUT FORMAT,
and then use this json OUTPUT, find relevant information, summarize, answer the user query and reply in RESPONSE.
Your RESPONSE must answer the user query. If you don't find relevant information from OUTPUT, just reply "Sorry I don't know".
Your RESPONSE must be related to the OUTPUT.
If the user query is related to code and the output contains code, your response should also contain the code snippets.

Your RESPONSE should be informative, and simple for users to follow and understand.

TOOL OUTPUT FORMAT:
{output_params}

OUTPUT:
{output}

USER QUERY: {query}

RESPONSE:
"""

import logging
import json

logging.getLogger().setLevel(logging.INFO)


class SingleActionAgent:
    def __init__(self):
        self.TOOL_SELECTION_PROMPT = TOOL_SELECTION_PROMPT
        self.TOOL_INVOCATION_PROMPT = TOOL_INVOCATION_PROMPT
        self.RESPONSE_PROMPT = RESPONSE_PROMPT
        self.llm_model_name = "text-bison@001"
        self.llm_max_output_tokens = 512
        self.llm_temperature = 0.1
        self.llm_top_p = 0.8
        self.llm_top_k = 40
        self.project_id = 'koverholt-devrel-355716'
        self.location = 'us-central1'
        self.staging_bucket = f'koverholt-dev-extensions'
        self.tool_infos = [
            {
                "extension_id": "4091098049001029632", # exchange rate tool
                "operation_id": "get_exchange_rate",
                "output_type": "Result",
            }
        ]

    def set_up(self):
        from langchain import llms
        from google.cloud import aiplatform
        from google.cloud.aiplatform.private_preview import llm_extension

        aiplatform.init(
            project=self.project_id,
            location=self.location,
            staging_bucket=self.staging_bucket,
        )

        self.llm = llms.VertexAI(
            model_name=self.llm_model_name,
            max_output_tokens=self.llm_max_output_tokens,
            temperature=self.llm_temperature,
            top_p=self.llm_top_p,
            top_k=self.llm_top_k,
        )
        self.tool_infos = [
            self._generate_tool_info(
                extension=llm_extension.Extension(
                    f"projects/{self.project_id}/locations/{self.location}/extensions/{tool_info['extension_id']}",
                    # api_base_path_override='autopush-aiplatform.sandbox.googleapis.com',
                ),
                operation_id=tool_info["operation_id"],
                output_type=tool_info["output_type"],
            )
            for tool_info in self.tool_infos
        ]

    def _get_tool_description_string(self):
        result_string = ""
        for i, tool_info in enumerate(self.tool_infos):
            result_string += f"""
            {i+1}. tool_name: {tool_info['name']}
              tool_description:
                  {tool_info['operation_description']}
                  {tool_info['extension_description']}
            """
        return result_string

    def _get_tool_info_with_name(self, name):
        for tool_info in self.tool_infos:
            if tool_info["name"] == name:
                return tool_info
        raise Exception(f"Tool {name} is not supported.")

    def _run_vertex_extension(
            self,
            extension,
            operation_id: str,
            operation_params: dict
        ) -> dict:
        response = extension.execute(operation_id, operation_params)
        logging.info(f"\n Vertex Extension Response: {response}")
        return response

    def _llm_select_tool(self, query):
        tool_descriptions = self._get_tool_description_string()
        tool_name = self.llm.predict(self.TOOL_SELECTION_PROMPT.format(
            tool_descriptions=tool_descriptions,
            query=query,
        ))
        logging.info("\n Selected Tool: " + tool_name)
        return self._get_tool_info_with_name(tool_name)

    def _llm_predict_params(self, query, selected_tool_info):
        input_params = selected_tool_info['input_params']
        invocation_examples = selected_tool_info['invocation_examples'] if "invocation_examples" in selected_tool_info else ""
        params_string = self.llm.predict(
            self.TOOL_INVOCATION_PROMPT.format(
                input_params=input_params,
                invocation_examples=invocation_examples,
                query=query))
        logging.info("\n Predicted Params String: " + params_string)
        params_json = json.loads(params_string)
        logging.info("\n Parsed Tool Params: " + str(params_json))
        return params_json

    def _llm_generate_response(self, query, api_output, selected_tool_info):
        response = self.llm.predict(self.RESPONSE_PROMPT.format(
            query=query,
            output=api_output,
            output_params=selected_tool_info['output_params'],
        ))
        logging.info("\n Response: " + response)
        return response

    def _find_operation_id(self, json_data, operation_id):
        """Recursively searches for the dictionary with the specified operationId value."""
        if ("operationId" in json_data and json_data["operationId"] == operation_id):
            return json_data
        for key, value in json_data.items():
            if isinstance(value, dict):
                # Recursively search within nested dictionaries
                found_dict = self._find_operation_id(value, operation_id)
                if found_dict:
                    return found_dict
        return None  # No matching dictionary found

    def _generate_tool_info(
            self,
            extension,
            operation_id: str,
            output_type: str,
        ):
        open_api_struct = extension.api_spec()
        operation_struct = self._find_operation_id(open_api_struct, operation_id)
        output_params = open_api_struct
        return {"extension": extension,
                "operation_id": operation_id,
                "name": f"{open_api_struct['info']['title']}/{operation_id}",
                "extension_description": open_api_struct['info']['description'],
                "operation_description": operation_struct['description'],
                "input_params": operation_struct['parameters'],
                "output_params": output_params}

    def query(self, query):
        selected_tool_info = self._llm_select_tool(query)
        params_json = self._llm_predict_params(query, selected_tool_info)
        print("API Parameters" + str(params_json))
        api_output = self._run_vertex_extension(
            selected_tool_info['extension'],
            selected_tool_info['operation_id'],
            params_json,
        )
        print("API Response: " + str(api_output))
        response = self._llm_generate_response(query, api_output, selected_tool_info)
        return response

    def raw_query(self, query):
        parameters = {
            "candidate_count": 1,
            "max_output_tokens": 1024,
            "temperature": 0.9,
            "top_p": 1
        }
        model = TextGenerationModel.from_pretrained("text-bison")
        response = model.predict(
            query,
            **parameters
        )
        return response.text

@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "GET":
        return 200

    if request.method == "POST":
        request_json = request.get_json(silent=True)
        if request_json and "prompt" in request_json:
            prompt = request_json["prompt"]

            agent = SingleActionAgent()
            agent.set_up()
            response = str(agent.query(prompt))
            raw_response = agent.raw_query(prompt)

            return jsonify({
                "response": response,
                "raw_response": raw_response,
                })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
