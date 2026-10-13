"""Span attribute names. Well-known keys follow the OpenTelemetry GenAI semantic conventions
(still marked 'development' upstream); everything app-specific lives under `blackbox.*`."""

# app-specific
RUN_ID = "blackbox.run_id"
SPAN_TYPE = "blackbox.span_type"  # agent | llm | tool
AGENT_INPUT = "blackbox.agent.input"
AGENT_OUTPUT = "blackbox.agent.output"
AGENT_STEPS = "blackbox.agent.steps"
AGENT_STEP = "blackbox.agent.step"
MODEL_PROMPT = "blackbox.model.prompt"
MODEL_COMPLETION = "blackbox.model.completion"
MODEL_TOOL_CALLS = "blackbox.model.tool_calls"
TOOL_ARGS = "blackbox.tool.args"
TOOL_OUTPUT = "blackbox.tool.output"

# GenAI semantic conventions
GEN_AI_OPERATION = "gen_ai.operation.name"  # invoke_agent | chat | execute_tool
GEN_AI_PROVIDER = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
