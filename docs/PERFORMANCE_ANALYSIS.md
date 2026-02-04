# Performance Analysis & Optimization Recommendations

## Current Architecture Performance Profile

### Response Time Breakdown

Based on the current architecture, here's where time is spent:

```
Total Response Time: 30-45 seconds (for full sequence)

1. WebSocket → Lambda (Initial)          ~50-100ms
2. Lambda Async Invocation               ~100-200ms
3. Lambda → AgentCore (SigV4 + Network)  ~200-500ms
4. AgentCore → MCP Server (Cold Start)   ~2-5 seconds (first call)
5. MCP Server → Bedrock API              ~5-15 seconds (per LLM call)
6. Bedrock Processing (Claude 4.5)       ~5-15 seconds (per call)
7. Response Path (AgentCore → Lambda)    ~200-500ms
8. Lambda → WebSocket (Send Message)     ~50-100ms

Per Tool Timing:
- generate_architecture_overview: 10-15s (LLM call)
- build_cfn_template: 5-10s (LLM call)
- validate_cfn_template: 1-2s (AWS API)
- generate_architecture_diagram: 2-5s (GraphViz)
- analyze_cost_optimization: 5-10s (LLM call)
- well_architected_review: 10-15s (LLM call)
```

## Bottleneck Analysis

### 1. **PRIMARY BOTTLENECK: Bedrock LLM Calls (70-80% of total time)**

**Current State**:
- Each LLM call takes 5-15 seconds
- We make 4 LLM calls in sequence (architecture, template, cost, review)
- Total LLM time: 25-50 seconds

**Why This Is The Bottleneck**:
- Claude Sonnet 4.5 processing time is inherent
- Large prompts (3000+ tokens) increase latency
- Sequential execution multiplies the delay

### 2. **SECONDARY BOTTLENECK: Lambda Async Pattern (5-10% of total time)**

**Current State**:
```python
# Lambda invokes itself asynchronously
lambda_client.invoke(
    FunctionName=context.function_name,
    InvocationType='Event',  # Async
    Payload=json.dumps({...})
)
```

**Overhead**:
- Initial Lambda invocation: ~50-100ms
- Async invocation overhead: ~100-200ms
- SigV4 signing: ~50-100ms
- Network round-trip to AgentCore: ~200-500ms

**Total Lambda Overhead**: ~400-900ms per tool call

### 3. **TERTIARY BOTTLENECK: AgentCore Cold Starts (5-10% on first call)**

**Current State**:
- First call to AgentCore: 2-5 seconds (container cold start)
- Subsequent calls: <500ms (warm container)
- AgentCore keeps containers warm for ~15 minutes

## Optimization Strategies

### Strategy 1: Parallel LLM Calls (HIGHEST IMPACT)

**Problem**: Sequential LLM calls waste time
**Solution**: Call multiple tools in parallel

**Current (Sequential)**:
```
Architecture (15s) → Template (10s) → Cost (10s) → Review (15s)
Total: 50 seconds
```

**Optimized (Parallel)**:
```
Architecture (15s) ┐
Template (10s)     ├─→ All complete in 15s (longest)
Cost (10s)         │
Review (15s)       ┘
Total: 15 seconds
```

**Implementation**:

```python
# In Lambda handler
import asyncio
import concurrent.futures

async def call_tools_parallel(tools_and_args):
    """Call multiple MCP tools in parallel"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(call_mcp_tool, tool, args)
            for tool, args in tools_and_args
        ]
        results = [future.result() for future in futures]
    return results

# Usage
tools = [
    ('generate_architecture_overview', {'prompt': prompt}),
    ('build_cfn_template', {'prompt': prompt}),
    ('analyze_cost_optimization', {'prompt': prompt}),
    ('well_architected_review', {'prompt': prompt})
]

results = await call_tools_parallel(tools)
```

**Expected Improvement**: 50s → 15s (70% reduction)

**Trade-offs**:
- ✅ Massive time savings
- ✅ Better user experience
- ❌ Higher concurrent Bedrock API calls (may hit throttling)
- ❌ More complex error handling
- ❌ Higher Lambda memory usage during parallel execution

---

### Strategy 2: Bedrock Latency-Optimized Inference (MEDIUM IMPACT)

**Problem**: Standard Bedrock inference has higher latency
**Solution**: Use latency-optimized inference mode

**Implementation**:

```python
def call_bedrock_with_retry(bedrock, model_id, body, max_retries=3):
    # Add performanceConfig for latency optimization
    body['performanceConfig'] = {
        'latency': 'optimized'  # Instead of 'standard'
    }
    
    response = bedrock.invoke_model(
        modelId=model_id,
        body=json.dumps(body)
    )
    return response
```

**Availability**:
- ✅ Claude 3.5 Haiku (supported)
- ❌ Claude Sonnet 4.5 (NOT YET SUPPORTED - check docs)
- ✅ Available in us-east-1, us-west-2

**Expected Improvement**: 5-15% latency reduction per LLM call

**Trade-offs**:
- ✅ Simple configuration change
- ✅ No code refactoring needed
- ❌ May not be available for Claude Sonnet 4.5
- ❌ Slightly higher cost
- ❌ Usage quotas apply

---

### Strategy 3: Remove Lambda Async Pattern (LOW-MEDIUM IMPACT)

**Problem**: Lambda async invocation adds 100-200ms overhead
**Solution**: Direct AgentCore invocation from initial Lambda

**Current Architecture**:
```
WebSocket → Lambda (sync) → Lambda (async) → AgentCore
            ↓ returns immediately
```

**Optimized Architecture**:
```
WebSocket → Lambda (sync, long timeout) → AgentCore
            ↓ returns after completion
```

**Implementation**:

```python
def lambda_handler(event, context):
    if route_key == '$default':
        body = json.loads(event.get('body', '{}'))
        tool = body.get('tool')
        arguments = body.get('arguments', {})
        
        # Send acknowledgment
        send_message(connection_id, {'type': 'acknowledged'})
        
        # Call MCP tool DIRECTLY (no async invoke)
        result = call_mcp_tool(tool, arguments)
        
        # Send result
        send_message(connection_id, {
            'type': 'response',
            'data': result
        })
        
        return {'statusCode': 200}
```

**Configuration Changes**:
```yaml
WebSocketLambda:
  Properties:
    Timeout: 600  # Already set to 10 minutes
    MemorySize: 2048  # Increase from 1024 for better network performance
```

**Expected Improvement**: 100-200ms per tool call

**Trade-offs**:
- ✅ Simpler code (no async pattern)
- ✅ Reduced Lambda invocations (lower cost)
- ✅ Faster response time
- ❌ Lambda must stay running for full duration
- ❌ Counts against Lambda concurrent execution limit
- ❌ WebSocket connection must stay open

---

### Strategy 4: Prompt Caching (MEDIUM IMPACT)

**Problem**: Sending same context repeatedly wastes tokens and time
**Solution**: Use Bedrock prompt caching

**Implementation**:

```python
def call_bedrock_with_caching(bedrock, model_id, system_prompt, user_message):
    body = {
        'anthropic_version': 'bedrock-2023-05-31',
        'max_tokens': 4096,
        'system': [
            {
                'type': 'text',
                'text': system_prompt,
                'cache_control': {'type': 'ephemeral'}  # Cache system prompt
            }
        ],
        'messages': [
            {'role': 'user', 'content': user_message}
        ]
    }
    
    response = bedrock.invoke_model(
        modelId=model_id,
        body=json.dumps(body)
    )
    return response
```

**Expected Improvement**:
- First call: Same latency
- Subsequent calls (within 5 min): 20-30% faster
- Cost reduction: 90% discount on cached tokens

**Trade-offs**:
- ✅ Faster subsequent calls
- ✅ Lower cost
- ✅ Simple implementation
- ❌ Only helps repeated calls with same context
- ❌ Cache expires after 5 minutes

---

### Strategy 5: Direct API Gateway → AgentCore Integration (HIGH IMPACT)

**Problem**: Lambda adds overhead and complexity
**Solution**: Direct integration from API Gateway to AgentCore

**New Architecture**:
```
WebSocket API Gateway → AgentCore Runtime (direct)
                      ↓
                   No Lambda!
```

**Implementation**:

```yaml
# API Gateway HTTP Integration
DefaultIntegration:
  Type: AWS::ApiGatewayV2::Integration
  Properties:
    ApiId: !Ref WebSocketApi
    IntegrationType: HTTP_PROXY
    IntegrationUri: !Sub 'https://bedrock-agentcore.${AWS::Region}.amazonaws.com/runtimes/${EncodedAgentArn}/invocations'
    IntegrationMethod: POST
    CredentialsArn: !GetAtt ApiGatewayRole.Arn  # For SigV4 signing
    RequestParameters:
      'integration.request.header.Content-Type': "'application/json'"
```

**Expected Improvement**: 400-900ms per tool call (removes all Lambda overhead)

**Trade-offs**:
- ✅ Eliminates Lambda cold starts
- ✅ Removes Lambda invocation overhead
- ✅ Simpler architecture
- ✅ Lower cost (no Lambda charges)
- ❌ Less flexibility (can't add custom logic)
- ❌ Harder to implement progress updates
- ❌ Limited error handling
- ❌ API Gateway must handle SigV4 signing

---

### Strategy 6: Provisioned Concurrency for Lambda (LOW IMPACT, HIGH COST)

**Problem**: Lambda cold starts add latency
**Solution**: Keep Lambda warm with provisioned concurrency

**Implementation**:

```yaml
WebSocketLambda:
  Properties:
    # ... existing config
    
ProvisionedConcurrency:
  Type: AWS::Lambda::ProvisionedConcurrencyConfig
  Properties:
    FunctionName: !Ref WebSocketLambda
    ProvisionedConcurrentExecutions: 2  # Keep 2 instances warm
    Qualifier: !GetAtt WebSocketLambda.Version
```

**Expected Improvement**: 50-100ms (eliminates cold start)

**Trade-offs**:
- ✅ Eliminates Lambda cold starts
- ✅ Consistent performance
- ❌ **HIGH COST**: ~$10-20/month per instance
- ❌ Only helps first invocation
- ❌ Not worth it for this use case

---

### Strategy 7: Optimize Bedrock Prompts (MEDIUM IMPACT)

**Problem**: Large prompts increase processing time
**Solution**: Reduce prompt size and complexity

**Current Prompts**:
- System prompt: ~500 tokens
- User message: ~200-1000 tokens
- Total: ~700-1500 tokens per call

**Optimization**:

```python
# Before: Verbose system prompt
system_prompt = """You are a Senior AWS Solutions Architect. 
Analyze requirements and create comprehensive architecture overviews 
with clear reasoning for every decision.

Your response must include:
1. Executive Summary (2-3 sentences)
2. Architecture Diagram (ASCII art with AWS service icons/emojis)
3. Component Breakdown (each service with purpose and rationale)
...
[500+ tokens]
"""

# After: Concise system prompt
system_prompt = """AWS Solutions Architect. Create architecture overview:
1. Summary (2-3 sentences)
2. ASCII diagram with AWS icons
3. Component breakdown with rationale
4. Design decisions
5. Data flow
6. Security considerations
"""
```

**Expected Improvement**: 10-20% latency reduction

**Trade-offs**:
- ✅ Faster processing
- ✅ Lower cost
- ❌ May reduce output quality
- ❌ Requires careful prompt engineering

---

## Recommended Implementation Plan

### Phase 1: Quick Wins (1-2 hours, 30-40% improvement)

1. **Parallel LLM Calls** (Strategy 1)
   - Implement ThreadPoolExecutor for parallel tool calls
   - Expected: 50s → 15s

2. **Remove Lambda Async Pattern** (Strategy 3)
   - Direct AgentCore calls from initial Lambda
   - Expected: -200ms per call

3. **Optimize Prompts** (Strategy 7)
   - Reduce prompt verbosity
   - Expected: -10-20% per LLM call

**Total Expected Improvement**: 50s → 12-15s (70% reduction)

### Phase 2: Advanced Optimizations (4-8 hours, additional 10-20%)

4. **Bedrock Latency-Optimized Inference** (Strategy 2)
   - Add performanceConfig if supported for Claude Sonnet 4.5
   - Expected: -5-15% per LLM call

5. **Prompt Caching** (Strategy 4)
   - Cache system prompts
   - Expected: -20-30% on subsequent calls

**Total Expected Improvement**: 12-15s → 10-12s (75-80% total reduction)

### Phase 3: Architectural Changes (2-3 days, additional 5-10%)

6. **Direct API Gateway Integration** (Strategy 5)
   - Remove Lambda entirely
   - Expected: -400-900ms overhead

**Total Expected Improvement**: 10-12s → 9-11s (80-85% total reduction)

### NOT Recommended:

7. ❌ **Provisioned Concurrency** (Strategy 6)
   - High cost, low benefit
   - Only saves 50-100ms
   - Not worth $10-20/month per instance

---

## Performance Monitoring

### Key Metrics to Track

```python
import time

def call_mcp_tool_with_metrics(tool_name, arguments):
    metrics = {}
    
    # Track Lambda overhead
    start = time.time()
    
    # Track SigV4 signing
    sig_start = time.time()
    # ... signing code ...
    metrics['sigv4_time'] = time.time() - sig_start
    
    # Track network call
    network_start = time.time()
    response = urllib.request.urlopen(req, timeout=300)
    metrics['network_time'] = time.time() - network_start
    
    # Track total time
    metrics['total_time'] = time.time() - start
    
    # Log to CloudWatch
    print(json.dumps({
        'tool': tool_name,
        'metrics': metrics
    }))
    
    return response
```

### CloudWatch Insights Queries

```sql
-- Average response time by tool
fields tool, metrics.total_time
| stats avg(metrics.total_time) as avg_time by tool
| sort avg_time desc

-- P50, P90, P99 latencies
fields tool, metrics.total_time
| stats 
    pct(metrics.total_time, 50) as p50,
    pct(metrics.total_time, 90) as p90,
    pct(metrics.total_time, 99) as p99
  by tool

-- Identify bottlenecks
fields tool, metrics.sigv4_time, metrics.network_time, metrics.total_time
| filter metrics.total_time > 10000
```

---

## Cost-Benefit Analysis

| Strategy | Implementation Time | Expected Improvement | Cost Impact | Recommendation |
|----------|-------------------|---------------------|-------------|----------------|
| Parallel LLM Calls | 1-2 hours | 70% | None | ✅ **DO THIS FIRST** |
| Remove Async Pattern | 30 min | 5-10% | -$0.50/month | ✅ **DO THIS** |
| Optimize Prompts | 1 hour | 10-20% | -10% Bedrock cost | ✅ **DO THIS** |
| Latency-Optimized | 15 min | 5-15% | +5% Bedrock cost | ✅ **DO IF AVAILABLE** |
| Prompt Caching | 30 min | 20-30% (repeat) | -90% cached tokens | ✅ **DO THIS** |
| Direct Integration | 2-3 days | 5-10% | -$1/month | ⚠️ **CONSIDER** |
| Provisioned Concurrency | 15 min | 2-3% | +$20/month | ❌ **DON'T DO** |

---

## Conclusion

**Primary Bottleneck**: Bedrock LLM calls (70-80% of time)
**Secondary Bottleneck**: Lambda async pattern (5-10% of time)

**Recommended Actions**:
1. ✅ Implement parallel LLM calls (70% improvement)
2. ✅ Remove Lambda async pattern (5-10% improvement)
3. ✅ Optimize prompts (10-20% improvement)
4. ✅ Add prompt caching (20-30% on repeats)

**Expected Result**: 50s → 10-12s (75-80% reduction)

**NOT Recommended**: Provisioned concurrency (high cost, low benefit)

The Lambda async pattern is NOT the primary bottleneck - it's the sequential LLM calls. Focus optimization efforts on parallelization first.
