"""
WebSocket Lambda handler for CloudFormation Builder
"""
import json
import os
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import urllib.request

AGENT_ARN = os.environ['AGENT_ARN']
REGION = os.environ.get('REGION', 'us-east-1')

# Lambda client for async self-invocation (avoids API Gateway 29s timeout)
lambda_client = boto3.client('lambda')

def get_apigw_client(event):
    """Get API Gateway Management API client for the WebSocket endpoint (event must have requestContext)."""
    domain = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    endpoint = f"https://{domain}/{stage}"
    return boto3.client('apigatewaymanagementapi', endpoint_url=endpoint)

def send_message(connection_id, message, event):
    try:
        client = get_apigw_client(event)
        client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message)
        )
        return True
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def call_mcp_tool(tool_name, arguments):
    """Call MCP server via AgentCore"""
    session = boto3.Session()
    credentials = session.get_credentials()
    
    encoded_arn = AGENT_ARN.replace(':', '%3A').replace('/', '%2F')
    mcp_url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    
    request_body = json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {
            'name': tool_name,
            'arguments': arguments
        }
    })
    
    aws_request = AWSRequest(
        method='POST',
        url=mcp_url,
        data=request_body,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
        }
    )
    
    SigV4Auth(credentials, 'bedrock-agentcore', REGION).add_auth(aws_request)
    
    req = urllib.request.Request(
        mcp_url,
        data=request_body.encode('utf-8'),
        headers=dict(aws_request.headers)
    )
    
    with urllib.request.urlopen(req, timeout=300) as response:
        response_data = response.read().decode('utf-8')
        print(f"Response data (first 500 chars): {response_data[:500]}")
        
        # Parse SSE format - look for "data: " line
        lines = response_data.split('\n')
        for line in lines:
            if line.startswith('data: '):
                json_data = line[6:]  # Remove 'data: ' prefix
                result = json.loads(json_data)
                return result
        
        # If no data line found
        return {'error': 'No data in SSE response'}


def lambda_handler(event, context):
    # Handle async processing (second invocation): run MCP call and push result over WebSocket.
    # This path is used to avoid API Gateway's 29-second integration timeout.
    if 'async_processing' in event:
        async_event = event['async_processing']
        tool = async_event['tool']
        arguments = async_event['arguments']
        request_id = async_event['requestId']
        connection_id = async_event['connectionId']
        original_event = async_event['event']

        print(f"Async processing: {tool}, requestId: {request_id}")

        try:
            send_message(connection_id, {
                'type': 'progress',
                'requestId': request_id,
                'progress': 50,
                'message': f'Processing {tool}...'
            }, original_event)

            result = call_mcp_tool(tool, arguments)

            if 'error' in result:
                send_message(connection_id, {
                    'type': 'error',
                    'requestId': request_id,
                    'error': result['error']
                }, original_event)
                return {'statusCode': 200}

            if result.get('result', {}).get('content'):
                content_text = result['result']['content'][0]['text']
                data = json.loads(content_text)
                send_message(connection_id, {
                    'type': 'response',
                    'requestId': request_id,
                    'tool': tool,
                    'data': data,
                    'status': 'completed'
                }, original_event)
            else:
                send_message(connection_id, {
                    'type': 'error',
                    'requestId': request_id,
                    'error': result.get('error', 'No result from MCP server')
                }, original_event)
        except Exception as e:
            print(f"Error in async processing: {e}")
            import traceback
            traceback.print_exc()
            send_message(connection_id, {
                'type': 'error',
                'requestId': request_id,
                'error': str(e)
            }, original_event)

        return {'statusCode': 200}

    # Normal WebSocket route handling
    route_key = event.get('requestContext', {}).get('routeKey')
    connection_id = event.get('requestContext', {}).get('connectionId')

    print(f"Route: {route_key}, Connection: {connection_id}")

    try:
        if route_key == '$connect':
            print(f"Client connected: {connection_id}")
            return {'statusCode': 200}

        elif route_key == '$disconnect':
            print(f"Client disconnected: {connection_id}")
            return {'statusCode': 200}

        elif route_key == '$default':
            body = json.loads(event.get('body', '{}'))
            request_id = body.get('id')
            tool = body.get('tool')
            arguments = body.get('arguments', {})

            print(f"Tool: {tool}, Request: {request_id}")

            send_message(connection_id, {
                'type': 'acknowledged',
                'requestId': request_id,
                'tool': tool
            }, event)

            send_message(connection_id, {
                'type': 'progress',
                'requestId': request_id,
                'progress': 10,
                'message': f'Calling {tool}...'
            }, event)

            # Invoke self asynchronously so this request returns within API Gateway's 29s limit.
            # The async invocation will call AgentCore (~68s) and then post_to_connection.
            lambda_client.invoke(
                FunctionName=context.function_name,
                InvocationType='Event',
                Payload=json.dumps({
                    'async_processing': {
                        'tool': tool,
                        'arguments': arguments,
                        'requestId': request_id,
                        'connectionId': connection_id,
                        'event': event
                    }
                })
            )

            return {'statusCode': 200}

        else:
            return {'statusCode': 400}

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

        if route_key == '$default':
            try:
                body = json.loads(event.get('body', '{}'))
                send_message(connection_id, {
                    'type': 'error',
                    'requestId': body.get('id'),
                    'error': str(e)
                }, event)
            except Exception:
                pass

        return {'statusCode': 500}
