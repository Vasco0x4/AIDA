"""
Tool Usage Analyzer - Extract and categorize tools from commands
"""
from typing import Any, Dict, List


# Tool categorization mapping
TOOL_CATEGORIES: Dict[str, List[str]] = {
    "recon": [
        # Port scanners
        "nmap", "masscan", "rustscan", "zmap",
        # Subdomain enumeration
        "subfinder", "amass", "assetfinder", "sublist3r", "findomain",
        # DNS enumeration
        "dnsenum", "dnsrecon", "fierce", "dnsmap",
        # DNS tools
        "whois", "dig", "host", "nslookup",
        # Network discovery
        "arp-scan", "netdiscover"
    ],
    "web": [
        # HTTP clients
        "curl", "wget", "httpx", "httprobe",
        # Directory/file fuzzing
        "gobuster", "dirb", "ffuf", "feroxbuster", "wfuzz", "dirsearch",
        # Web scanners
        "nikto", "whatweb", "wafw00f", "wappalyzer", "nuclei",
        # Web proxies
        "burpsuite", "zaproxy", "mitmproxy"
    ],
    "exploitation": [
        # SQL injection
        "sqlmap",
        # Metasploit
        "metasploit", "msfconsole", "msfvenom",
        # Exploit search
        "searchsploit", "exploitdb",
        # Framework
        "nuclei", "commix", "xsstrike"
    ],
    "file_ops": [
        # File viewers
        "cat", "less", "more", "head", "tail", "bat",
        # Text processing
        "grep", "egrep", "fgrep", "awk", "sed", "cut", "sort", "uniq",
        # File utilities
        "find", "locate", "ls", "tree", "file"
    ],
    "network": [
        # Network tools
        "ping", "traceroute", "tracert", "mtr",
        # Connection tools
        "netcat", "nc", "ncat", "telnet", "ssh", "scp", "sftp",
        # Protocol tools
        "openssl", "socat", "tcpdump", "wireshark", "tshark"
    ],
    "password": [
        # Password attacks
        "hydra", "medusa", "john", "hashcat", "crunch",
        # Hash tools
        "hash-identifier", "hashid"
    ],
    "other": []
}


def extract_tool_name(command: str) -> str:
    """
    Extract the tool name from a command string
    
    Examples:
        "nmap -sV -p- target.com" → "nmap"
        "curl -I https://example.com" → "curl"
        "sudo nmap ..." → "nmap" (ignores sudo)
        "cat /context/file.txt" → "cat"
        "/usr/bin/nmap" → "nmap"
    
    Args:
        command: Full command string
        
    Returns:
        Tool name (lowercase)
    """
    # Clean and split
    parts = command.strip().split()
    
    if not parts:
        return "unknown"
    
    # Ignore common prefixes
    prefixes_to_ignore = {'sudo', 'time', 'timeout', 'watch', 'nice', 'nohup'}
    
    tool = parts[0]
    idx = 0
    
    # Ignore all prefixes until finding the real command
    while tool.lower() in prefixes_to_ignore and idx + 1 < len(parts):
        idx += 1
        tool = parts[idx]
    
    # Extract just the name (without path)
    # Ex: "/usr/bin/nmap" → "nmap"
    if '/' in tool:
        tool = tool.split('/')[-1]
    
    # Clean potential special characters
    tool = tool.strip(',.;:')
    
    return tool.lower()


def categorize_tool(tool: str) -> str:
    """
    Categorize a tool into one of the predefined categories
    
    Args:
        tool: Tool name (lowercase)
        
    Returns:
        Category name (e.g., 'recon', 'web', 'exploitation', etc.)
        Returns 'other' if tool is not in any category
    """
    for category, tools in TOOL_CATEGORIES.items():
        if tool in tools:
            return category
    
    return "other"


def get_all_tools_in_category(category: str) -> List[str]:
    """
    Get all tools in a specific category
    
    Args:
        category: Category name
        
    Returns:
        List of tool names in that category
    """
    return TOOL_CATEGORIES.get(category, [])


def get_tool_counts_by_category(
    tool_counts: Dict[str, int]
) -> Dict[str, Dict[str, Any]]:
    """
    Group tool counts by category
    
    Args:
        tool_counts: Dictionary of {tool_name: count}
        
    Returns:
        Dictionary of {category: {"count": int, "tools": [str]}}
    """
    category_stats = {}
    
    # Initialize all categories
    for category in TOOL_CATEGORIES.keys():
        category_stats[category] = {
            "count": 0,
            "tools": []
        }
    
    # Count tools by category
    for tool, count in tool_counts.items():
        category = categorize_tool(tool)
        
        if category not in category_stats:
            category_stats[category] = {"count": 0, "tools": []}
        
        category_stats[category]["count"] += count
        if tool not in category_stats[category]["tools"]:
            category_stats[category]["tools"].append(tool)
    
    return category_stats
