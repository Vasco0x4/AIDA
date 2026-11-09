"""
Intelligent scan output parsers
Reduce large scan outputs to essential summaries
"""
from typing import Dict, Any


def parse_scan_output(command: str, result: Dict[str, Any], max_length: int = 5000) -> str:
    """
    Parse scan output intelligently based on command type
    Returns a concise summary instead of full output

    Args:
        command: The command that was executed
        result: The command result dictionary
        max_length: Maximum length for generic output truncation (default: 5000, -1 for unlimited)
    """
    stdout = result.get("stdout", "")
    cmd_lower = command.lower()

    # NMAP Parser
    if "nmap" in cmd_lower:
        return parse_nmap_output(stdout, result)

    # Gobuster Parser
    elif "gobuster" in cmd_lower:
        return parse_gobuster_output(stdout, result)

    # Nikto Parser
    elif "nikto" in cmd_lower:
        return parse_nikto_output(stdout, result)

    # Nuclei Parser
    elif "nuclei" in cmd_lower:
        return parse_nuclei_output(stdout, result)

    # Subfinder/Amass (subdomain enum)
    elif "subfinder" in cmd_lower or "amass" in cmd_lower:
        return parse_subdomain_output(stdout, result)

    # Generic (truncate)
    else:
        return parse_generic_output(stdout, result, max_length)


def parse_nmap_output(stdout: str, result: Dict[str, Any]) -> str:
    """Parse nmap output - keep only essentials"""
    lines = stdout.split('\n')

    # Extract open ports
    open_ports = []
    for line in lines:
        if '/tcp' in line and 'open' in line:
            open_ports.append(line.strip())

    # Extract services
    services = []
    for line in lines:
        if 'Service Info:' in line or 'Running:' in line:
            services.append(line.strip())

    # Build summary
    output = "**Nmap Scan Results:**\n\n"

    if open_ports:
        output += f"**Open Ports ({len(open_ports)}):**\n"
        for port in open_ports[:15]:  # Max 15 ports
            output += f"  {port}\n"
        if len(open_ports) > 15:
            output += f"  ... and {len(open_ports) - 15} more ports\n"
    else:
        output += "No open ports found.\n"

    if services:
        output += "\n**Services Detected:**\n"
        for service in services[:5]:
            output += f"  {service}\n"

    return output


def parse_gobuster_output(stdout: str, result: Dict[str, Any]) -> str:
    """Parse gobuster output - summary of discoveries"""
    lines = stdout.split('\n')

    # Extract found paths
    found_paths = []
    for line in lines:
        if line.startswith('/') or 'Status:' in line:
            found_paths.append(line.strip())

    output = "**Gobuster Scan Results:**\n\n"

    if found_paths:
        output += f"**Found Paths ({len(found_paths)}):**\n"
        # Group by status code
        status_200 = [p for p in found_paths if '200' in p]
        status_301 = [p for p in found_paths if '301' in p or '302' in p]
        status_403 = [p for p in found_paths if '403' in p]

        if status_200:
            output += f"\n**Status 200 ({len(status_200)}):**\n"
            for path in status_200[:10]:
                output += f"  {path}\n"

        if status_301:
            output += f"\n**Redirects ({len(status_301)}):**\n"
            for path in status_301[:5]:
                output += f"  {path}\n"

        if status_403:
            output += f"\n**🔒 Forbidden ({len(status_403)}):**\n"
            for path in status_403[:5]:
                output += f"  {path}\n"
    else:
        output += "No paths found.\n"

    return output


def parse_nikto_output(stdout: str, result: Dict[str, Any]) -> str:
    """Parse nikto output - summary of vulnerabilities"""
    lines = stdout.split('\n')

    # Extract findings
    findings = []
    for line in lines:
        if line.startswith('+') and ('OSVDB' in line or 'CVE' in line or 'vuln' in line.lower()):
            findings.append(line.strip())

    output = "**Nikto Scan Results:**\n\n"

    if findings:
        output += f"**Potential Issues ({len(findings)}):**\n"
        for finding in findings[:10]:
            output += f"  {finding}\n"
        if len(findings) > 10:
            output += f"  ... and {len(findings) - 10} more findings\n"
    else:
        output += "No major issues found.\n"

    return output


def parse_nuclei_output(stdout: str, result: Dict[str, Any]) -> str:
    """Parse nuclei output - vulnerability summary"""
    lines = stdout.split('\n')

    # Extract vulnerabilities by severity
    critical = []
    high = []
    medium = []
    low = []

    for line in lines:
        if '[critical]' in line.lower():
            critical.append(line.strip())
        elif '[high]' in line.lower():
            high.append(line.strip())
        elif '[medium]' in line.lower():
            medium.append(line.strip())
        elif '[low]' in line.lower() or '[info]' in line.lower():
            low.append(line.strip())

    output = "**Nuclei Scan Results:**\n\n"

    if critical:
        output += f"**🔴 CRITICAL ({len(critical)}):**\n"
        for vuln in critical[:5]:
            output += f"  {vuln}\n"

    if high:
        output += f"\n**🟠 HIGH ({len(high)}):**\n"
        for vuln in high[:5]:
            output += f"  {vuln}\n"

    if medium:
        output += f"\n**🟡 MEDIUM ({len(medium)}):**\n"
        for vuln in medium[:5]:
            output += f"  {vuln}\n"

    total = len(critical) + len(high) + len(medium) + len(low)
    output += f"\nTotal findings: {total}\n"

    return output


def parse_subdomain_output(stdout: str, result: Dict[str, Any]) -> str:
    """Parse subdomain enumeration output"""
    lines = stdout.split('\n')
    subdomains = [line.strip() for line in lines if line.strip() and '.' in line]

    output = "**Subdomain Enumeration Results:**\n\n"

    if subdomains:
        output += f"**Found {len(subdomains)} subdomains:**\n"
        for subdomain in subdomains[:20]:
            output += f"  {subdomain}\n"
        if len(subdomains) > 20:
            output += f"  ... and {len(subdomains) - 20} more\n"
    else:
        output += "No subdomains found.\n"

    return output


def parse_generic_output(stdout: str, result: Dict[str, Any], max_length: int = 5000) -> str:
    """Fallback - generic truncation

    Args:
        stdout: Command stdout
        result: Command result dictionary
        max_length: Maximum length for output truncation (default: 5000, -1 for unlimited)
    """
    if result.get("success"):
        if stdout:
            # Skip truncation if max_length is -1 (unlimited)
            if max_length == -1:
                truncated = stdout
                response = f"```\n{truncated}\n```\n"
            else:
                truncated = stdout[:max_length]
                response = f"```\n{truncated}\n```\n"
                if len(stdout) > max_length:
                    response += f"\n... (output truncated - showing {max_length}/{len(stdout)} chars)\n"
        else:
            # No stdout - check if there's stderr (e.g., grep "binary file matches")
            stderr = result.get("stderr", "").strip()
            if stderr:
                # Show stderr as it contains important info (like grep binary file warning)
                response = f"No output (stderr: {stderr[:500]})\n"
            else:
                response = "Command completed (no output)\n"
    else:
        stderr = result.get("stderr", "Unknown error")
        response = f"ERROR: {stderr[:500]}"

    return response
