import json
import os

import boto3
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

# Load configuration from the project-root .env file, regardless of the
# working directory this script is launched from.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

ENDPOINT = os.environ.get("ENDPOINT", "http://localhost:4566")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
GATEKEEPER_FUNCTION_NAME = os.environ.get("GATEKEEPER_FUNCTION_NAME", "gatekeeper-function")
DOWNLOAD_FUNCTION_NAME = os.environ.get("DOWNLOAD_FUNCTION_NAME", "download-handler-function")
WEB_APP_PORT = int(os.environ.get("WEB_APP_PORT", 5000))

app = Flask(__name__)

lambda_client = boto3.client(
    "lambda",
    endpoint_url=ENDPOINT,
    region_name=AWS_REGION,
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
)


def invoke_lambda(function_name: str, payload: dict):
    """
    Synchronously invokes a Lambda function on LocalStack, wrapping the
    payload in the same {"body": "<json string>"} shape the functions
    already expect from API Gateway. Returns (status_code, parsed_body_dict).

    This Flask app is a thin broker only — it never talks to S3 or
    DynamoDB directly. All business logic (2PC, expiration checks) stays
    inside the Lambda functions, so the browser never needs AWS
    credentials of any kind.
    """
    event = {"body": json.dumps(payload)}
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(event).encode("utf-8"),
    )
    raw_payload = response["Payload"].read()
    result = json.loads(raw_payload) if raw_payload else {}

    if "FunctionError" in response:
        print(f"[Broker] Lambda {function_name} raised an error: {result}")
        return 500, {"error": "The service is temporarily unavailable."}

    status_code = result.get("statusCode", 500)
    body = result.get("body", "{}")
    body_dict = json.loads(body) if isinstance(body, str) else (body or {})
    return status_code, body_dict


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload-request", methods=["POST"])
def upload_request():
    data = request.get_json(force=True, silent=True) or {}
    filename = data.get("filename", "unnamed_file")

    try:
        expiration_seconds = int(data.get("expiration_seconds", 900))
    except (TypeError, ValueError):
        return jsonify({"error": "expiration_seconds must be an integer."}), 400

    status_code, body = invoke_lambda(GATEKEEPER_FUNCTION_NAME, {
        "filename": filename,
        "expiration_seconds": expiration_seconds,
    })
    return jsonify(body), status_code


@app.route("/api/download", methods=["POST"])
def download_request():
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip().upper()

    if not code:
        return jsonify({"error": "Missing 'code'."}), 400

    status_code, body = invoke_lambda(DOWNLOAD_FUNCTION_NAME, {"code": code})
    return jsonify(body), status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=WEB_APP_PORT, debug=True)
