from google.cloud import aiplatform
from google.cloud.aiplatform.private_preview import llm_extension

# Upload YAML file to GCS

aiplatform.init(project="koverholt-devrel-355716", location="us-central1")

extension_bigquery = llm_extension.Extension.create(
    display_name = "BigQuery",
    description = "Interact with the BigQuery API",
    manifest = {
        "name": "bigquery_tool",
        "description": "BigQUery Extension",
        "api_spec": {
            "open_api_gcs_uri": "gs://vertex-ai-extensions-koverholt/bigquery/extension.yaml"
        },
        "auth_config": {
            "google_service_account_config": {},
            "auth_type": "GOOGLE_SERVICE_ACCOUNT_AUTH",
        },
    },
)
print(extension_bigquery)
