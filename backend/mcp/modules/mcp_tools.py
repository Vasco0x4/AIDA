"""
MCP Tools Definitions - Refactored according to specifications
- Renamed: start_assessment → load_assessment
- Added: create_assessment, list_assessments, list_containers
- Removed: section_number from add_finding, add_observation, add_info
- Added: 9 new tools (list_*, update_*)
"""
from typing import List
from mcp.types import Tool


def get_tool_definitions() -> List[Tool]:
    """Get all MCP tool definitions"""
    return [
        # ========== Assessment Management (5 tools) ==========
        Tool(
            name="load_assessment",
            description="Load an existing assessment to begin work. Returns full state: scope, phases, cards (findings/observations/info), recon data, credentials, and workspace structure.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the assessment to load"
                    },
                    "skip_data": {
                        "type": "boolean",
                        "description": "If true, only reloads assessment without returning any context.",
                        "default": False
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="create_assessment",
            description="Create a new pentest assessment and auto-load it. Gather scope, targets, and constraints from the user BEFORE calling this tool.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Assessment name (must be unique)"
                    },
                    "client_name": {
                        "type": "string",
                        "description": "Client or organization name"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["API", "Website", "External Infra", "Mobile", "Cloud", "General"],
                        "description": "Assessment category"
                    },
                    "scope": {
                        "type": "string",
                        "description": "What is in scope (targets, applications, networks)"
                    },
                    "limitations": {
                        "type": "string",
                        "description": "What is out of scope or restricted"
                    },
                    "objectives": {
                        "type": "string",
                        "description": "Goals of the assessment"
                    },
                    "target_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Target domains (e.g., ['example.com', 'api.example.com'])"
                    },
                    "ip_scopes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IP addresses or CIDR ranges in scope (e.g., ['10.0.0.0/24', '192.168.1.100'])"
                    },
                    "environment": {
                        "type": "string",
                        "enum": ["non_specifie", "production", "dev"],
                        "description": "Target environment (default: non_specifie)"
                    },
                    "environment_notes": {
                        "type": "string",
                        "description": "Additional notes about the environment"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date (YYYY-MM-DD format)"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date (YYYY-MM-DD format)"
                    },
                    "credentials": {
                        "type": "string",
                        "description": "Initial credentials or access information"
                    },
                    "access_info": {
                        "type": "string",
                        "description": "VPN, jump hosts, or other access details"
                    }
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="list_assessments",
            description="List existing assessments. Useful to check what exists before creating a new one or to find an assessment to load.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "completed", "archived"],
                        "description": "Filter by status (optional, shows all if not specified)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of assessments to return",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="list_containers",
            description="List available pentesting containers with their status. No assessment needs to be loaded.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="update_phase",
            description="Update content of a phase section (free text, markdown supported)",
            inputSchema={
                "type": "object",
                "properties": {
                    "phase_number": {
                        "type": "number",
                        "description": "Phase number (1.0, 2.0, 3.0, etc.)"
                    },
                    "title": {
                        "type": "string",
                        "description": "Section title"
                    },
                    "content": {
                        "type": "string",
                        "description": "Phase content (markdown supported)"
                    }
                },
                "required": ["phase_number", "content"]
            }
        ),

        # ========== Cards Management (4 unified tools) ==========
        Tool(
            name="add_card",
            description="Add a card (finding, observation, or info) - returns the created card ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "card_type": {
                        "type": "string",
                        "enum": ["finding", "observation", "info"],
                        "description": "Type of card to create"
                    },
                    "title": {
                        "type": "string",
                        "description": "Card title (vulnerability name for findings)"
                    },
                    "target_service": {
                        "type": "string",
                        "description": "Target or service affected"
                    },
                    # Finding-specific fields
                    "cvss_vector": {
                        "type": "string",
                        "description": "CVSS 4.0 vector string (preferred for findings). Example: CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N. Severity will be automatically calculated from the score."
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
                        "description": "Severity level for findings. Use cvss_vector instead when possible — severity will be derived automatically. Use this only when CVSS cannot be assessed."
                    },
                    "status": {
                        "type": "string",
                        "enum": ["confirmed", "potential", "untested"],
                        "description": "Status of finding (default: confirmed)"
                    },
                    "technical_analysis": {
                        "type": "string",
                        "description": "Technical analysis and notes"
                    },
                    "proof": {
                        "type": "string",
                        "description": "Proof of concept or evidence"
                    },
                    # Observation-specific
                    "notes": {
                        "type": "string",
                        "description": "Observation notes"
                    },
                    # Info-specific
                    "context": {
                        "type": "string",
                        "description": "Contextual information"
                    }
                },
                "required": ["card_type", "title"]
            }
        ),
        Tool(
            name="list_cards",
            description="List all cards with optional type filter",
            inputSchema={
                "type": "object",
                "properties": {
                    "card_type": {
                        "type": "string",
                        "enum": ["finding", "observation", "info"],
                        "description": "Filter by card type (optional, shows all if not specified)"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
                        "description": "Filter findings by severity (optional)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of cards to return",
                        "default": 50
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="update_card",
            description="Update an existing card by ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "card_id": {
                        "type": "integer",
                        "description": "ID of the card to update"
                    },
                    "title": {
                        "type": "string",
                        "description": "New title"
                    },
                    "target_service": {
                        "type": "string",
                        "description": "Updated target/service"
                    },
                    "cvss_vector": {
                        "type": "string",
                        "description": "Updated CVSS 4.0 vector string. Severity will be automatically recalculated from the new score."
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
                        "description": "New severity level (findings only). Prefer cvss_vector when possible."
                    },
                    "status": {
                        "type": "string",
                        "enum": ["confirmed", "potential", "untested"],
                        "description": "Updated status (findings only)"
                    },
                    "technical_analysis": {
                        "type": "string",
                        "description": "Updated technical analysis"
                    },
                    "proof": {
                        "type": "string",
                        "description": "Updated proof of concept"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Updated notes (observations)"
                    },
                    "context": {
                        "type": "string",
                        "description": "Updated context (info cards)"
                    }
                },
                "required": ["card_id"]
            }
        ),
        Tool(
            name="delete_card",
            description="Delete a card by ID (finding, observation, or info)",
            inputSchema={
                "type": "object",
                "properties": {
                    "card_id": {
                        "type": "integer",
                        "description": "ID of the card to delete"
                    }
                },
                "required": ["card_id"]
            }
        ),

        # ========== Reconnaissance Management (2 tools) ==========
        Tool(
            name="add_recon_data",
            description="Add reconnaissance data (single entry or batch). Provide either (data_type + name) for single entry OR entries array for batch.",
            inputSchema={
                "type": "object",
                "properties": {
                    # Single entry mode
                    "data_type": {
                        "type": "string",
                        "description": "Type discovered (lowercase snake_case). Examples: endpoint, subdomain, service, technology, database, credential, port, vulnerability"
                    },
                    "name": {
                        "type": "string",
                        "description": "Name/value of the discovered data"
                    },
                    "details": {
                        "type": "object",
                        "description": "Additional details (JSON object)"
                    },
                    "discovered_in_phase": {
                        "type": "string",
                        "description": "Phase where this was discovered"
                    },
                    # Batch mode
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "data_type": {
                                    "type": "string",
                                    "description": "Type discovered (lowercase snake_case). Examples: endpoint, subdomain, service, technology, database, credential, port, vulnerability"
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Name/value of the discovered data"
                                },
                                "details": {
                                    "type": "object",
                                    "description": "Additional details (JSON object)"
                                },
                                "discovered_in_phase": {
                                    "type": "string",
                                    "description": "Phase where this was discovered"
                                }
                            },
                            "required": ["data_type", "name"]
                        },
                        "description": "Array of recon data entries to add (batch mode)"
                    }
                }
                # Note: No required fields - validation happens in handler
                # Handler will check: must have either (data_type AND name) OR entries
            }
        ),
        Tool(
            name="list_recon",
            description="List reconnaissance data with optional filters",
            inputSchema={
                "type": "object",
                "properties": {
                    "data_type": {
                        "type": "string",
                        "description": "Filter by data type (optional). Use any category available in the assessment."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of recon items to return",
                        "default": 50
                    }
                },
                "required": []
            }
        ),

        # ========== Command Execution (1 tool) ==========


        Tool(
            name="execute",
            description="Execute a command in the active pentesting container",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command to execute"
                    },
                    "phase": {
                        "type": "string",
                        "description": "Current phase (for logging)"
                    }
                },
                "required": ["command"]
            }
        ),

        Tool(
            name="python_exec",
            description=(
                "Execute Python code directly in the active pentesting container"
                "Pass multi-line Python as a plain string — no heredoc, no backslash hell, no quoting errors. "
                "Use this instead of execute() for any Python script. "
                "Supports {{PLACEHOLDER}} credential substitution in the code."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute (multi-line supported, no escaping needed)"
                    },
                    "phase": {
                        "type": "string",
                        "description": "Current phase (for logging)"
                    }
                },
                "required": ["code"]
            }
        ),

        Tool(
            name="http_request",
            description=(
                "Make HTTP requests from inside the active pentesting container — no curl escaping hell. "
                "Pass structured params (method, headers, json body, cookies, auth, proxy). "
                "Execution stays inside the container (network isolation, VPN access). "
                "Use proxy='http://127.0.0.1:8080' to route through Burp Suite. "
                "Supports {{PLACEHOLDER}} credential substitution on url, headers, cookies, auth."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Target URL (supports {{PLACEHOLDER}} substitution)"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                        "description": "HTTP method (default: GET)"
                    },
                    "headers": {
                        "type": "object",
                        "description": "Request headers as key-value pairs (values support {{PLACEHOLDER}})"
                    },
                    "params": {
                        "type": "object",
                        "description": "Query string parameters as key-value pairs"
                    },
                    "data": {
                        "type": ["object", "string"],
                        "description": "Form data (dict) or raw body string"
                    },
                    "json": {
                        "type": "object",
                        "description": "JSON body — auto-sets Content-Type: application/json"
                    },
                    "cookies": {
                        "type": "object",
                        "description": "Cookies as key-value pairs (values support {{PLACEHOLDER}})"
                    },
                    "auth": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 2,
                        "description": "Basic auth as [username, password] (supports {{PLACEHOLDER}})"
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Request timeout in seconds (default: 30)"
                    },
                    "follow_redirects": {
                        "type": "boolean",
                        "description": "Follow HTTP redirects (default: true)"
                    },
                    "verify_ssl": {
                        "type": "boolean",
                        "description": "Verify SSL certificate (default: true, set false for self-signed)"
                    },
                    "proxy": {
                        "type": "string",
                        "description": "Proxy URL e.g. 'http://127.0.0.1:8080' to route through Burp Suite"
                    },
                    "phase": {
                        "type": "string",
                        "description": "Current assessment phase (for logging)"
                    }
                },
                "required": ["url"]
            }
        ),

        # ========== Pentesting Tools (5 tools) ==========
        Tool(
            name="scan",
            description="Run security scans with common tools. Use optional parameters for advanced control, or use execute() for full flexibility.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["nmap_quick", "nmap_full", "nmap_vuln", "dirb", "nikto", "gobuster", "ffuf"],
                        "description": "Scan type: nmap_quick (fast top ports), nmap_full (all ports + version), nmap_vuln (vuln scripts), dirb/gobuster/ffuf (web fuzzing), nikto (web server scan)"
                    },
                    "target": {
                        "type": "string",
                        "description": "Target IP, domain, or URL (include http:// for web scans)"
                    },
                    "ports": {
                        "type": "string",
                        "description": "Port specification for nmap (e.g., '80,443', '1-1000', '22,80,443,8080'). Default: top 100 for quick, all for full."
                    },
                    "wordlist": {
                        "type": "string",
                        "enum": ["common", "medium", "large", "dirb", "raft-small", "raft-medium"],
                        "description": "Wordlist for directory/file discovery. common=fast, medium=balanced, large=thorough. Default: common"
                    },
                    "extensions": {
                        "type": "string",
                        "description": "File extensions to check (e.g., 'php,html,js,txt'). Applies to gobuster/ffuf/dirb."
                    },
                    "threads": {
                        "type": "integer",
                        "description": "Number of threads for parallel scanning. Default: 10 for web fuzzers."
                    },
                    "extra_flags": {
                        "type": "string",
                        "description": "Additional flags to pass to the underlying tool (e.g., '-sC' for nmap scripts, '--follow-redirect' for ffuf)"
                    }
                },
                "required": ["type", "target"]
            }
        ),
        Tool(
            name="subdomain_enum",
            description="Perform subdomain enumeration using subfinder/amass",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Domain to enumerate subdomains for"
                    }
                },
                "required": ["domain"]
            }
        ),
        Tool(
            name="ssl_analysis",
            description="Analyze SSL certificate of target",
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Target host:port (default port 443)"
                    }
                },
                "required": ["target"]
            }
        ),
        Tool(
            name="tech_detection",
            description="Detect technology stack of a website",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to analyze"
                    }
                },
                "required": ["url"]
            }
        ),
        # ========== Credentials Management (2 tools) ==========
        Tool(
            name="credentials_add",
            description="Add authentication credentials (bearer tokens, cookies, SSH creds, etc.) - Placeholder auto-generated from name",
            inputSchema={
                "type": "object",
                "properties": {
                    "credential_type": {
                        "type": "string",
                        "enum": ["bearer_token", "cookie", "basic_auth", "api_key", "ssh", "custom"],
                        "description": "Type of credential"
                    },
                    "name": {
                        "type": "string",
                        "description": "Descriptive name (e.g., 'Fleet Manager Auth') - placeholder will be auto-generated"
                    },
                    "placeholder": {
                        "type": "string",
                        "description": "Optional: Custom placeholder (auto-generated from name if not provided)"
                    },
                    "token": {
                        "type": "string",
                        "description": "Token value (for bearer_token, api_key)"
                    },
                    "username": {
                        "type": "string",
                        "description": "Username (for basic_auth, ssh)"
                    },
                    "password": {
                        "type": "string",
                        "description": "Password (for basic_auth, ssh)"
                    },
                    "cookie_value": {
                        "type": "string",
                        "description": "Cookie string (for cookie type)"
                    },
                    "custom_data": {
                        "type": "object",
                        "description": "Custom data (JSON object for custom type)"
                    },
                    "service": {
                        "type": "string",
                        "description": "Service name (SSH, API, Web, etc.)"
                    },
                    "target": {
                        "type": "string",
                        "description": "Target URL or IP"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes (e.g., 'Found in config file', 'Expires in 15 min')"
                    }
                },
                "required": ["credential_type", "name"]
            }
        ),
        Tool(
            name="credentials_list",
            description="List all available credentials with their placeholders and types",
            inputSchema={
                "type": "object",
                "properties": {
                    "credential_type": {
                        "type": "string",
                        "enum": ["bearer_token", "cookie", "basic_auth", "api_key", "ssh", "custom"],
                        "description": "Filter by type (optional)"
                    }
                },
                "required": []
            }
        ),
    ]
