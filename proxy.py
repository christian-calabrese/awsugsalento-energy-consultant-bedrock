import json
import os

import urllib.request

def lambda_handler(event, context):
    print(event)
    path = event["apiPath"]
    http_method = event["httpMethod"]
    headers = event.get(
        "headers",
        {
            "accept": "*/*",
            "accept-language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "content-type": "application/json",
        },
    )
    request_body = {
        param["name"]: param["value"]
        for param in event.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("properties", [])
    }
    parameters = {
        param["name"]: param["value"] for param in event.get("parameters", [])
    }
    url = os.getenv("API_GW_STAGE_URL") + path

    path_params = dict()
    query_params = dict()

    for key, value in parameters.items():
        if "{" + key + "}" in url:
            path_params[key] = value
        else:
            query_params[key] = value

    url = url.format(**path_params)

    print(url)

    if query_params:
        url += "?" + urllib.parse.urlencode(query_params)
    print(f"URL: {url}")

    if request_body:
        req = urllib.request.Request(
            url,
            headers=headers,
            method=http_method,
            data=bytes(json.dumps(request_body), encoding="utf-8"),
        )
    else:
        req = urllib.request.Request(
            url,
            headers=headers,
            method=http_method,
        )

    resp = urllib.request.urlopen(req)
    body = resp.read()

    response_body = {"application/json": {"body": body.decode("utf-8")}}
    action_response = {
        "actionGroup": event["actionGroup"],
        "apiPath": event["apiPath"],
        "httpMethod": event["httpMethod"],
        "httpStatusCode": 200,
        "responseBody": response_body,
    }
    api_response = {"messageVersion": "1.0", "response": action_response}

    return api_response