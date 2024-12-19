from typing import Dict, Optional
import requests
import time
from flask import current_app

class TranscriptFetcher:
    def __init__(self, assembly: str):
        self.base_url = "https://rest.ensembl.org" if assembly == 'GRCh38' else "https://grch37.rest.ensembl.org"
        self.assembly = assembly

    def _make_ensembl_request(self, endpoint: str) -> Optional[Dict]:
        headers = {"Content-Type": "application/json"}
        url = f"{self.base_url}/{endpoint}"
        
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == 2:
                    current_app.logger.error(f"Failed to fetch data from Ensembl: {e}")
                    return None
                time.sleep(2 ** attempt)
        return None

    def fetch_gene_symbol(self, transcript_id: str) -> Optional[str]:
        """Lightweight method to only fetch gene symbol for a transcript."""
        if transcript_id.startswith(('NM_', 'NR_')):
            ensembl_id = self._get_refseq_to_ensembl_mapping(transcript_id)
            if not ensembl_id:
                return None
        else:
            ensembl_id = transcript_id

        # Get minimal transcript information
        endpoint = f"lookup/id/{ensembl_id}"
        transcript_data = self._make_ensembl_request(endpoint)
        if not transcript_data:
            return None

        # Get gene information to get the gene symbol
        gene_id = transcript_data.get('Parent')
        gene_data = self._get_gene_info(gene_id) if gene_id else None
        return gene_data.get('display_name') if gene_data else transcript_data.get('display_name', '').split('-')[0]

    def _get_refseq_to_ensembl_mapping(self, refseq_id: str) -> Optional[str]:
        """Get the Ensembl transcript ID for a RefSeq ID."""
        # First try direct lookup
        endpoint = f"match/symbol/homo_sapiens/{refseq_id}?content-type=application/json"
        data = self._make_ensembl_request(endpoint)
        
        if data:
            # Look for transcript matches
            for match in data:
                if match.get('biotype') == 'transcript':
                    return match['id']

        # If direct lookup fails, try using the xrefs endpoint
        base_id = refseq_id.split('.')[0]
        endpoint = f"xrefs/symbol/homo_sapiens/{base_id}?external_db=RefSeq_mRNA"
        data = self._make_ensembl_request(endpoint)

        if data:
            for item in data:
                if 'id' in item and item.get('type') == 'transcript':
                    return item['id']

        return None

    def _get_gene_info(self, gene_id: str) -> Optional[Dict]:
        """Get gene information from Ensembl."""
        endpoint = f"lookup/id/{gene_id}?expand=1"
        return self._make_ensembl_request(endpoint) 