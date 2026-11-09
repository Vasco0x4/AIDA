"""
Ffuf Parser - Parse ffuf JSON output
"""
import json
from typing import List
from urllib.parse import urlparse
from .base_parser import BaseParser, ParsedItem, ParseResult, ItemType, ScanType


class FfufParser(BaseParser):
    """Parser for ffuf JSON output (-of json flag)"""
    
    scan_type = ScanType.FFUF
    
    def can_parse(self, content: bytes, filename: str) -> bool:
        """Check if content is ffuf JSON output"""
        try:
            if not filename.lower().endswith('.json'):
                return False
            
            text = content.decode('utf-8', errors='ignore').strip()
            data = json.loads(text)
            
            # ffuf output has specific structure
            if isinstance(data, dict):
                # Check for ffuf-specific fields
                has_results = 'results' in data
                has_config = 'config' in data or 'commandline' in data
                return has_results and has_config
            
            return False
        except Exception:
            return False
    
    def parse(self, content: bytes, filename: str) -> ParseResult:
        """Parse ffuf JSON content"""
        items: List[ParsedItem] = []
        stats = {
            "endpoints": 0, 
            "status_2xx": 0, 
            "status_3xx": 0, 
            "status_4xx": 0, 
            "status_5xx": 0
        }
        
        try:
            text = content.decode('utf-8', errors='ignore').strip()
            data = json.loads(text)
            
            # Get results array
            results = data.get('results', [])
            
            # Track seen URLs to avoid duplicates within same file
            seen_urls = set()
            
            for result in results:
                # Get URL
                url = result.get('url', '')
                if not url:
                    continue
                
                # Skip duplicates within file
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                
                # Get response info
                status = result.get('status', 0)
                length = result.get('length', 0)
                words = result.get('words', 0)
                lines = result.get('lines', 0)
                content_type = result.get('content-type', '')
                redirect_location = result.get('redirectlocation', '')
                
                # Extract path from URL
                try:
                    parsed = urlparse(url)
                    path = parsed.path or '/'
                    host = parsed.netloc
                except Exception:
                    path = url
                    host = ''
                
                # Build display name (just the path for cleaner display)
                display_name = path
                
                # Build dedup key: normalized URL without query params
                dedup_key = f"ffuf:{host}:{path}"
                
                # Count by status code
                stats["endpoints"] += 1
                if 200 <= status < 300:
                    stats["status_2xx"] += 1
                elif 300 <= status < 400:
                    stats["status_3xx"] += 1
                elif 400 <= status < 500:
                    stats["status_4xx"] += 1
                elif status >= 500:
                    stats["status_5xx"] += 1
                
                item = ParsedItem(
                    id=self._generate_id("ffuf", url),
                    item_type=ItemType.ENDPOINT,
                    name=display_name,
                    source=ScanType.FFUF,
                    source_file=filename,
                    dedup_key=dedup_key,
                    details={
                        "url": url,
                        "host": host,
                        "path": path,
                        "status_code": status,
                        "content_length": length,
                        "word_count": words,
                        "line_count": lines,
                        "content_type": content_type,
                        "redirect_location": redirect_location if redirect_location else None
                    }
                )
                items.append(item)
            
            return ParseResult(
                success=True,
                scan_type=ScanType.FFUF,
                filename=filename,
                items=items,
                stats=stats
            )
            
        except json.JSONDecodeError as e:
            return ParseResult(
                success=False,
                scan_type=ScanType.FFUF,
                filename=filename,
                error=f"Invalid JSON format: {str(e)}"
            )
        except Exception as e:
            return ParseResult(
                success=False,
                scan_type=ScanType.FFUF,
                filename=filename,
                error=f"Parse error: {str(e)}"
            )
