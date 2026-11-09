"""
Scan Importer - Main orchestrator for importing scan results
Handles file detection, parsing, deduplication, and database import
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models.recon_data import ReconData
from models.card import Card

from .base_parser import BaseParser, ParsedItem, ParseResult, ItemType, ScanType
from .nmap_parser import NmapParser
from .nuclei_parser import NucleiParser
from .ffuf_parser import FfufParser


class ScanImportError(Exception):
    """Custom exception for scan import errors"""
    pass


class ScanImporter:
    """
    Main service for importing scan results into an assessment
    
    Supports:
    - nmap XML output
    - nuclei JSON/JSONL output
    - ffuf JSON output
    """
    
    # Available parsers in priority order
    PARSERS: List[BaseParser] = [
        NmapParser(),
        NucleiParser(),
        FfufParser()
    ]
    
    def __init__(self, db: Session, assessment_id: int):
        self.db = db
        self.assessment_id = assessment_id
    
    def detect_scan_type(self, content: bytes, filename: str) -> Tuple[ScanType, Optional[BaseParser]]:
        """
        Auto-detect scan type from file content
        
        Returns:
            Tuple of (ScanType, Parser) or (UNKNOWN, None) if not detected
        """
        for parser in self.PARSERS:
            if parser.can_parse(content, filename):
                return parser.scan_type, parser
        
        return ScanType.UNKNOWN, None
    
    def parse_file(self, content: bytes, filename: str) -> ParseResult:
        """
        Parse a single scan file
        
        Args:
            content: Raw file content
            filename: Original filename
            
        Returns:
            ParseResult with parsed items
        """
        scan_type, parser = self.detect_scan_type(content, filename)
        
        if parser is None:
            return ParseResult(
                success=False,
                scan_type=ScanType.UNKNOWN,
                filename=filename,
                error="Unknown scan format. Supported: nmap XML, nuclei JSON, ffuf JSON"
            )
        
        return parser.parse(content, filename)
    
    def parse_files(self, files: List[Tuple[bytes, str]]) -> Dict[str, Any]:
        """
        Parse multiple scan files and return aggregated preview
        
        Args:
            files: List of (content, filename) tuples
            
        Returns:
            Aggregated preview data with deduplication info
        """
        all_items: List[ParsedItem] = []
        file_results: List[Dict] = []
        
        for content, filename in files:
            result = self.parse_file(content, filename)
            file_results.append({
                "filename": filename,
                "success": result.success,
                "scan_type": result.scan_type.value,
                "error": result.error,
                "item_count": len(result.items),
                "stats": result.stats
            })
            
            if result.success:
                all_items.extend(result.items)
        
        # Check for duplicates against database
        self._check_duplicates(all_items)
        
        # Group items by type
        grouped_items = {
            "services": [],
            "endpoints": [],
            "findings": []
        }
        
        for item in all_items:
            item_dict = item.to_dict()
            if item.item_type == ItemType.SERVICE:
                grouped_items["services"].append(item_dict)
            elif item.item_type == ItemType.ENDPOINT:
                grouped_items["endpoints"].append(item_dict)
            elif item.item_type == ItemType.FINDING:
                grouped_items["findings"].append(item_dict)
        
        # Calculate stats
        total = len(all_items)
        duplicates = sum(1 for item in all_items if item.is_duplicate)
        
        return {
            "success": True,
            "files": file_results,
            "items": grouped_items,
            "stats": {
                "total": total,
                "services": len(grouped_items["services"]),
                "endpoints": len(grouped_items["endpoints"]),
                "findings": len(grouped_items["findings"]),
                "duplicates": duplicates,
                "new_items": total - duplicates
            }
        }
    
    def _check_duplicates(self, items: List[ParsedItem]) -> None:
        """
        Check items against database for duplicates
        Modifies items in-place to set is_duplicate flag
        """
        # Collect all dedup keys by type
        service_keys = set()
        endpoint_keys = set()
        finding_keys = set()
        
        for item in items:
            if item.item_type == ItemType.SERVICE:
                service_keys.add(item.dedup_key)
            elif item.item_type == ItemType.ENDPOINT:
                endpoint_keys.add(item.dedup_key)
            elif item.item_type == ItemType.FINDING:
                finding_keys.add(item.dedup_key)
        
        # Check services against ReconData
        existing_services = set()
        if service_keys:
            # Query existing services for this assessment
            existing = self.db.query(ReconData).filter(
                and_(
                    ReconData.assessment_id == self.assessment_id,
                    ReconData.data_type == 'service'
                )
            ).all()
            
            for recon in existing:
                details = recon.details or {}
                host = details.get('host', '')
                port = details.get('port', '')
                protocol = details.get('protocol', 'tcp')
                key = f"{host}:{port}:{protocol}"
                existing_services.add(key)
        
        # Check endpoints against ReconData
        existing_endpoints = set()
        if endpoint_keys:
            existing = self.db.query(ReconData).filter(
                and_(
                    ReconData.assessment_id == self.assessment_id,
                    ReconData.data_type == 'endpoint'
                )
            ).all()
            
            for recon in existing:
                details = recon.details or {}
                host = details.get('host', '')
                path = details.get('path', '')
                key = f"ffuf:{host}:{path}"
                existing_endpoints.add(key)
        
        # Check findings against Cards
        existing_findings = set()
        if finding_keys:
            existing = self.db.query(Card).filter(
                and_(
                    Card.assessment_id == self.assessment_id,
                    Card.card_type == 'finding'
                )
            ).all()
            
            for card in existing:
                # Try to extract template_id from notes or technical_analysis
                notes = card.notes or ''
                if 'nuclei:' in notes:
                    # Extract key from notes
                    for line in notes.split('\n'):
                        if line.startswith('dedup_key:'):
                            existing_findings.add(line.split(':', 1)[1].strip())
        
        # Mark duplicates
        for item in items:
            if item.item_type == ItemType.SERVICE:
                item.is_duplicate = item.dedup_key in existing_services
            elif item.item_type == ItemType.ENDPOINT:
                item.is_duplicate = item.dedup_key in existing_endpoints
            elif item.item_type == ItemType.FINDING:
                item.is_duplicate = item.dedup_key in existing_findings
    
    def import_items(self, item_ids: List[str], all_items: Dict[str, List[Dict]]) -> Dict[str, int]:
        """
        Import selected items into the database
        
        Args:
            item_ids: List of item IDs to import (empty = import all non-duplicates)
            all_items: Grouped items from parse_files result
            
        Returns:
            Import statistics
        """
        stats = {
            "services": 0,
            "endpoints": 0,
            "findings": 0,
            "skipped_duplicates": 0
        }
        
        # Flatten all items
        all_flat = []
        for items_list in all_items.values():
            all_flat.extend(items_list)
        
        # Filter by selection
        if item_ids:
            selected_ids = set(item_ids)
            items_to_import = [i for i in all_flat if i["id"] in selected_ids]
        else:
            # Import all non-duplicates
            items_to_import = [i for i in all_flat if not i.get("is_duplicate", False)]
        
        # Import each item
        for item in items_to_import:
            if item.get("is_duplicate", False):
                stats["skipped_duplicates"] += 1
                continue
            
            item_type = item.get("item_type")
            
            if item_type == "service":
                self._import_service(item)
                stats["services"] += 1
            elif item_type == "endpoint":
                self._import_endpoint(item)
                stats["endpoints"] += 1
            elif item_type == "finding":
                self._import_finding(item)
                stats["findings"] += 1
        
        self.db.commit()
        return stats
    
    def _import_service(self, item: Dict) -> None:
        """Import a service as ReconData"""
        details = item.get("details", {})
        
        recon = ReconData(
            assessment_id=self.assessment_id,
            data_type='service',
            name=item.get("name", "Unknown Service"),
            details={
                **details,
                "source": item.get("source", "scan"),
                "source_file": item.get("source_file", ""),
                "imported_from": "scan_import"
            },
            discovered_in_phase="Phase 1 - Reconnaissance"
        )
        self.db.add(recon)
    
    def _import_endpoint(self, item: Dict) -> None:
        """Import an endpoint as ReconData"""
        details = item.get("details", {})
        
        recon = ReconData(
            assessment_id=self.assessment_id,
            data_type='endpoint',
            name=item.get("name", "Unknown Endpoint"),
            details={
                **details,
                "source": item.get("source", "scan"),
                "source_file": item.get("source_file", ""),
                "imported_from": "scan_import"
            },
            discovered_in_phase="Phase 2 - Enumeration"
        )
        self.db.add(recon)
    
    def _import_finding(self, item: Dict) -> None:
        """Import a finding as Card"""
        details = item.get("details", {})
        severity = item.get("severity", "INFO")
        
        # Build technical analysis
        tech_analysis = []
        if details.get("template_id"):
            tech_analysis.append(f"**Template:** {details['template_id']}")
        if details.get("matched_at"):
            tech_analysis.append(f"**Matched At:** {details['matched_at']}")
        if details.get("description"):
            tech_analysis.append(f"\n**Description:**\n{details['description']}")
        if details.get("curl_command"):
            tech_analysis.append(f"\n**Curl Command:**\n```\n{details['curl_command']}\n```")
        
        # Build tags string
        tags = details.get("tags", [])
        tags_str = ", ".join(tags) if tags else ""
        
        card = Card(
            assessment_id=self.assessment_id,
            card_type='finding',
            title=item.get("name", "Unknown Finding"),
            severity=severity,
            status='potential',  # Mark as potential since auto-imported
            target_service=details.get("host", ""),
            technical_analysis="\n".join(tech_analysis) if tech_analysis else None,
            notes=f"Auto-imported from {item.get('source', 'scan')} scan\n"
                  f"Source file: {item.get('source_file', '')}\n"
                  f"Tags: {tags_str}\n"
                  f"dedup_key:{item.get('dedup_key', '')}"
        )
        self.db.add(card)
        
        # Also create ReconData entry for the vulnerability
        recon = ReconData(
            assessment_id=self.assessment_id,
            data_type='vulnerability',
            name=item.get("name", "Unknown Vulnerability"),
            details={
                **details,
                "source": item.get("source", "scan"),
                "source_file": item.get("source_file", ""),
                "severity": severity,
                "imported_from": "scan_import"
            },
            discovered_in_phase="Phase 3 - Vulnerability Assessment"
        )
        self.db.add(recon)
