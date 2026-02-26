"""
LADX - Core Agent Logic
================================
This is the brain of LADX.
It uses OpenRouter (free models) as the AI engine and provides specialized tools
for PLC code generation, troubleshooting, and conversion.
"""

import os
import json
import re
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI
from config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL, AI_MODEL, MAX_TOKENS,
    OUTPUT_DIR, TIA_BRIDGE_URL, PLATFORMS,
    get_system_prompt
)

# ===========================================
# Initialize OpenRouter Client (OpenAI-compatible)
# ===========================================
client = OpenAI(
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY,
)

# ===========================================
# Tool Definitions for OpenAI function calling format
# ===========================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_plc_code",
            "description": "Generate complete, compilable PLC code from a natural language description. Supports Siemens SCL, Allen-Bradley Structured Text, and CODESYS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Detailed description of what the PLC program should do"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["siemens", "allen_bradley", "codesys"],
                        "description": "Target PLC platform"
                    },
                    "block_type": {
                        "type": "string",
                        "enum": ["FB", "FC", "OB", "AOI", "Program", "Function"],
                        "description": "Type of PLC block to generate"
                    },
                    "block_name": {
                        "type": "string",
                        "description": "Name for the PLC block"
                    }
                },
                "required": ["description", "platform"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "troubleshoot_plc",
            "description": "Diagnose PLC faults, interpret error codes, and provide step-by-step troubleshooting procedures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem_description": {
                        "type": "string",
                        "description": "Description of the problem, error codes, LED status, symptoms"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["siemens", "allen_bradley"],
                        "description": "PLC platform"
                    },
                    "cpu_model": {
                        "type": "string",
                        "description": "Specific CPU model (e.g., S7-1500, 1756-L85E)"
                    }
                },
                "required": ["problem_description", "platform"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "convert_plc_code",
            "description": "Convert PLC code from one platform to another (e.g., Siemens to Allen-Bradley or vice versa).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_code": {
                        "type": "string",
                        "description": "The original PLC code to convert"
                    },
                    "source_platform": {
                        "type": "string",
                        "enum": ["siemens", "allen_bradley", "codesys"],
                        "description": "Original platform"
                    },
                    "target_platform": {
                        "type": "string",
                        "enum": ["siemens", "allen_bradley", "codesys"],
                        "description": "Target platform to convert to"
                    }
                },
                "required": ["source_code", "source_platform", "target_platform"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_plc_code",
            "description": "Analyze and explain existing PLC code - what it does, how it works, and suggest improvements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The PLC code to analyze"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["siemens", "allen_bradley", "codesys"],
                        "description": "Which platform the code is for"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_tag_list",
            "description": "Generate a structured tag/variable list for a PLC project, ready for import.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the system to generate tags for"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["siemens", "allen_bradley"],
                        "description": "Target platform"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["csv", "json", "xml"],
                        "description": "Output format for the tag list"
                    }
                },
                "required": ["description", "platform"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_code_to_file",
            "description": "Save generated PLC code to a file in the output directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name for the output file (without path)"
                    },
                    "content": {
                        "type": "string",
                        "description": "The code content to save"
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["siemens", "allen_bradley", "codesys"],
                        "description": "Platform (determines file extension)"
                    }
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_to_tia_portal",
            "description": "Send generated code to TIA Portal via the Windows bridge server. Requires the bridge to be running on your Windows PC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_name": {
                        "type": "string",
                        "description": "Name of the block to create in TIA Portal"
                    },
                    "scl_code": {
                        "type": "string",
                        "description": "The SCL code to import"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["import", "compile", "export"],
                        "description": "Action to perform in TIA Portal"
                    }
                },
                "required": ["block_name", "action"]
            }
        }
    }
]


# ===========================================
# Tool Implementations
# ===========================================

def handle_generate_plc_code(params: dict) -> str:
    """Generate PLC code using AI."""
    platform_info = PLATFORMS.get(params["platform"], PLATFORMS["siemens"])
    block_type = params.get("block_type", "FB")
    block_name = params.get("block_name", "NewBlock")

    prompt = f"""Generate a complete, compilable {block_type} named '{block_name}'
for {platform_info['name']} in {platform_info['language']}.

Description of what it should do:
{params['description']}

Requirements:
- Include ALL variable declarations
- Add comprehensive comments
- Include error handling and fault detection
- Follow the naming conventions in your system prompt
- The code must compile without errors in {platform_info['name']}
- Generate the COMPLETE block, not a snippet

Return ONLY the PLC code, no additional explanation."""

    response = client.chat.completions.create(
        model=AI_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )

    code = response.choices[0].message.content

    # Auto-save to output directory
    ext = platform_info["file_ext"]
    filename = f"{block_name}{ext}"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(code, encoding="utf-8")

    return f"Generated {block_type} '{block_name}' for {platform_info['name']}.\nSaved to: {filepath}\n\n{code}"


def handle_troubleshoot_plc(params: dict) -> str:
    """Troubleshoot PLC issues."""
    platform_info = PLATFORMS.get(params["platform"], PLATFORMS["siemens"])
    cpu = params.get("cpu_model", "not specified")

    prompt = f"""Troubleshoot this {platform_info['name']} PLC issue:

CPU Model: {cpu}
Problem: {params['problem_description']}

Provide your diagnosis in this exact structure:
1. MOST LIKELY CAUSE: (one paragraph)
2. DIAGNOSTIC STEPS: (numbered step-by-step)
3. SOLUTION: (how to fix it)
4. PREVENTION: (how to prevent this in the future)
5. RELATED ISSUES: (other things to check while you're at it)"""

    response = client.chat.completions.create(
        model=AI_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content


def handle_convert_plc_code(params: dict) -> str:
    """Convert code between PLC platforms."""
    source = PLATFORMS.get(params["source_platform"], PLATFORMS["siemens"])
    target = PLATFORMS.get(params["target_platform"], PLATFORMS["allen_bradley"])

    prompt = f"""Convert this PLC code from {source['name']} ({source['language']})
to {target['name']} ({target['language']}).

SOURCE CODE:
```
{params['source_code']}
```

CONVERSION REQUIREMENTS:
1. Map ALL data types correctly (watch INT size differences!)
2. Convert all instructions to target platform equivalents
3. Adapt timer/counter syntax
4. Adjust array indexing (Siemens 1-based vs AB 0-based)
5. Flag ANY instructions without direct equivalents
6. Preserve ALL comments (translate if needed)
7. Maintain the same logic flow and structure

Return:
- The complete converted code
- A conversion notes section listing all changes made
- Any warnings about behavioral differences"""

    response = client.chat.completions.create(
        model=AI_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )

    result = response.choices[0].message.content

    # Auto-save
    filename = f"converted_{datetime.now().strftime('%Y%m%d_%H%M%S')}{target['file_ext']}"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(result, encoding="utf-8")

    return f"Conversion complete. Saved to: {filepath}\n\n{result}"


def handle_explain_plc_code(params: dict) -> str:
    """Explain PLC code."""
    platform = params.get("platform", "auto-detect")

    prompt = f"""Analyze this PLC code (platform: {platform}):

```
{params['code']}
```

Provide:
1. SUMMARY: What this code does (2-3 sentences)
2. INPUTS/OUTPUTS: List all I/O with descriptions
3. LOGIC FLOW: Step-by-step explanation of the logic
4. POTENTIAL ISSUES: Any bugs, inefficiencies, or safety concerns
5. SUGGESTED IMPROVEMENTS: How to make this code better"""

    response = client.chat.completions.create(
        model=AI_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content


def handle_generate_tag_list(params: dict) -> str:
    """Generate a tag list for a PLC project."""
    platform_info = PLATFORMS.get(params["platform"], PLATFORMS["siemens"])
    fmt = params.get("format", "csv")

    prompt = f"""Generate a complete PLC tag list for {platform_info['name']}.

System description: {params['description']}

Output format: {fmt}
Include: Tag name, Data type, Address (if applicable), Description, Initial value, Engineering unit

Follow standard naming conventions:
- Digital inputs: DI_xxx or I_xxx
- Digital outputs: DO_xxx or Q_xxx
- Analog inputs: AI_xxx
- Analog outputs: AO_xxx
- Internal: M_xxx or internal tag
- Timers: T_xxx or TON_xxx
- Counters: C_xxx or CTU_xxx"""

    response = client.chat.completions.create(
        model=AI_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}]
    )

    result = response.choices[0].message.content

    # Save tag list
    ext = {"csv": ".csv", "json": ".json", "xml": ".xml"}.get(fmt, ".csv")
    filename = f"taglist_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(result, encoding="utf-8")

    return f"Tag list generated. Saved to: {filepath}\n\n{result}"


def handle_save_code_to_file(params: dict) -> str:
    """Save code to a file."""
    platform = params.get("platform", "siemens")
    platform_info = PLATFORMS.get(platform, PLATFORMS["siemens"])

    filename = params["filename"]
    if not any(filename.endswith(ext) for ext in [".scl", ".st", ".xml", ".csv", ".json", ".l5x"]):
        filename += platform_info["file_ext"]

    filepath = OUTPUT_DIR / filename
    filepath.write_text(params["content"], encoding="utf-8")

    return f"File saved: {filepath}"


def handle_send_to_tia_portal(params: dict) -> str:
    """Send code to TIA Portal via Windows bridge."""
    action = params["action"]
    block_name = params["block_name"]

    try:
        if action == "import":
            response = httpx.post(
                f"{TIA_BRIDGE_URL}/api/import-scl",
                json={
                    "block_name": block_name,
                    "scl_code": params.get("scl_code", "")
                },
                timeout=30.0
            )
        elif action == "compile":
            response = httpx.post(
                f"{TIA_BRIDGE_URL}/api/compile",
                json={"block_name": block_name},
                timeout=60.0
            )
        elif action == "export":
            response = httpx.post(
                f"{TIA_BRIDGE_URL}/api/export-block",
                json={"block_name": block_name},
                timeout=30.0
            )
        else:
            return f"Unknown action: {action}"

        result = response.json()
        if result.get("success"):
            return f"TIA Portal: {action} '{block_name}' - SUCCESS\n{result.get('message', '')}"
        else:
            return f"TIA Portal: {action} '{block_name}' - FAILED\n{result.get('message', '')}"

    except httpx.ConnectError:
        return (
            f"Cannot connect to TIA Portal bridge at {TIA_BRIDGE_URL}\n"
            "Make sure tia_bridge_server.py is running on your Windows PC."
        )
    except Exception as e:
        return f"Error communicating with TIA Portal bridge: {str(e)}"


# ===========================================
# Tool Router
# ===========================================
TOOL_HANDLERS = {
    "generate_plc_code": handle_generate_plc_code,
    "troubleshoot_plc": handle_troubleshoot_plc,
    "convert_plc_code": handle_convert_plc_code,
    "explain_plc_code": handle_explain_plc_code,
    "generate_tag_list": handle_generate_tag_list,
    "save_code_to_file": handle_save_code_to_file,
    "send_to_tia_portal": handle_send_to_tia_portal,
}


# ===========================================
# Main Agent Loop
# ===========================================

class PLCAgent:
    """
    The main LADX Agent.
    Handles conversation, tool use, and maintains chat history.
    Uses OpenRouter with OpenAI-compatible API.
    """

    def __init__(self):
        self.conversation_history = []
        self.system_prompt = get_system_prompt()
        self.model_override = None  # Set per-request to override AI_MODEL

    @property
    def active_model(self):
        """Return the model to use: override if set, otherwise default."""
        return self.model_override or AI_MODEL

    def chat(self, user_message: str) -> str:
        """
        Send a message to the agent and get a response.
        Handles multi-turn tool use automatically via OpenAI function calling.
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Build messages with system prompt
        messages = [
            {"role": "system", "content": self.system_prompt}
        ] + self.conversation_history

        # Call OpenRouter with tools
        try:
            response = client.chat.completions.create(
                model=self.active_model,
                max_tokens=MAX_TOKENS,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                extra_headers={
                    "HTTP-Referer": "https://ladx.dev",
                    "X-Title": "LADX - PLC AI Agent"
                }
            )
        except Exception as e:
            # If tool calling fails (some free models don't support it),
            # fall back to plain chat without tools
            try:
                response = client.chat.completions.create(
                    model=self.active_model,
                    max_tokens=MAX_TOKENS,
                    messages=messages,
                    extra_headers={
                        "HTTP-Referer": "https://ladx.dev",
                        "X-Title": "LADX - PLC AI Agent"
                    }
                )
            except Exception as e2:
                error_msg = f"Error calling AI: {str(e2)}"
                self.conversation_history.pop()  # Remove failed user message
                return error_msg

        # Process the response (may involve tool calls)
        final_response = self._process_response(response)
        return final_response

    def _process_response(self, response) -> str:
        """Process OpenRouter response, handling any tool calls."""
        collected_text = []
        message = response.choices[0].message

        # Loop for multi-turn tool use
        while message.tool_calls:
            # Collect any text content
            if message.content:
                collected_text.append(message.content)

            # Add assistant message with tool calls to history
            self.conversation_history.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]
            })

            # Execute all tool calls
            for tc in message.tool_calls:
                handler = TOOL_HANDLERS.get(tc.function.name)
                if handler:
                    try:
                        args = json.loads(tc.function.arguments)
                        result = handler(args)
                    except Exception as e:
                        result = f"Tool error: {str(e)}"
                else:
                    result = f"Unknown tool: {tc.function.name}"

                # Add tool result to history
                self.conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result
                })

            # Get next response
            messages = [
                {"role": "system", "content": self.system_prompt}
            ] + self.conversation_history

            try:
                next_response = client.chat.completions.create(
                    model=self.active_model,
                    max_tokens=MAX_TOKENS,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                    extra_headers={
                        "HTTP-Referer": "https://ladx.dev",
                        "X-Title": "LADX - PLC AI Agent"
                    }
                )
                message = next_response.choices[0].message
            except Exception:
                # If follow-up fails, break out of loop
                break

        # Collect final text
        if message.content:
            collected_text.append(message.content)

        # Add final assistant message to history
        self.conversation_history.append({
            "role": "assistant",
            "content": message.content or ""
        })

        return "\n".join(collected_text) if collected_text else "I received your message but couldn't generate a response. Please try again."

    def reset(self):
        """Clear conversation history."""
        self.conversation_history = []

    def get_history_length(self) -> int:
        """Get number of messages in conversation."""
        return len(self.conversation_history)


# ===========================================
# CLI Interface (for testing)
# ===========================================

def main():
    """Run the agent in terminal/CLI mode."""
    print("=" * 60)
    print("  LADX - Command Line Interface")
    print(f"  Model: {AI_MODEL}")
    print(f"  Provider: OpenRouter")
    print("  Type 'quit' to exit, 'reset' to clear history")
    print("=" * 60)

    agent = PLCAgent()

    while True:
        try:
            user_input = input("\n🔧 You: ").strip()

            if not user_input:
                continue
            if user_input.lower() == "quit":
                print("Goodbye!")
                break
            if user_input.lower() == "reset":
                agent.reset()
                print("Conversation cleared.")
                continue

            print("\n🤖 LADX is thinking...\n")
            response = agent.chat(user_input)
            print(f"🤖 LADX:\n{response}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            print("Try again or type 'reset' to start fresh.")


if __name__ == "__main__":
    main()
