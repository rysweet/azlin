"""Prompt templates for azdoit auto mode."""

OBJECTIVE_TEMPLATE = """You must pursue this objective step by step, iteratively, until it is achieved.

OBJECTIVE: {user_request}

CONTEXT:
You are assisting with Azure infrastructure management. Your goal is to help achieve the stated objective by researching best practices, testing approaches, and ultimately generating reusable infrastructure-as-code.

REQUIREMENTS:
1. Pursue the objective methodically through multiple iterations
2. When the goal is achieved, output an example script
3. Use az CLI, Terraform, or other appropriate tools
4. Include comments explaining what the script does
5. Make scripts idempotent (safe to run multiple times)
6. Follow Azure best practices

LEARNING RESOURCES:
- Azure CLI Reference: https://learn.microsoft.com/en-us/cli/azure/?view=azure-cli-latest
- Terraform Azure Provider: https://learn.microsoft.com/en-us/azure/developer/terraform/
- Terraform Azure Tutorial: https://developer.hashicorp.com/terraform/tutorials/azure-get-started
- Use web search for additional resources as needed

OUTPUT FORMAT:
When the objective is achieved, provide:
1. Summary: Brief explanation of what was accomplished
2. Script: Complete, runnable script with comments (bash, terraform, etc.)
3. Instructions: Step-by-step guide to run the script
4. Notes: Any prerequisites, costs, or considerations

EXECUTION STYLE:
- Be thorough but efficient
- Test assumptions via research
- Adapt based on findings
- Prefer standard solutions over custom
- Document your reasoning"""


def format_objective_prompt(user_request: str, max_length: int = 5000) -> str:
    """Format the objective prompt template with user request.

    Args:
        user_request: The user's natural language objective
        max_length: Maximum length for user request (default 5000 chars)

    Returns:
        Formatted prompt string ready for auto mode

    Raises:
        ValueError: If user_request exceeds max_length
    """
    if len(user_request) > max_length:
        msg = f"Request too long ({len(user_request)} chars). Maximum is {max_length} characters."
        raise ValueError(msg)

    # Basic prompt injection detection
    dangerous_patterns = ["ignore previous", "ignore instructions", "system:", "assistant:"]
    lower_request = user_request.lower()
    for pattern in dangerous_patterns:
        if pattern in lower_request:
            msg = f"Request contains potentially unsafe pattern: '{pattern}'"
            raise ValueError(msg)

    return OBJECTIVE_TEMPLATE.format(user_request=user_request)
