"""
MCP Tool Handlers - Refactored handlers for all MCP tools
Handles: load_assessment, add_*, list_*, update_*, execute, pentesting tools
"""
from typing import List, Optional, Tuple
from mcp.types import TextContent
from scan_parsers import parse_scan_output


def _calculate_cvss4_score(vector: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Calculate CVSS 4.0 score and severity from a vector string.
    Returns (score, severity) or (None, None) on error.
    Uses the cvss library if available, otherwise falls back to None.
    """
    try:
        from cvss import CVSS4
        c = CVSS4(vector)
        score = float(c.base_score)
        severity = _score_to_severity(score)
        return score, severity
    except Exception:
        pass
    return None, None


def _score_to_severity(score: float) -> str:
    """Map CVSS 4.0 numeric score to severity label (FIRST standard thresholds)."""
    if score >= 9.0:
        return "CRITICAL"
    elif score >= 7.0:
        return "HIGH"
    elif score >= 4.0:
        return "MEDIUM"
    elif score > 0.0:
        return "LOW"
    return "INFO"


async def handle_tool_call(name: str, arguments: dict, mcp_service) -> List[TextContent]:
    """Handle tool calls from Claude - Main dispatcher"""
    try:
        await mcp_service.initialize()

        # ========== Assessment Management ==========

        if name == "load_assessment":
            return await _handle_load_assessment(arguments, mcp_service)

        elif name == "create_assessment":
            return await _handle_create_assessment(arguments, mcp_service)

        elif name == "list_assessments":
            return await _handle_list_assessments(arguments, mcp_service)

        elif name == "list_containers":
            return await _handle_list_containers(arguments, mcp_service)

        elif name == "update_phase":
            return await _handle_update_phase(arguments, mcp_service)
        # ========== Cards Management (unified) ==========

        elif name == "add_card":
            return await _handle_add_card(arguments, mcp_service)

        elif name == "list_cards":
            return await _handle_list_cards(arguments, mcp_service)

        elif name == "update_card":
            return await _handle_update_card(arguments, mcp_service)

        elif name == "delete_card":
            return await _handle_delete_card(arguments, mcp_service)

        # ========== Reconnaissance Management ==========

        elif name == "add_recon_data":
            return await _handle_add_recon_data(arguments, mcp_service)

        elif name == "list_recon":
            return await _handle_list_recon(arguments, mcp_service)

        # ========== Command Execution ==========

        elif name == "execute":
            return await _handle_execute(arguments, mcp_service)

        elif name == "python_exec":
            return await _handle_python_exec(arguments, mcp_service)

        elif name == "http_request":
            return await _handle_http_request(arguments, mcp_service)

        # ========== Pentesting Tools ==========

        elif name == "scan":
            return await _handle_scan(arguments, mcp_service)

        elif name == "subdomain_enum":
            return await _handle_subdomain_enum(arguments, mcp_service)

        elif name == "ssl_analysis":
            return await _handle_ssl_analysis(arguments, mcp_service)

        elif name == "tech_detection":
            return await _handle_tech_detection(arguments, mcp_service)

        # ========== Credentials Management ==========

        elif name == "credentials_add":
            return await _handle_credentials_add(arguments, mcp_service)

        elif name == "credentials_list":
            return await _handle_credentials_list(arguments, mcp_service)

        else:
            return [TextContent(type="text", text=f"Unknown tool: `{name}`")]

    except Exception as e:
        import logging
        log = logging.getLogger("aida-mcp")
        log.error(f"Tool execution error: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ========== Assessment Management Handlers ==========

async def _handle_load_assessment(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle load_assessment - Load and display full assessment data"""
    assessment_name = arguments["name"]
    skip_data = arguments.get("skip_data", False)

    # Find assessment by name
    assessment = await mcp_service.get_assessment_by_name(assessment_name)

    if not assessment:
        return [TextContent(
            type="text",
            text=f"Assessment '{assessment_name}' not found. USER must create it via the interface first."
        )]

    # Set context
    mcp_service.current_assessment_id = assessment["id"]
    mcp_service.current_assessment_name = assessment["name"]

    # If skip_data, return minimal response
    if skip_data:
        return [TextContent(
            type="text",
            text=f"Assessment '{assessment_name}' loaded successfully."
        )]

    # Load full data
    full_data = await mcp_service.get_assessment_full_data(assessment["id"])
    assessment_data = full_data['assessment']

    # Format response
    response = f"**Assessment Loaded: {assessment_data['name']}**\n\n"
    response += "## State of Work\n"
    response += f"**Client:** {assessment_data.get('client_name', 'N/A')}\n"
    response += f"**Environment:** {assessment_data.get('environment', 'non_specifie')}\n"
    response += f"**Scope:** {assessment_data.get('scope', 'N/A')}\n"
    response += f"**Limitations:** {assessment_data.get('limitations', 'N/A')}\n\n"

    response += "## Basic Information\n"
    target_domains = assessment_data.get('target_domains') or []
    ip_scopes = assessment_data.get('ip_scopes') or []
    response += f"**Target Domains:** {', '.join(target_domains) if isinstance(target_domains, list) else str(target_domains) or 'N/A'}\n"
    response += f"**IP Scopes:** {', '.join(ip_scopes) if isinstance(ip_scopes, list) else str(ip_scopes) or 'N/A'}\n\n"

    response += f"**Workspace:** `{assessment_data.get('workspace_path', 'Not created')}`\n\n"
    
    # Generate workspace tree structure and list context documents
    if assessment_data.get('workspace_path') and assessment_data.get('container_name'):
        try:
            from utils.tree_generator import generate_workspace_tree, get_context_files_list
            import logging
            log = logging.getLogger("aida-mcp")
            
            # Generate tree structure
            tree_structure = await generate_workspace_tree(
                container_name=assessment_data.get('container_name'),
                workspace_path=assessment_data.get('workspace_path'),
                max_depth=2
            )
            
            response += "## Workspace Structure\n\n"
            response += "```\n"
            response += tree_structure
            response += "\n```\n\n"
            
            # List context documents if any
            context_files = await get_context_files_list(
                container_name=assessment_data.get('container_name'),
                workspace_path=assessment_data.get('workspace_path')
            )
            
            if context_files:
                response += "## 📄 Context Documents Provided by User\n\n"
                response += "The following documents are available in `/context` for additional context:\n\n"
                for file_info in context_files:
                    response += f"- `{file_info['filename']}` ({file_info['size_human']}) - {file_info['type']}\n"
                    response += f"  Path: `{file_info['path']}`\n"
                response += "\n**Note:** You can read these files using the `execute()` tool with commands like `cat` or `less`.\n\n"
        except Exception as e:
            # Continue without tree if error
            log.warning(f"Failed to generate workspace tree: {e}")
    


    # Add sections information
    sections = full_data.get('sections', [])
    if sections:
        response += "## Assessment Phases\n"
        for section in sections:
            phase_num = section.get('section_type', '').replace('phase_', '')
            if phase_num.isdigit():
                phase_names = {
                    '1': 'Reconnaissance',
                    '2': 'Mapping & Enumeration',
                    '3': 'Vulnerability Assessment',
                    '4': 'Exploitation',
                    '5': 'Post-Exploitation & Reporting'
                }
                phase_name = phase_names.get(phase_num, f'Phase {phase_num}')
                content = section.get('content', '')
                if content:
                    response += f"**Phase {phase_num} - {phase_name}:**\n{content}\n\n"
                else:
                    response += f"**Phase {phase_num} - {phase_name}:** No content yet\n"

    # Add all cards with full details
    cards = full_data.get('cards', [])
    if cards:
        # Filter out false positives (hidden from AI)
        cards = [c for c in cards if c.get('status') != 'false_positive']
        
        # Separate by type
        findings = [c for c in cards if c.get('card_type') == 'finding']
        observations = [c for c in cards if c.get('card_type') == 'observation']
        infos = [c for c in cards if c.get('card_type') == 'info']

        # Display FINDINGS with full details
        if findings:
            response += f"\n## Findings ({len(findings)} total)\n"
            # Group by severity
            for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']:
                severity_findings = [f for f in findings if f.get('severity') == severity]
                if severity_findings:
                    response += f"\n### {severity} ({len(severity_findings)})\n"
                    for finding in severity_findings:
                        response += f"\n**[ID: {finding['id']}] {finding.get('title', 'Untitled')}**\n"
                        if finding.get('target_service'):
                            response += f"- **Target:** {finding['target_service']}\n"
                        if finding.get('status'):
                            response += f"- **Status:** {finding['status']}\n"
                        if finding.get('cvss_score') is not None:
                            response += f"- **CVSS Score:** {finding['cvss_score']}\n"
                        if finding.get('cvss_vector'):
                            response += f"- **CVSS Vector:** `{finding['cvss_vector']}`\n"
                        if finding.get('section_number'):
                            response += f"- **Section:** {finding['section_number']}\n"
                        if finding.get('technical_analysis'):
                            response += f"- **Technical Analysis:**\n{finding['technical_analysis']}\n"
                        if finding.get('proof'):
                            response += f"- **Proof:**\n{finding['proof']}\n"
                        if finding.get('notes'):
                            response += f"- **Notes:** {finding['notes']}\n"
                        if finding.get('context'):
                            response += f"- **Context:** {finding['context']}\n"
                        response += f"- **Created:** {finding.get('created_at', 'N/A')}\n"

        # Display OBSERVATIONS with full details
        if observations:
            response += f"\n## Observations ({len(observations)} total)\n"
            for obs in observations:
                response += f"\n**[ID: {obs['id']}] {obs.get('title', 'Untitled')}**\n"
                if obs.get('target_service'):
                    response += f"- **Target:** {obs['target_service']}\n"
                if obs.get('section_number'):
                    response += f"- **Section:** {obs['section_number']}\n"
                if obs.get('notes'):
                    response += f"- **Notes:**\n{obs['notes']}\n"
                if obs.get('context'):
                    response += f"- **Context:** {obs['context']}\n"
                if obs.get('technical_analysis'):
                    response += f"- **Analysis:** {obs['technical_analysis']}\n"
                response += f"- **Created:** {obs.get('created_at', 'N/A')}\n"

        # Display INFO CARDS with full details
        if infos:
            response += f"\n## Info Cards ({len(infos)} total)\n"
            for info in infos:
                response += f"\n**[ID: {info['id']}] {info.get('title', 'Untitled')}**\n"
                if info.get('target_service'):
                    response += f"- **Target:** {info['target_service']}\n"
                if info.get('section_number'):
                    response += f"- **Section:** {info['section_number']}\n"
                if info.get('context'):
                    response += f"- **Context:**\n{info['context']}\n"
                if info.get('notes'):
                    response += f"- **Notes:** {info['notes']}\n"
                if info.get('technical_analysis'):
                    response += f"- **Analysis:** {info['technical_analysis']}\n"
                response += f"- **Created:** {info.get('created_at', 'N/A')}\n"

    # Add reconnaissance data
    recon_data = full_data.get('recon_data', [])
    if recon_data:
        response += "\n## Reconnaissance Data\n"

        # Group all items by data_type (no truncation)
        recon_by_type = {}
        for r in recon_data:
            dtype = r.get('data_type', 'other')
            recon_by_type.setdefault(dtype, []).append(r)

        # Display order: known types first, then anything else
        ordered_types = ['endpoint', 'subdomain', 'service', 'technology', 'port', 'database', 'credential', 'vulnerability']
        displayed = set()

        for dtype in ordered_types:
            items = recon_by_type.get(dtype)
            if not items:
                continue
            displayed.add(dtype)
            label = dtype.capitalize() + 's'
            names = [str(i.get('name', '') or '') for i in items]
            response += f"**{label} ({len(names)}):** {', '.join(names)}\n"

        # Any extra/custom types not in the predefined list
        for dtype, items in recon_by_type.items():
            if dtype in displayed:
                continue
            label = dtype.replace('_', ' ').capitalize() + 's'
            names = [str(i.get('name', '') or '') for i in items]
            response += f"**{label} ({len(names)}):** {', '.join(names)}\n"

    # Add recent command history
    try:
        # Get command_history_limit from settings (default: 10)
        limit = await mcp_service.get_command_history_limit()

        # Skip if limit is 0 (disabled)
        if limit <= 0:
            raise Exception("Command history disabled (limit=0)")

        # Fetch commands for this assessment
        commands_response = await mcp_service.http_client.get(
            f"{mcp_service.backend_url}/assessments/{assessment['id']}/commands",
            params={"limit": limit}
        )
        commands_response.raise_for_status()
        commands = commands_response.json()

        if commands:
            response += f"\n## Recent Commands ({len(commands)} most recent)\n"
            for cmd in commands:
                response += f"\n`{cmd.get('command', 'N/A')}`\n"
                # Show stdout if available
                if cmd.get('stdout'):
                    response += f"{cmd['stdout']}\n"
                # Show stderr if available
                if cmd.get('stderr'):
                    response += f"Error: {cmd['stderr']}\n"
    except Exception as e:
        # Continue without commands
        pass

    # Add credentials (placeholders + metadata, no raw secrets)
    try:
        creds_response = await mcp_service.http_client.get(
            f"{mcp_service.backend_url}/assessments/{assessment['id']}/credentials"
        )
        creds_response.raise_for_status()
        creds_data = creds_response.json()
        credentials = creds_data.get("credentials", [])

        if credentials:
            response += f"\n## Credentials ({len(credentials)} available)\n"
            response += "Use `{{PLACEHOLDER}}` syntax in commands/HTTP requests for automatic substitution.\n\n"
            for cred in credentials:
                placeholder = cred.get("placeholder", "")
                ctype = cred.get("credential_type", "")
                name = cred.get("name", "")
                service = cred.get("service", "")
                target = cred.get("target", "")
                notes = cred.get("notes", "")
                response += f"- **{name}** ({ctype}) → `{{{{{placeholder}}}}}`"
                if service:
                    response += f" | Service: {service}"
                if target:
                    response += f" | Target: {target}"
                if notes:
                    response += f" | Notes: {notes}"
                response += "\n"
                # Show actual credential value
                if ctype == "bearer_token" or ctype == "api_key":
                    if cred.get("token"):
                        response += f"  Value: `{cred['token']}`\n"
                elif ctype == "basic_auth" or ctype == "ssh":
                    if cred.get("username"):
                        response += f"  Username: `{cred['username']}`\n"
                    if cred.get("password"):
                        response += f"  Password: `{cred['password']}`\n"
                elif ctype == "cookie":
                    if cred.get("cookie_value"):
                        response += f"  Cookie: `{cred['cookie_value']}`\n"
                elif ctype == "custom":
                    if cred.get("custom_data"):
                        response += f"  Data: {cred['custom_data']}\n"
        else:
            response += "\n## Credentials\nNo credentials configured yet. Use `credentials_add` to add tokens, cookies, etc.\n"
    except Exception:
        pass

    response += "\nReady to begin assessment work!"

    return [TextContent(type="text", text=response)]


async def _handle_create_assessment(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle create_assessment - Create a new assessment and auto-load it"""
    name = arguments.get("name", "").strip()
    if not name:
        return [TextContent(type="text", text="Error: Assessment name is required.")]

    # Build the creation payload
    payload = {"name": name}

    optional_fields = [
        "client_name", "scope", "limitations", "objectives",
        "target_domains", "ip_scopes", "credentials", "access_info",
        "category", "environment", "environment_notes",
        "start_date", "end_date"
    ]
    for field in optional_fields:
        value = arguments.get(field)
        if value is not None:
            payload[field] = value

    try:
        response = await mcp_service.http_client.post(
            f"{mcp_service.backend_url}/assessments",
            json=payload
        )

        if response.status_code == 400:
            error_detail = response.json().get("detail", "Bad request")
            return [TextContent(type="text", text=f"Error: {error_detail}")]

        response.raise_for_status()
        assessment = response.json()

        # Auto-load: set current assessment context
        mcp_service.current_assessment_id = assessment["id"]
        mcp_service.current_assessment_name = assessment["name"]

        # Format success response
        result = f"**Assessment Created and Loaded: {assessment['name']}**\n\n"
        result += f"- **ID:** {assessment['id']}\n"
        result += f"- **Status:** {assessment.get('status', 'active')}\n"
        if assessment.get("category"):
            result += f"- **Category:** {assessment['category']}\n"
        result += f"- **Environment:** {assessment.get('environment', 'non_specifie')}\n"
        if assessment.get("container_name"):
            result += f"- **Container:** {assessment['container_name']}\n"
        if assessment.get("workspace_path"):
            result += f"- **Workspace:** `{assessment['workspace_path']}`\n"
        if assessment.get("scope"):
            result += f"- **Scope:** {assessment['scope']}\n"
        if assessment.get("target_domains"):
            domains = assessment['target_domains']
            result += f"- **Target Domains:** {', '.join(domains) if isinstance(domains, list) else str(domains)}\n"
        if assessment.get("ip_scopes"):
            scopes = assessment['ip_scopes']
            result += f"- **IP Scopes:** {', '.join(scopes) if isinstance(scopes, list) else str(scopes)}\n"
        if assessment.get("limitations"):
            result += f"- **Limitations:** {assessment['limitations']}\n"
        if assessment.get("objectives"):
            result += f"- **Objectives:** {assessment['objectives']}\n"
        if assessment.get("client_name"):
            result += f"- **Client:** {assessment['client_name']}\n"

        result += "\nAssessment is now active. You can start the pentesting workflow."
        return [TextContent(type="text", text=result)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error creating assessment: {str(e)}")]


async def _handle_list_assessments(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle list_assessments - List existing assessments"""
    try:
        params = {}
        status_filter = arguments.get("status")
        if status_filter:
            params["status"] = status_filter
        limit = arguments.get("limit", 50)
        params["limit"] = limit

        response = await mcp_service.http_client.get(
            f"{mcp_service.backend_url}/assessments",
            params=params
        )
        response.raise_for_status()
        assessments = response.json()

        if not assessments:
            filter_msg = f" with status '{status_filter}'" if status_filter else ""
            return [TextContent(type="text", text=f"No assessments found{filter_msg}.")]

        result = f"**Assessments ({len(assessments)})**\n\n"
        for a in assessments:
            status_icon = {"active": "●", "completed": "✓", "archived": "○"}.get(a.get("status", ""), "?")
            result += f"- {status_icon} **{a['name']}**"
            if a.get("category"):
                result += f" [{a['category']}]"
            result += f" — {a.get('status', 'unknown')}"
            if a.get("client_name"):
                result += f" | Client: {a['client_name']}"
            result += "\n"

        return [TextContent(type="text", text=result)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error listing assessments: {str(e)}")]


async def _handle_list_containers(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle list_containers - List available pentesting containers"""
    try:
        response = await mcp_service.http_client.get(
            f"{mcp_service.backend_url}/containers"
        )
        response.raise_for_status()
        data = response.json()

        # Handle both list and dict responses
        containers = data if isinstance(data, list) else data.get("containers", [])
        current = data.get("current", "") if isinstance(data, dict) else ""

        if not containers:
            return [TextContent(type="text", text="No pentesting containers found. Make sure a container is running (aida-pentest or Exegol).")]

        result = f"**Available Containers ({len(containers)})**\n\n"
        for c in containers:
            name = c.get("name", "unknown")
            status_str = c.get("status", "unknown")
            is_running = "running" in status_str.lower()
            is_current = name == current
            status_icon = "🟢" if is_running else "⚫"
            result += f"- {status_icon} **{name}**"
            if is_current:
                result += " *(active)*"
            result += f" — {status_str}"
            if c.get("image"):
                result += f" | Image: {c['image']}"
            result += "\n"

        return [TextContent(type="text", text=result)]

    except Exception as e:
        return [TextContent(type="text", text=f"Error listing containers: {str(e)}")]


async def _handle_update_phase(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle update_phase - Update phase content"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    phase_num = arguments["phase_number"]
    section_type = f"phase_{int(phase_num)}"

    await mcp_service.update_section(
        assessment_id=mcp_service.current_assessment_id,
        section_type=section_type,
        section_number=phase_num,
        title=arguments.get("title"),
        content=arguments["content"]
    )

    return [TextContent(
        type="text",
        text=f"Phase {phase_num} updated"
    )]


# ========== Cards Management Handlers (unified) ==========

async def _handle_add_card(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle add_card - Unified handler for finding/observation/info with ID return"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    card_type = arguments["card_type"]
    title = arguments["title"]

    # Build card data - include all provided fields
    card_data = {
        "card_type": card_type,
        "title": title,
    }

    # Add all optional fields if provided (don't filter by type - backend accepts all)
    optional_fields = [
        "target_service", "severity", "status",
        "technical_analysis", "proof", "notes", "context"
    ]
    for field in optional_fields:
        if field in arguments and arguments[field] is not None:
            card_data[field] = arguments[field]

    # Handle CVSS 4.0 vector: calculate score and derive severity automatically
    cvss_vector = arguments.get("cvss_vector")
    if cvss_vector:
        score, derived_severity = _calculate_cvss4_score(cvss_vector)
        card_data["cvss_vector"] = cvss_vector
        if score is not None:
            card_data["cvss_score"] = score
            card_data["severity"] = derived_severity  # Override manual severity
        else:
            # Library not available or invalid vector — store vector, keep manual severity if provided
            import logging
            logging.getLogger("aida-mcp").warning(f"Could not calculate CVSS score for vector: {cvss_vector}")

    # Validate that findings have either cvss_vector or severity
    if card_type == "finding" and "severity" not in card_data:
        return [TextContent(type="text", text="findings require either cvss_vector or severity")]

    # Set default status for findings
    if card_type == "finding" and "status" not in card_data:
        card_data["status"] = "confirmed"

    # Create card via backend API
    result = await mcp_service.add_card(
        assessment_id=mcp_service.current_assessment_id,
        **card_data
    )

    card_id = result.get("id", "unknown")

    # Format response based on type
    if card_type == "finding":
        cvss_info = ""
        if card_data.get("cvss_score") is not None:
            cvss_info = f" — CVSS {card_data['cvss_score']}"
        severity_label = card_data.get("severity", "N/A")
        return [TextContent(
            type="text",
            text=f"Finding added: {title} ({severity_label}{cvss_info}) [ID: {card_id}]"
        )]
    elif card_type == "observation":
        return [TextContent(
            type="text",
            text=f"Observation added: {title} [ID: {card_id}]"
        )]
    else:  # info
        return [TextContent(
            type="text",
            text=f"Info added: {title} [ID: {card_id}]"
        )]



async def _handle_list_cards(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle list_cards - List all cards with optional filters"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    # Get full data
    full_data = await mcp_service.get_assessment_full_data(mcp_service.current_assessment_id)
    cards = full_data.get('cards', [])

    # Filter out false positives (hidden from AI)
    cards = [c for c in cards if c.get('status') != 'false_positive']

    # Apply card_type filter if provided
    card_type_filter = arguments.get("card_type")
    if card_type_filter:
        cards = [c for c in cards if c.get('card_type') == card_type_filter]

    # Apply severity filter if provided (for findings)
    severity_filter = arguments.get("severity")
    if severity_filter:
        cards = [c for c in cards if c.get('severity') == severity_filter]

    # Apply limit
    limit = arguments.get("limit", 50)
    cards = cards[:limit]

    if not cards:
        filter_msg = f" (type: {card_type_filter})" if card_type_filter else ""
        return [TextContent(type="text", text=f"No cards found{filter_msg}.")]

    response = f"**Cards ({len(cards)}):**\n\n"

    for card in cards:
        card_id = card.get('id', 'N/A')
        card_type = card.get('card_type', 'unknown')
        title = card.get('title', 'Untitled')
        target = card.get('target_service', 'N/A')

        # Type badge
        type_badge = f"[{card_type.upper()}]"
        if card_type == "finding":
            severity = card.get('severity', 'UNKNOWN')
            status = card.get('status', 'N/A')
            response += f"**ID: {card_id}** | {type_badge} [{severity}] {title}\n"
            response += f"  - Target: {target}\n"
            response += f"  - Status: {status}\n"
        else:
            response += f"**ID: {card_id}** | {type_badge} {title}\n"
            response += f"  - Target: {target}\n"

        # Show preview of content
        analysis = card.get('technical_analysis') or card.get('notes') or card.get('context')
        if analysis:
            preview = analysis[:100] + "..." if len(analysis) > 100 else analysis
            response += f"  - Content: {preview}\n"

        response += "\n"

    return [TextContent(type="text", text=response)]


async def _handle_update_card(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle update_card - Update any card by ID"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    card_id = arguments["card_id"]

    # Build update payload (only include provided fields)
    update_data = {}
    for field in ["title", "target_service", "severity", "status",
                  "technical_analysis", "proof", "notes", "context"]:
        if field in arguments:
            update_data[field] = arguments[field]

    # Handle CVSS 4.0 vector update: recalculate score and severity
    cvss_vector = arguments.get("cvss_vector")
    if cvss_vector:
        score, derived_severity = _calculate_cvss4_score(cvss_vector)
        update_data["cvss_vector"] = cvss_vector
        if score is not None:
            update_data["cvss_score"] = score
            update_data["severity"] = derived_severity
        else:
            import logging
            logging.getLogger("aida-mcp").warning(f"Could not calculate CVSS score for vector: {cvss_vector}")

    if not update_data:
        return [TextContent(type="text", text="No fields to update provided.")]

    # Call backend API to update
    response = await mcp_service.http_client.patch(
        f"{mcp_service.backend_url}/assessments/{mcp_service.current_assessment_id}/cards/{card_id}",
        json=update_data
    )
    response.raise_for_status()

    return [TextContent(
        type="text",
        text=f"Card {card_id} updated successfully"
    )]


async def _handle_delete_card(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle delete_card - Delete any card by ID"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    card_id = arguments["card_id"]

    # Call backend API to delete
    response = await mcp_service.http_client.delete(
        f"{mcp_service.backend_url}/assessments/{mcp_service.current_assessment_id}/cards/{card_id}"
    )
    response.raise_for_status()

    return [TextContent(
        type="text",
        text=f"Card {card_id} deleted successfully"
    )]


# ========== Reconnaissance Management Handlers ==========

async def _handle_add_recon_data(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle add_recon_data - SINGLE OU BATCH"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    # Mode batch
    if "entries" in arguments:
        entries = arguments["entries"]
        if not entries:
            return [TextContent(type="text", text="No entries provided.")]

        # API will validate and normalize data_types via Pydantic
        # Batch call to backend
        try:
            response = await mcp_service.http_client.post(
                f"{mcp_service.backend_url}/assessments/{mcp_service.current_assessment_id}/recon/batch",
                json={"entries": entries}
            )
            response.raise_for_status()
            result = response.json()
            
            # Format summary
            summary_parts = []
            for data_type, count in result.get("summary", {}).items():
                summary_parts.append(f"{count} {data_type}(s)")
            
            summary_text = ", ".join(summary_parts) if summary_parts else "unknown types"
            
            return [TextContent(
                type="text",
                text=f"Added {result.get('created_count', len(entries))} recon entries: {summary_text}"
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Error adding batch recon data: {str(e)}"
            )]
    
    # Mode single - capture ID from response
    else:
        result = await mcp_service.add_recon_data(
            assessment_id=mcp_service.current_assessment_id,
            data_type=arguments["data_type"],
            name=arguments["name"],
            details=arguments.get("details"),
            discovered_in_phase=arguments.get("discovered_in_phase")
        )

        recon_id = result.get("id", "unknown")

        return [TextContent(
            type="text",
            text=f"Recon data added: {arguments['data_type']} -> {arguments['name']} [ID: {recon_id}]"
        )]


async def _handle_list_recon(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle list_recon"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    full_data = await mcp_service.get_assessment_full_data(mcp_service.current_assessment_id)
    recon_data = full_data.get('recon_data', [])

    # Apply data_type filter if provided
    data_type_filter = arguments.get("data_type")
    if data_type_filter:
        recon_data = [r for r in recon_data if r.get('data_type') == data_type_filter]

    limit = arguments.get("limit", 50)
    recon_data = recon_data[:limit]

    if not recon_data:
        return [TextContent(type="text", text="No recon data found.")]

    response = f"**Reconnaissance Data ({len(recon_data)}):**\n\n"
    for recon in recon_data:
        recon_id = recon.get('id', 'N/A')
        data_type = recon.get('data_type', 'UNKNOWN')
        name = recon.get('name', 'Unnamed')
        phase = recon.get('discovered_in_phase', 'N/A')

        response += f"**ID: {recon_id}** | [{data_type}] {name}\n"
        response += f"  - Discovered in: {phase}\n"

        details = recon.get('details')
        if details:
            response += f"  - Details: {details}\n"

        response += "\n"

    return [TextContent(type="text", text=response)]

# ========== Command Execution Handler ==========

async def _handle_execute(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle execute with command approval modes, timeout, credential substitution, and intelligent parsing"""
    command = arguments["command"]
    phase = arguments.get("phase")

    # Check if assessment loaded
    if not mcp_service.current_assessment_id:
        return [TextContent(
            type="text",
            text="No assessment loaded. Use 'load_assessment' first."
        )]

    # ========== STEP 1: CHECK COMMAND EXECUTION MODE ==========
    try:
        mode_response = await mcp_service.http_client.get(
            f"{mcp_service.backend_url}/command-settings"
        )
        mode_response.raise_for_status()
        settings = mode_response.json()

        execution_mode = settings.get("execution_mode", "open")
        filter_keywords = settings.get("filter_keywords", [])
    except Exception as e:
        # Default to open mode if settings unavailable
        execution_mode = "open"
        filter_keywords = []

    # ========== STEP 2: DETERMINE IF APPROVAL REQUIRED ==========
    requires_approval = False
    matched_keywords = []

    if execution_mode == "closed":
        # All commands require approval
        requires_approval = True
    elif execution_mode == "filter":
        # Check if command contains any filter keywords
        command_lower = command.lower()
        matched_keywords = [kw for kw in filter_keywords if kw.lower() in command_lower]
        if matched_keywords:
            requires_approval = True

    # ========== STEP 3: APPROVAL FLOW WITH BLOCKING WAIT ==========
    if requires_approval:
        import asyncio
        
        # Get timeout from settings (default 5 minutes)
        timeout_seconds = 300
        try:
            timeout_response = await mcp_service.http_client.get(
                f"{mcp_service.backend_url}/command-settings"
            )
            if timeout_response.status_code == 200:
                timeout_seconds = timeout_response.json().get("timeout_seconds", 300)
        except:
            pass
        
        poll_interval = 2  # Poll every 2 seconds
        pending_id = None
        
        # Create pending command
        try:
            pending_response = await mcp_service.http_client.post(
                f"{mcp_service.backend_url}/pending-commands/create",
                json={
                    "assessment_id": mcp_service.current_assessment_id,
                    "command": command,
                    "phase": phase,
                    "matched_keywords": matched_keywords
                }
            )
            pending_response.raise_for_status()
            pending_cmd = pending_response.json()
            pending_id = pending_cmd.get("id")
            
        except Exception as e:
            # If we can't create pending command, reject by default for safety
            return [TextContent(
                type="text",
                text=f"**❌ Command blocked - failed to create approval request**\n\n"
                     f"**Command:** `{command}`\n"
                     f"**Error:** {str(e)}\n\n"
                     f"The command was NOT executed for safety reasons."
            )]
        
        if not pending_id:
            return [TextContent(
                type="text",
                text=f"**❌ Command blocked - invalid approval request**\n\n"
                     f"**Command:** `{command}`\n\n"
                     f"The command was NOT executed for safety reasons."
            )]
        
        # Waiting for approval
        mode_label = "Closed mode" if execution_mode == "closed" else f"Filter (keywords: {', '.join(matched_keywords)})"
        
        # ========== POLL AND WAIT FOR APPROVAL ==========
        elapsed = 0
        final_status = "timeout"
        execution_result = None
        
        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            try:
                # Check status of pending command
                status_response = await mcp_service.http_client.get(
                    f"{mcp_service.backend_url}/pending-commands/{pending_id}"
                )
                
                if status_response.status_code == 200:
                    pending_data = status_response.json()
                    current_status = pending_data.get("status", "pending")
                    
                    if current_status == "executed":
                        # User approved and command was executed
                        final_status = "approved"
                        execution_result = pending_data.get("execution_result", {})
                        break
                    
                    elif current_status == "rejected":
                        # User rejected
                        final_status = "rejected"
                        break
                    
                    elif current_status == "timeout":
                        # Already timed out by backend
                        final_status = "timeout"
                        break
                    
                    # Still pending - continue polling
                    
            except Exception as e:
                # Continue polling on error
                pass
        
        # ========== RETURN RESULT BASED ON FINAL STATUS ==========
        if final_status == "approved" and execution_result:
            # Command was approved and executed - return output like normal execution
            stdout = execution_result.get("stdout", "")
            stderr = execution_result.get("stderr", "")
            success = execution_result.get("success", False)
            
            max_length = await mcp_service.get_output_max_length()
            
            if success:
                if stdout:
                    response_text = f"```\n{stdout[:max_length]}\n```\n"
                else:
                    response_text = "*(Command completed with no output)*\n"
            else:
                response_text = f"Command failed (exit code {execution_result.get('returncode', 'unknown')})\n"
                if stderr:
                    response_text += f"```\n{stderr[:500]}\n```\n"
            
            return [TextContent(type="text", text=response_text)]
        
        elif final_status == "rejected":
            return [TextContent(
                type="text",
                text="Command rejected by user"
            )]
        
        else:  # timeout
            return [TextContent(
                type="text",
                text=f"Command approval timed out after {timeout_seconds}s. The command was NOT executed."
            )]

    # ========== STEP 4: EXECUTE IMMEDIATELY (OPEN MODE OR NO KEYWORD MATCH) ==========
    try:
        response = await mcp_service.http_client.post(
            f"{mcp_service.backend_url}/assessments/{mcp_service.current_assessment_id}/commands/execute-with-credentials",
            json={"command": command, "phase": phase}
        )
        response.raise_for_status()
        result = response.json()

    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg and "Placeholder" in error_msg:
            return [TextContent(
                type="text",
                text=f"ERROR: {error_msg}\n\nUse `credentials_list` to see available placeholders, or `credentials_add` to add it."
            )]
        else:
            return [TextContent(
                type="text",
                text=f"ERROR executing command: {error_msg}"
            )]

    # Format response (do NOT echo command back to Claude - it causes confusion)
    response_text = ""

    # Check if timeout occurred
    if result.get("status") == "timeout":
        timeout_seconds = result.get("execution_time", 300)
        response_text += f"**Timeout ({timeout_seconds}s exceeded)**\n\n"
        response_text += f"**Command:**\n```bash\n{command}\n```\n\n"
        response_text += "Please run this command manually and paste the results here.\n"
        response_text += "I'm pausing until you provide the output.\n"

        return [TextContent(type="text", text=response_text)]

    # Get output_max_length setting
    max_length = await mcp_service.get_output_max_length()

    # Success - parse output intelligently
    if result.get("success"):
        parsed_output = parse_scan_output(command, result, max_length)
        response_text += parsed_output
    else:
        # Error - show both stdout and stderr
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""

        if stdout:
            response_text += f"**Command output (exit code {result.get('returncode', 'unknown')}):**\n\n"
            response_text += f"```\n{stdout[:max_length]}\n```\n"
            if stderr:
                response_text += f"\n**Stderr:**\n{stderr[:500]}\n"
        elif stderr:
            response_text += f"ERROR: {stderr[:500]}\n"
        else:
            response_text += f"ERROR: Command failed with exit code {result.get('returncode', 'unknown')}\n"
            response_text += f"DEBUG: success={result.get('success')}, stdout={repr(result.get('stdout'))}, stderr={repr(result.get('stderr'))}, status={result.get('status')}\n"

    return [TextContent(type="text", text=response_text)]


# ========== Python Exec Handler ==========

async def _handle_python_exec(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle python_exec — execute Python via stdin, same approval flow as execute."""
    code = arguments.get("code", "")
    phase = arguments.get("phase")

    if not mcp_service.current_assessment_id:
        return [TextContent(
            type="text",
            text="No assessment loaded. Use 'load_assessment' first."
        )]

    if not code.strip():
        return [TextContent(type="text", text="No code provided.")]

    # ========== CHECK COMMAND EXECUTION MODE ==========
    try:
        mode_response = await mcp_service.http_client.get(
            f"{mcp_service.backend_url}/command-settings"
        )
        mode_response.raise_for_status()
        cmd_settings = mode_response.json()
        execution_mode = cmd_settings.get("execution_mode", "open")
        filter_keywords = cmd_settings.get("filter_keywords", [])
    except Exception:
        execution_mode = "open"
        filter_keywords = []

    # ========== DETERMINE IF APPROVAL REQUIRED ==========
    requires_approval = False
    matched_keywords = []

    if execution_mode == "closed":
        requires_approval = True
    elif execution_mode == "filter":
        # Keyword check runs on the Python code content
        code_lower = code.lower()
        matched_keywords = [kw for kw in filter_keywords if kw.lower() in code_lower]
        if matched_keywords:
            requires_approval = True

    # ========== APPROVAL FLOW ==========
    if requires_approval:
        import asyncio

        timeout_seconds = 300
        try:
            timeout_response = await mcp_service.http_client.get(
                f"{mcp_service.backend_url}/command-settings"
            )
            if timeout_response.status_code == 200:
                timeout_seconds = timeout_response.json().get("timeout_seconds", 300)
        except Exception:
            pass

        poll_interval = 2
        pending_id = None

        try:
            pending_response = await mcp_service.http_client.post(
                f"{mcp_service.backend_url}/pending-commands/create",
                json={
                    "assessment_id": mcp_service.current_assessment_id,
                    "command": code,           # Store full Python code as command
                    "command_type": "python",  # Mark as python for approve routing
                    "phase": phase,
                    "matched_keywords": matched_keywords
                }
            )
            pending_response.raise_for_status()
            pending_cmd = pending_response.json()
            pending_id = pending_cmd.get("id")
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"**❌ python_exec blocked — failed to create approval request**\n\n**Error:** {str(e)}\n\nCode was NOT executed."
            )]

        if not pending_id:
            return [TextContent(
                type="text",
                text="**❌ python_exec blocked — invalid approval request**\n\nCode was NOT executed."
            )]

        # Poll for approval
        elapsed = 0
        final_status = "timeout"
        execution_result = None

        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            try:
                status_response = await mcp_service.http_client.get(
                    f"{mcp_service.backend_url}/pending-commands/{pending_id}"
                )
                if status_response.status_code == 200:
                    pending_data = status_response.json()
                    current_status = pending_data.get("status", "pending")
                    if current_status == "executed":
                        final_status = "approved"
                        execution_result = pending_data.get("execution_result", {})
                        break
                    elif current_status in ("rejected", "timeout"):
                        final_status = current_status
                        break
            except Exception:
                pass

        if final_status == "approved" and execution_result:
            max_length = await mcp_service.get_python_exec_output_max_length()
            stdout = execution_result.get("stdout", "")
            stderr = execution_result.get("stderr", "")
            success = execution_result.get("success", False)
            if success:
                return [TextContent(type="text", text=f"```\n{stdout[:max_length]}\n```\n" if stdout else "*(No output)*\n")]
            else:
                response_text = f"Python failed (exit code {execution_result.get('returncode', 'unknown')})\n"
                if stderr:
                    response_text += f"```\n{stderr[:500]}\n```\n"
                return [TextContent(type="text", text=response_text)]
        elif final_status == "rejected":
            return [TextContent(type="text", text="python_exec rejected by user.")]
        else:
            return [TextContent(type="text", text=f"python_exec approval timed out after {timeout_seconds}s. Code was NOT executed.")]

    # ========== EXECUTE IMMEDIATELY (OPEN MODE) ==========
    try:
        response = await mcp_service.http_client.post(
            f"{mcp_service.backend_url}/assessments/{mcp_service.current_assessment_id}/commands/python-exec",
            json={"code": code, "phase": phase}
        )
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg and "Placeholder" in error_msg:
            return [TextContent(
                type="text",
                text=f"ERROR: {error_msg}\n\nUse `credentials_list` to see available placeholders, or `credentials_add` to add it."
            )]
        return [TextContent(type="text", text=f"ERROR executing Python: {error_msg}")]

    if result.get("status") == "timeout":
        timeout_val = result.get("execution_time", 300)
        return [TextContent(
            type="text",
            text=f"**Timeout ({timeout_val}s exceeded)**\n\nPlease run the Python code manually and paste the results here.\nI'm pausing until you provide the output.\n"
        )]

    max_length = await mcp_service.get_python_exec_output_max_length()

    if result.get("success"):
        stdout = result.get("stdout") or ""
        response_text = f"```\n{stdout[:max_length]}\n```\n" if stdout else "*(Python completed with no output)*\n"
    else:
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        if stdout:
            response_text = f"**Python output (exit code {result.get('returncode', 'unknown')}):**\n\n```\n{stdout[:max_length]}\n```\n"
            if stderr:
                response_text += f"\n**Stderr:**\n```\n{stderr[:500]}\n```\n"
        elif stderr:
            response_text = f"**Python error:**\n```\n{stderr[:500]}\n```\n"
        else:
            response_text = f"ERROR: Python failed with exit code {result.get('returncode', 'unknown')}\n"

    return [TextContent(type="text", text=response_text)]


# ========== HTTP Request Handler ==========

async def _handle_http_request(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle http_request — structured HTTP requests from Exegol without curl escaping."""
    import json as _json

    url = arguments.get("url", "")
    method = arguments.get("method", "GET").upper()
    phase = arguments.get("phase")

    if not mcp_service.current_assessment_id:
        return [TextContent(
            type="text",
            text="No assessment loaded. Use 'load_assessment' first."
        )]

    if not url.strip():
        return [TextContent(type="text", text="No URL provided.")]

    # Build the payload for the backend (note: MCP schema uses 'json', Pydantic uses 'json_body')
    http_payload = {
        "url": url,
        "method": method,
        "phase": phase,
    }
    # Optional fields — only include if provided
    for field in ("headers", "params", "data", "cookies", "auth", "proxy"):
        if arguments.get(field) is not None:
            http_payload[field] = arguments[field]
    if arguments.get("json") is not None:
        http_payload["json_body"] = arguments["json"]
    if arguments.get("timeout") is not None:
        http_payload["timeout"] = arguments["timeout"]
    if arguments.get("follow_redirects") is not None:
        http_payload["follow_redirects"] = arguments["follow_redirects"]
    if arguments.get("verify_ssl") is not None:
        http_payload["verify_ssl"] = arguments["verify_ssl"]

    # ========== CHECK COMMAND EXECUTION MODE ==========
    try:
        mode_response = await mcp_service.http_client.get(
            f"{mcp_service.backend_url}/command-settings"
        )
        mode_response.raise_for_status()
        cmd_settings = mode_response.json()
        execution_mode = cmd_settings.get("execution_mode", "open")
        filter_keywords = cmd_settings.get("filter_keywords", [])
        http_method_rules = cmd_settings.get("http_method_rules", {})
    except Exception:
        execution_mode = "open"
        filter_keywords = []
        http_method_rules = {}

    # ========== DETERMINE IF APPROVAL REQUIRED ==========
    requires_approval = False
    matched_keywords = []
    target_lower = f"{method} {url}".lower()

    # HTTP method rule takes priority over global mode
    method_action = http_method_rules.get(method, "inherit")
    if method_action == "auto_approve":
        requires_approval = False
    elif method_action == "require_approval":
        requires_approval = True
        matched_keywords = [f"HTTP {method}"]
    else:
        # "inherit" — use global execution mode logic
        if execution_mode == "closed":
            requires_approval = True
        elif execution_mode == "filter":
            # Keyword check on the URL and method
            matched_keywords = [kw for kw in filter_keywords if kw.lower() in target_lower]
            if matched_keywords:
                requires_approval = True

    # ========== APPROVAL FLOW ==========
    if requires_approval:
        import asyncio

        timeout_seconds = 300
        try:
            timeout_response = await mcp_service.http_client.get(
                f"{mcp_service.backend_url}/command-settings"
            )
            if timeout_response.status_code == 200:
                timeout_seconds = timeout_response.json().get("timeout_seconds", 300)
        except Exception:
            pass

        poll_interval = 2
        pending_id = None

        try:
            pending_response = await mcp_service.http_client.post(
                f"{mcp_service.backend_url}/pending-commands/create",
                json={
                    "assessment_id": mcp_service.current_assessment_id,
                    "command": _json.dumps(http_payload),  # JSON-serialized params
                    "command_type": "http",
                    "phase": phase,
                    "matched_keywords": matched_keywords
                }
            )
            pending_response.raise_for_status()
            pending_cmd = pending_response.json()
            pending_id = pending_cmd.get("id")
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"**❌ http_request blocked — failed to create approval request**\n\n**Error:** {str(e)}\n\nRequest was NOT sent."
            )]

        if not pending_id:
            return [TextContent(
                type="text",
                text="**❌ http_request blocked — invalid approval request**\n\nRequest was NOT sent."
            )]

        # Poll for approval
        elapsed = 0
        final_status = "timeout"
        execution_result = None

        while elapsed < timeout_seconds:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            try:
                status_response = await mcp_service.http_client.get(
                    f"{mcp_service.backend_url}/pending-commands/{pending_id}"
                )
                if status_response.status_code == 200:
                    pending_data = status_response.json()
                    current_status = pending_data.get("status", "pending")
                    if current_status == "executed":
                        final_status = "approved"
                        execution_result = pending_data.get("execution_result", {})
                        break
                    elif current_status in ("rejected", "timeout"):
                        final_status = current_status
                        break
            except Exception:
                pass

        if final_status == "approved" and execution_result:
            max_length = await mcp_service.get_http_request_output_max_length()
            stdout = execution_result.get("stdout", "")
            stderr = execution_result.get("stderr", "")
            success = execution_result.get("success", False)
            if success:
                return [TextContent(type="text", text=f"```\n{stdout[:max_length]}\n```\n" if stdout else "*(No output)*\n")]
            else:
                response_text = f"HTTP request failed (exit code {execution_result.get('returncode', 'unknown')})\n"
                if stderr:
                    response_text += f"```\n{stderr[:500]}\n```\n"
                return [TextContent(type="text", text=response_text)]
        elif final_status == "rejected":
            return [TextContent(type="text", text="http_request rejected by user.")]
        else:
            return [TextContent(type="text", text=f"http_request approval timed out after {timeout_seconds}s. Request was NOT sent.")]

    # ========== EXECUTE IMMEDIATELY (OPEN MODE) ==========
    try:
        response = await mcp_service.http_client.post(
            f"{mcp_service.backend_url}/assessments/{mcp_service.current_assessment_id}/commands/http-request",
            json=http_payload
        )
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg and "Placeholder" in error_msg:
            return [TextContent(
                type="text",
                text=f"ERROR: {error_msg}\n\nUse `credentials_list` to see available placeholders, or `credentials_add` to add it."
            )]
        return [TextContent(type="text", text=f"ERROR making HTTP request: {error_msg}")]

    if result.get("status") == "timeout":
        timeout_val = result.get("execution_time", 30)
        return [TextContent(
            type="text",
            text=f"**Timeout ({timeout_val}s exceeded)**\n\nThe HTTP request timed out. Check target availability.\n"
        )]

    max_length = await mcp_service.get_http_request_output_max_length()

    if result.get("success"):
        stdout = result.get("stdout") or ""
        response_text = f"```\n{stdout[:max_length]}\n```\n" if stdout else "*(Request completed with no output)*\n"
    else:
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or ""
        if stdout:
            response_text = f"**HTTP request failed (exit code {result.get('returncode', 'unknown')}):**\n\n```\n{stdout[:max_length]}\n```\n"
            if stderr:
                response_text += f"\n**Stderr:**\n```\n{stderr[:500]}\n```\n"
        elif stderr:
            response_text = f"**HTTP error:**\n```\n{stderr[:500]}\n```\n"
        else:
            response_text = f"ERROR: HTTP request failed with exit code {result.get('returncode', 'unknown')}\n"

    return [TextContent(type="text", text=response_text)]


# ========== Pentesting Tools Handlers ==========

async def _handle_scan(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle scan with enhanced options for custom ports, wordlists, extensions, and more"""
    if not mcp_service.current_container:
        return [TextContent(type="text", text="No container selected for scanning.")]

    scan_type = arguments["type"]
    target = arguments["target"]
    
    # Optional parameters
    ports = arguments.get("ports")
    wordlist = arguments.get("wordlist", "common")
    extensions = arguments.get("extensions")
    threads = arguments.get("threads", 10)
    extra_flags = arguments.get("extra_flags", "")
    
    # Wordlist mapping
    WORDLISTS = {
        "common": "/usr/share/dirb/wordlists/common.txt",
        "medium": "/usr/share/dirbuster/directory-list-2.3-medium.txt",
        "large": "/usr/share/dirbuster/directory-list-2.3-big.txt",
        "dirb": "/usr/share/dirb/wordlists/big.txt",
        "raft-small": "/usr/share/seclists/Discovery/Web-Content/raft-small-words.txt",
        "raft-medium": "/usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt"
    }
    
    selected_wordlist = WORDLISTS.get(wordlist, WORDLISTS["common"])
    
    # Build commands dynamically based on scan type
    if scan_type == "nmap_quick":
        # Fast scan with version detection
        port_arg = f"-p {ports}" if ports else "-F"  # -F = fast (top 100 ports)
        command = f"nmap -sV {port_arg} {extra_flags} {target}".strip()
        
    elif scan_type == "nmap_full":
        # Comprehensive scan with all ports
        port_arg = f"-p {ports}" if ports else "-p-"  # All ports
        command = f"nmap -sS -sV -O -T4 {port_arg} {extra_flags} {target}".strip()
        
    elif scan_type == "nmap_vuln":
        # Vulnerability script scan
        port_arg = f"-p {ports}" if ports else ""
        command = f"nmap -sV --script=vuln {port_arg} {extra_flags} {target}".strip()
        
    elif scan_type == "gobuster":
        # Ensure target has protocol
        url = target if target.startswith(("http://", "https://")) else f"http://{target}"
        ext_arg = f"-x {extensions}" if extensions else ""
        command = f"gobuster dir -u {url} -w {selected_wordlist} -t {threads} {ext_arg} {extra_flags}".strip()
        
    elif scan_type == "ffuf":
        # Fast web fuzzer - ensure target has FUZZ placeholder or add one
        url = target if target.startswith(("http://", "https://")) else f"http://{target}"
        if "FUZZ" not in url:
            url = f"{url.rstrip('/')}/FUZZ"
        ext_arg = f"-e {extensions}" if extensions else ""
        command = f"ffuf -u {url} -w {selected_wordlist} -t {threads} {ext_arg} {extra_flags}".strip()
        
    elif scan_type == "dirb":
        url = target if target.startswith(("http://", "https://")) else f"http://{target}"
        ext_arg = f"-X .{extensions.replace(',', ',.')}" if extensions else ""
        command = f"dirb {url} {selected_wordlist} {ext_arg} {extra_flags}".strip()
        
    elif scan_type == "nikto":
        command = f"nikto -h {target} {extra_flags}".strip()
        
    else:
        return [TextContent(type="text", text=f"Unknown scan type: {scan_type}")]

    # Check if tool is available
    tool_name = command.split()[0]
    if not await mcp_service.check_tool_availability(tool_name):
        return [TextContent(type="text",
                            text=f"Tool `{tool_name}` not available in container.")]

    response = f"**Starting {scan_type} scan on `{target}`**\n"
    response += f"Command: `{command}`\n\n"

    result = await mcp_service.execute_container_command(
        mcp_service.current_container, command
    )

    if result["success"]:
        response += f"**Results:**\n```\n{result['stdout']}\n```"
        if result.get("stderr"):
            response += f"\n**Warnings:**\n```\n{result['stderr']}\n```"
    else:
        error_msg = result.get("stderr") or result.get("error", "Unknown error")
        response += f"**Scan failed:**\n```\n{error_msg}\n```"

    return [TextContent(type="text", text=response)]


async def _handle_subdomain_enum(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle subdomain_enum"""
    domain = arguments["domain"]

    result = await mcp_service.subdomain_enumeration(domain)

    if not result["success"]:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    response = f"**Subdomain Enumeration for `{domain}`:**\n\n"

    for i, cmd_result in enumerate(result["results"], 1):
        response += f"**Method {i}:** `{cmd_result['command'].split()[0]}`\n"
        if cmd_result["success"] and cmd_result["output"]:
            response += f"```\n{cmd_result['output']}\n```\n"
        elif cmd_result["error"]:
            response += f"Error: {cmd_result['error']}\n"
        response += "\n"

    return [TextContent(type="text", text=response)]


async def _handle_ssl_analysis(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle ssl_analysis"""
    target = arguments["target"]

    result = await mcp_service.ssl_analysis(target)

    if not result["success"]:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    response = f"**SSL Analysis for `{target}`:**\n\n"

    for cmd_result in result["results"]:
        if cmd_result["success"] and cmd_result["output"]:
            response += f"**{cmd_result['command'].replace('openssl x509 -noout -', '').title()}:**\n"
            response += f"```\n{cmd_result['output']}\n```\n\n"
        elif cmd_result["error"]:
            response += f"Error in {cmd_result['command']}: {cmd_result['error']}\n\n"

    return [TextContent(type="text", text=response)]


async def _handle_tech_detection(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle tech_detection"""
    url = arguments["url"]

    result = await mcp_service.tech_stack_detection(url)

    if not result["success"]:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    response = f"**Technology Detection for `{url}`:**\n\n"

    for cmd_result in result["results"]:
        if cmd_result["success"] and cmd_result["output"]:
            response += f"**{cmd_result['command'].split()[0].upper()}:**\n"
            response += f"```\n{cmd_result['output']}\n```\n\n"
        elif cmd_result["error"]:
            response += f"Error with {cmd_result['command']}: {cmd_result['error']}\n\n"

    return [TextContent(type="text", text=response)]


# ========== Credentials Management Handlers ==========

async def _handle_credentials_add(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle credentials_add - Add authentication credentials"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    credential_type = arguments["credential_type"]
    name = arguments["name"]

    # Auto-generate placeholder if not provided
    if "placeholder" in arguments and arguments["placeholder"]:
        placeholder = arguments["placeholder"]
    else:
        # Generate placeholder from name and type
        import re
        clean_name = re.sub(r'[^A-Z0-9\s]', '', name.upper()).replace(' ', '_')
        type_prefix = credential_type.upper().replace('_', '_')
        placeholder = f"{{{{{type_prefix}_{clean_name}}}}}"

    # Prepare credential data
    credential_data = {
        "credential_type": credential_type,
        "name": name,
        "placeholder": placeholder,
        "discovered_by": "claude"  # Marked as added by Claude
    }

    # Add optional fields if present
    optional_fields = ["token", "username", "password", "cookie_value", "custom_data", "service", "target", "notes"]
    for field in optional_fields:
        if field in arguments:
            credential_data[field] = arguments[field]

    # API call to create credential
    try:
        response = await mcp_service.http_client.post(
            f"{mcp_service.backend_url}/assessments/{mcp_service.current_assessment_id}/credentials",
            json=credential_data
        )
        response.raise_for_status()
        result = response.json()

        # Format response
        response_text = f"✅ Credential added: **{name}**\n\n"
        response_text += f"**Type:** {credential_type}\n"
        response_text += f"**Placeholder:** `{placeholder}`\n"

        if credential_data.get("target"):
            response_text += f"**Target:** {credential_data['target']}\n"

        if credential_data.get("service"):
            response_text += f"**Service:** {credential_data['service']}\n"

        response_text += f"\n💡 **Usage:** Use `{placeholder}` in your execute commands.\n"
        response_text += f"**Example:** `execute('curl -H \"Authorization: Bearer {placeholder}\" https://api.example.com')`"

        return [TextContent(type="text", text=response_text)]

    except Exception as e:
        error_msg = str(e)
        if "409" in error_msg or "already exists" in error_msg.lower():
            return [TextContent(
                type="text",
                text=f"❌ Error: Placeholder '{placeholder}' already exists for this assessment. Choose a different placeholder."
            )]
        else:
            return [TextContent(
                type="text",
                text=f"❌ Error adding credential: {error_msg}"
            )]


async def _handle_credentials_list(arguments: dict, mcp_service) -> List[TextContent]:
    """Handle credentials_list - List all credentials"""
    if not mcp_service.current_assessment_id:
        return [TextContent(type="text", text="No assessment loaded. Use 'load_assessment' first.")]

    # Filter by type if specified
    credential_type = arguments.get("credential_type")

    # API call to list credentials
    try:
        url = f"{mcp_service.backend_url}/assessments/{mcp_service.current_assessment_id}/credentials"
        if credential_type:
            url += f"?credential_type={credential_type}"

        response = await mcp_service.http_client.get(url)
        response.raise_for_status()
        result = response.json()

        credentials = result.get("credentials", [])
        total = result.get("total", 0)
        by_type = result.get("by_type", {})

        if total == 0:
            return [TextContent(
                type="text",
                text="No credentials found for this assessment.\n\nUse `credentials_add` to add authentication tokens, cookies, or other credentials."
            )]

        # Format response
        response_text = f"**Available Credentials ({total}):**\n\n"

        # Summary by type
        if by_type:
            response_text += "**By Type:**\n"
            for cred_type, count in by_type.items():
                response_text += f"- {cred_type}: {count}\n"
            response_text += "\n"

        # Detailed list
        response_text += "**Credentials:**\n\n"
        for i, cred in enumerate(credentials, 1):
            response_text += f"{i}. **{cred['name']}** ({cred['credential_type']})\n"
            response_text += f"   - Placeholder: `{cred['placeholder']}`\n"

            if cred.get("target"):
                response_text += f"   - Target: {cred['target']}\n"

            if cred.get("service"):
                response_text += f"   - Service: {cred['service']}\n"

            if cred.get("notes"):
                notes_preview = cred['notes'][:80] + "..." if len(cred['notes']) > 80 else cred['notes']
                response_text += f"   - Notes: {notes_preview}\n"

            response_text += f"   - Added: {cred.get('created_at', 'N/A')}\n"
            response_text += "\n"

        response_text += "💡 **Tip:** Use placeholders in execute commands for automatic substitution."

        return [TextContent(type="text", text=response_text)]

    except Exception as e:
        return [TextContent(
            type="text",
            text=f"❌ Error listing credentials: {str(e)}"
        )]
