"""
Nmap Parser - Parse nmap XML output
"""
# Uploaded scan files are untrusted input. ``defusedxml`` blocks entity
# expansion (billion-laughs) and external-entity/DTD attacks that the stdlib
# ``xml.etree.ElementTree`` parser is vulnerable to.
from defusedxml.ElementTree import ParseError, fromstring as safe_fromstring
from typing import List
from .base_parser import BaseParser, ParsedItem, ParseResult, ItemType, ScanType


class NmapParser(BaseParser):
    """Parser for nmap XML output (-oX flag)"""
    
    scan_type = ScanType.NMAP
    
    def can_parse(self, content: bytes, filename: str) -> bool:
        """Check if content is nmap XML"""
        try:
            # Check filename extension
            if filename.lower().endswith('.xml'):
                # Try to parse and look for nmap signature
                text = content.decode('utf-8', errors='ignore')
                if '<!DOCTYPE nmaprun' in text or '<nmaprun' in text:
                    return True
            return False
        except Exception:
            return False
    
    def parse(self, content: bytes, filename: str) -> ParseResult:
        """Parse nmap XML content"""
        items: List[ParsedItem] = []
        stats = {"hosts": 0, "services": 0, "open_ports": 0}
        
        try:
            # Parse XML
            text = content.decode('utf-8', errors='ignore')
            root = safe_fromstring(text)
            
            # Iterate over hosts
            for host in root.findall('.//host'):
                # Skip hosts that are down
                status = host.find('status')
                if status is not None and status.get('state') != 'up':
                    continue
                
                stats["hosts"] += 1
                
                # Get host address
                addr_elem = host.find('address[@addrtype="ipv4"]')
                if addr_elem is None:
                    addr_elem = host.find('address[@addrtype="ipv6"]')
                if addr_elem is None:
                    addr_elem = host.find('address')
                
                host_addr = addr_elem.get('addr') if addr_elem is not None else 'unknown'
                
                # Get hostname if available
                hostname = None
                hostnames = host.find('hostnames')
                if hostnames is not None:
                    hostname_elem = hostnames.find('hostname[@type="user"]')
                    if hostname_elem is None:
                        hostname_elem = hostnames.find('hostname')
                    if hostname_elem is not None:
                        hostname = hostname_elem.get('name')
                
                display_host = hostname or host_addr
                
                # Get OS detection if available
                os_info = None
                os_match = host.find('.//osmatch')
                if os_match is not None:
                    os_info = os_match.get('name')
                
                # Iterate over ports
                ports = host.find('ports')
                if ports is not None:
                    for port in ports.findall('port'):
                        port_id = port.get('portid')
                        protocol = port.get('protocol', 'tcp')
                        
                        # Check port state
                        state = port.find('state')
                        if state is None or state.get('state') != 'open':
                            continue
                        
                        stats["open_ports"] += 1
                        stats["services"] += 1
                        
                        # Get service info
                        service = port.find('service')
                        service_name = 'unknown'
                        version = None
                        product = None
                        extra_info = None
                        
                        if service is not None:
                            service_name = service.get('name', 'unknown')
                            version = service.get('version')
                            product = service.get('product')
                            extra_info = service.get('extrainfo')
                        
                        # Get script results if any
                        scripts = {}
                        for script in port.findall('script'):
                            script_id = script.get('id')
                            script_output = script.get('output', '')
                            if script_id:
                                scripts[script_id] = script_output[:500]  # Limit size
                        
                        # Build display name
                        display_name = f"{display_host}:{port_id}/{service_name}"
                        
                        # Build dedup key
                        dedup_key = f"{host_addr}:{port_id}:{protocol}"
                        
                        # Build version string
                        version_str = None
                        if product or version:
                            parts = [p for p in [product, version] if p]
                            version_str = " ".join(parts)
                        
                        item = ParsedItem(
                            id=self._generate_id("nmap", host_addr, port_id, protocol),
                            item_type=ItemType.SERVICE,
                            name=display_name,
                            source=ScanType.NMAP,
                            source_file=filename,
                            dedup_key=dedup_key,
                            details={
                                "host": host_addr,
                                "hostname": hostname,
                                "port": int(port_id),
                                "protocol": protocol,
                                "service": service_name,
                                "version": version_str,
                                "product": product,
                                "extra_info": extra_info,
                                "os": os_info,
                                "scripts": scripts if scripts else None
                            }
                        )
                        items.append(item)
            
            return ParseResult(
                success=True,
                scan_type=ScanType.NMAP,
                filename=filename,
                items=items,
                stats=stats
            )
            
        except ParseError as e:
            return ParseResult(
                success=False,
                scan_type=ScanType.NMAP,
                filename=filename,
                error=f"Invalid XML format: {str(e)}"
            )
        except Exception as e:
            return ParseResult(
                success=False,
                scan_type=ScanType.NMAP,
                filename=filename,
                error=f"Parse error: {str(e)}"
            )
