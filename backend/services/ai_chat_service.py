"""
AI Chat Service - Orchestrates AI conversations with tool execution.
Calls Anthropic Claude API, processes tool_use blocks, executes via ContainerService.
"""
import json
import httpx
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from models import Assessment, Card, CommandHistory, ReconData
from services.container_service import ContainerService
from utils.logger import get_logger

logger = get_logger(__name__)

# Simplified tool definitions for Claude API (matching MCP tools that make sense from UI)
CHAT_TOOLS = [
    {
        "name": "execute_command",
        "description": "Execute a shell command in the pentesting container. Use for nmap, ffuf, nuclei, sqlmap, gobuster, nikto, curl, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "phase": {"type": "string", "description": "Current phase: recon, scanning, exploitation, post_exploitation"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "add_finding",
        "description": "Document a vulnerability finding",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Finding title"},
                "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]},
                "target_service": {"type": "string", "description": "Affected service/endpoint"},
                "technical_analysis": {"type": "string", "description": "Technical details"},
                "proof": {"type": "string", "description": "Evidence/proof of concept"},
                "context": {"type": "string", "description": "Remediation recommendation"}
            },
            "required": ["title", "severity"]
        }
    },
    {
        "name": "add_observation",
        "description": "Document a security observation (not a vulnerability)",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Observation title"},
                "technical_analysis": {"type": "string", "description": "Details"},
                "target_service": {"type": "string", "description": "Related service"}
            },
            "required": ["title"]
        }
    },
    {
        "name": "add_recon_data",
        "description": "Log reconnaissance data (discovered domain, IP, service, technology, endpoint)",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_type": {"type": "string", "description": "Type: subdomain, service, technology, endpoint, ip"},
                "name": {"type": "string", "description": "Name/value of the finding"},
                "details": {"type": "object", "description": "Additional details as JSON"}
            },
            "required": ["data_type", "name"]
        }
    },
]

SYSTEM_PROMPT = """You are AIDA, an AI-driven security assessment assistant. You are conducting a penetration test.

Assessment: {assessment_name}
Scope: {scope}
Targets: {targets}

You have access to a pentesting container with tools like nmap, ffuf, nuclei, nikto, sqlmap, gobuster, curl, etc.

Guidelines:
- Execute commands methodically, analyze results before proceeding
- Document findings with proper severity ratings
- Log recon data as you discover it
- Be thorough but respect the defined scope
- Explain what you're doing and why in plain language
- When you find a vulnerability, use add_finding to document it
- After each command, analyze the output and decide next steps

Respond in the same language as the user's message."""


class AIChatService:
    def __init__(self, api_key: str, provider: str, db: Session, async_db: AsyncSession):
        self.api_key = api_key
        self.provider = provider
        self.db = db
        self.async_db = async_db
        self.container_service = ContainerService()

    async def chat(
        self,
        assessment_id: int,
        assessment_name: str,
        message: str,
        model: Optional[str] = None,
    ) -> dict:
        """Process a chat message: call Claude, execute tools, return response."""

        assessment = self.db.query(Assessment).filter(Assessment.id == assessment_id).first()
        scope = assessment.scope or "Not defined"
        targets = ", ".join(assessment.target_domains or []) or "Not specified"

        system = SYSTEM_PROMPT.format(
            assessment_name=assessment_name,
            scope=scope,
            targets=targets,
        )

        # Get recent command history for context
        recent_cmds = (
            self.db.query(CommandHistory)
            .filter(CommandHistory.assessment_id == assessment_id)
            .order_by(CommandHistory.created_at.desc())
            .limit(5)
            .all()
        )
        if recent_cmds:
            history_ctx = "\n\nRecent commands:\n"
            for cmd in reversed(recent_cmds):
                status = "OK" if cmd.success else "FAIL"
                output_preview = (cmd.stdout or "")[:200]
                history_ctx += f"[{status}] $ {cmd.command}\n{output_preview}\n\n"
            system += history_ctx

        messages = [{"role": "user", "content": message}]
        all_tool_calls = []

        if self.provider == "anthropic":
            return await self._chat_anthropic(system, messages, assessment_id, model, all_tool_calls)
        else:
            return {"response": f"Provider '{self.provider}' not supported. Use 'anthropic'.", "tool_calls": [], "error": "unsupported_provider"}

    async def _chat_anthropic(self, system, messages, assessment_id, model, all_tool_calls, depth=0):
        """Call Claude API with tool use loop"""
        if depth > 10:
            return {"response": "Maximum tool call depth reached.", "tool_calls": all_tool_calls}

        model = model or "claude-sonnet-4-20250514"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 4096,
                    "system": system,
                    "messages": messages,
                    "tools": CHAT_TOOLS,
                },
            )

        if resp.status_code != 200:
            error_text = resp.text
            logger.error("Anthropic API error", status=resp.status_code, body=error_text[:500])
            return {"response": "", "tool_calls": all_tool_calls, "error": f"API error {resp.status_code}: {error_text[:300]}"}

        data = resp.json()
        stop_reason = data.get("stop_reason")
        content_blocks = data.get("content", [])

        # Extract text and tool_use blocks
        text_parts = []
        tool_uses = []

        for block in content_blocks:
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_uses.append(block)

        if not tool_uses or stop_reason != "tool_use":
            # No tools to call — return the response
            return {"response": "\n".join(text_parts), "tool_calls": all_tool_calls}

        # Execute tools and build tool_result messages
        tool_results = []
        for tool_use in tool_uses:
            tool_name = tool_use["name"]
            tool_input = tool_use["input"]
            tool_id = tool_use["id"]

            result_text = await self._execute_tool(tool_name, tool_input, assessment_id)

            all_tool_calls.append({
                "tool": tool_name,
                "input": tool_input,
                "output": result_text[:1000],  # Trim for response
            })

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_text[:15000],  # Trim for API limits
            })

        # Continue conversation with tool results
        messages.append({"role": "assistant", "content": content_blocks})
        messages.append({"role": "user", "content": tool_results})

        # Prepend any text from this turn
        sub_result = await self._chat_anthropic(system, messages, assessment_id, model, all_tool_calls, depth + 1)
        full_text = "\n".join(text_parts)
        if full_text and sub_result["response"]:
            sub_result["response"] = full_text + "\n\n" + sub_result["response"]
        elif full_text:
            sub_result["response"] = full_text
        return sub_result

    async def _execute_tool(self, name: str, args: dict, assessment_id: int) -> str:
        """Execute a tool and return the result as text"""
        try:
            if name == "execute_command":
                return await self._exec_command(args, assessment_id)
            elif name == "add_finding":
                return self._add_finding(args, assessment_id)
            elif name == "add_observation":
                return self._add_observation(args, assessment_id)
            elif name == "add_recon_data":
                return self._add_recon(args, assessment_id)
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            logger.error("Tool execution error", tool=name, error=str(e))
            return f"Error executing {name}: {str(e)}"

    async def _exec_command(self, args: dict, assessment_id: int) -> str:
        """Execute command in container via ContainerService"""
        command = args.get("command", "")
        phase = args.get("phase", "recon")

        result = await self.container_service.execute_and_log_command(
            assessment_id=assessment_id,
            command=command,
            phase=phase,
            db=self.async_db,
        )

        output = ""
        if result.stdout:
            output += result.stdout[:10000]
        if result.stderr:
            output += f"\nSTDERR: {result.stderr[:2000]}"
        output += f"\n[Exit code: {result.returncode}]"
        return output

    def _add_finding(self, args: dict, assessment_id: int) -> str:
        """Create a finding card"""
        card = Card(
            assessment_id=assessment_id,
            card_type="finding",
            title=args["title"],
            severity=args.get("severity", "INFO"),
            target_service=args.get("target_service"),
            technical_analysis=args.get("technical_analysis"),
            proof=args.get("proof"),
            context=args.get("context"),
            status="confirmed",
        )
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return f"Finding added: [{card.severity}] {card.title} (id={card.id})"

    def _add_observation(self, args: dict, assessment_id: int) -> str:
        """Create an observation card"""
        card = Card(
            assessment_id=assessment_id,
            card_type="observation",
            title=args["title"],
            technical_analysis=args.get("technical_analysis"),
            target_service=args.get("target_service"),
        )
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return f"Observation added: {card.title} (id={card.id})"

    def _add_recon(self, args: dict, assessment_id: int) -> str:
        """Add recon data"""
        recon = ReconData(
            assessment_id=assessment_id,
            data_type=args["data_type"],
            name=args["name"],
            details=args.get("details"),
            discovered_in_phase="recon",
        )
        self.db.add(recon)
        self.db.commit()
        self.db.refresh(recon)
        return f"Recon data added: {recon.data_type} - {recon.name} (id={recon.id})"
