"""Core chat Lambda handler using AWS Bedrock Claude."""

import os
import json
import logging
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
HISTORY_TABLE = os.environ.get("HISTORY_TABLE", "chatbot-conversations")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)

SYSTEM_PROMPT = """You are a knowledgeable financial advisor AI assistant. You help users with:
- Portfolio analysis and asset allocation advice
- Market insights and trend analysis
- Risk assessment and management strategies
- Retirement planning and savings optimization
- Tax-efficient investing strategies
- Understanding financial concepts and instruments

Guidelines:
- Always provide balanced, well-reasoned financial advice
- Include relevant disclaimers when appropriate
- Use data and metrics to support your recommendations
- Ask clarifying questions when the user's situation is unclear
- Never guarantee returns or make specific price predictions
- Recommend consulting a licensed financial advisor for major decisions

DISCLAIMER: This AI provides general financial information and education. It is not a substitute for professional financial advice. Always consult with a qualified financial advisor before making investment decisions."""

TOOLS = [
    {
        "name": "analyze_portfolio",
        "description": "Analyze a portfolio of stocks/assets and provide diversification metrics, risk assessment, and rebalancing suggestions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "holdings": {
                    "type": "array",
                    "description": "List of holdings with ticker and allocation percentage",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "allocation_pct": {"type": "number"},
                            "shares": {"type": "number"},
                        },
                        "required": ["ticker", "allocation_pct"],
                    },
                },
                "risk_tolerance": {
                    "type": "string",
                    "enum": ["conservative", "moderate", "aggressive"],
                },
            },
            "required": ["holdings"],
        },
    },
    {
        "name": "get_market_data",
        "description": "Get current market data, price, and key metrics for a stock ticker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Metrics to fetch: price, pe_ratio, market_cap, dividend_yield, 52w_high, 52w_low",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "calculate_risk",
        "description": "Calculate portfolio risk metrics including volatility, Sharpe ratio, max drawdown, and Value at Risk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_value": {"type": "number", "description": "Total portfolio value in USD"},
                "holdings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "allocation_pct": {"type": "number"},
                        },
                    },
                },
                "time_horizon_years": {"type": "number"},
            },
            "required": ["portfolio_value", "holdings"],
        },
    },
]


def invoke_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return results."""
    from financial_chatbot.tools.portfolio import analyze_portfolio
    from financial_chatbot.tools.market_data import get_market_data
    from financial_chatbot.tools.risk import calculate_risk

    if tool_name == "analyze_portfolio":
        return json.dumps(analyze_portfolio(**tool_input))
    elif tool_name == "get_market_data":
        return json.dumps(get_market_data(**tool_input))
    elif tool_name == "calculate_risk":
        return json.dumps(calculate_risk(**tool_input))
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


def get_conversation_history(conversation_id: str) -> list:
    """Retrieve conversation history from DynamoDB."""
    table = dynamodb.Table(HISTORY_TABLE)
    try:
        response = table.get_item(Key={"conversation_id": conversation_id})
        item = response.get("Item", {})
        return json.loads(item.get("messages", "[]"))
    except Exception:
        return []


def save_conversation_history(conversation_id: str, messages: list):
    """Save conversation history to DynamoDB."""
    table = dynamodb.Table(HISTORY_TABLE)
    table.put_item(Item={
        "conversation_id": conversation_id,
        "messages": json.dumps(messages[-50:]),  # Keep last 50 messages
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def chat(message: str, conversation_id: str = None) -> dict:
    """Process a chat message and return response."""
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    messages = get_conversation_history(conversation_id)
    messages.append({"role": "user", "content": message})

    # Call Bedrock
    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": messages,
            "tools": TOOLS,
        }),
    )

    result = json.loads(response["body"].read())
    stop_reason = result.get("stop_reason", "")

    # Handle tool use
    if stop_reason == "tool_use":
        assistant_message = {"role": "assistant", "content": result["content"]}
        messages.append(assistant_message)

        tool_results = []
        for block in result["content"]:
            if block.get("type") == "tool_use":
                tool_result = invoke_tool(block["name"], block["input"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": tool_result,
                })

        messages.append({"role": "user", "content": tool_results})

        # Get final response after tool use
        response2 = bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": SYSTEM_PROMPT,
                "messages": messages,
                "tools": TOOLS,
            }),
        )
        result = json.loads(response2["body"].read())

    # Extract text response
    response_text = ""
    for block in result.get("content", []):
        if block.get("type") == "text":
            response_text += block["text"]

    messages.append({"role": "assistant", "content": response_text})
    save_conversation_history(conversation_id, messages)

    return {
        "conversation_id": conversation_id,
        "response": response_text,
        "model": MODEL_ID,
        "usage": result.get("usage", {}),
    }


def handler(event, context):
    """API Gateway Lambda handler."""
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)

        message = body.get("message", "")
        conversation_id = body.get("conversation_id", "")

        if not message:
            return _response(400, {"error": "Message is required"})

        result = chat(message, conversation_id)
        return _response(200, result)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return _response(500, {"error": "Internal server error"})


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body),
    }
