import boto3
import json
import os
import urllib.request

from boto3.dynamodb.types import Decimal
from chalice import Chalice, Response


bills_table_name = os.getenv("BILLS_TABLE_NAME", "bills")
tariffs_table_name = os.getenv("tariffs_TABLE_NAME", "dealers_tariff")

app = Chalice(app_name="energy_consultant")

dynamodb = boto3.resource("dynamodb")

bills_table = dynamodb.Table(bills_table_name)

tariffs_table = dynamodb.Table(tariffs_table_name)


@app.route("/bills/{pod}/{year_month_from}")
def get_bill(pod, year_month_from):
    response = bills_table.get_item(
        Key={"pod": pod, "year_month_from": year_month_from}
    )

    return Response(
        body=response.get("Item", dict()),
        status_code=200,
        headers={"Content-Type": "application/json"},
    )


@app.route("/bills/{pod}")
def list_bills(pod):
    response = bills_table.query(
        KeyConditionExpression="pod = :pod",
        ExpressionAttributeValues={":pod": pod},
    )

    # extract the items from the response
    items = response.get("Items", [])

    return Response(
        body=items,
        status_code=200,
        headers={"Content-Type": "application/json"},
    )


@app.route("/bills/{pod}", methods=["POST"])
def put_bill(pod):
    request = app.current_request.json_body
    request["f1"] = Decimal(request.get("f1", 0))
    request["f2"] = Decimal(request.get("f2", 0))
    request["f3"] = Decimal(request.get("f3", 0))
    request["pod"] = pod

    request["total"] = (
        request.get("f1", 0) + request.get("f2", 0) + request.get("f3", 0)
    )
    bills_table.put_item(Item=request)

    return Response(
        body={"status": "OK"},
        status_code=200,
        headers={"Content-Type": "application/json"},
    )


def decimal_serializer(obj):
    if isinstance(obj, Decimal):
        ratio = obj.as_integer_ratio()
        if ratio[1] == 1:
            return int(obj)
        return float(obj)
    return obj


@app.route("/tariffs")
def list_tariffs():
    all_tariffs = []
    args = dict()
    query_params = (
        app.current_request.query_params if app.current_request.query_params else dict()
    )

    order_by = query_params.get("order", "desc")

    if query_params.get("limit", None):
        args["Limit"] = int(query_params.get("limit"))

    response = tariffs_table.scan(**args)
    all_tariffs = response.get("Items", [])

    while "LastEvaluatedKey" in response:
        response = tariffs_table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        all_tariffs.extend(response.get("Items", []))

    for tariff in all_tariffs:
        average = (tariff["F1"] + tariff["F2"] + tariff["F3"]) / 3
        tariff["average"] = average

    all_tariffs = sorted(
        all_tariffs,
        key=lambda item: item["average"],
        reverse=True if order_by == "desc" else False,
    )
    all_tariffs_f = json.dumps(all_tariffs, default=lambda x: decimal_serializer(x))

    return Response(
        body=all_tariffs_f,
        status_code=200,
        headers={"Content-Type": "application/json"},
    )


@app.lambda_function(name="bedrock-proxy")
def bedrock_proxy(event, context):
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
