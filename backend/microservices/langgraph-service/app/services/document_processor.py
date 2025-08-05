"""
Document Processor Service - Extract and process text from various document formats
"""
import io
import base64
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger
import PyPDF2
import docx
import openpyxl
import csv
import json
from PIL import Image
import pytesseract
import re
from datetime import datetime


class DocumentProcessor:
    """Process various document formats and extract text content"""
    
    SUPPORTED_FORMATS = {
        'application/pdf': 'pdf',
        'text/plain': 'txt',
        'text/csv': 'csv',
        'application/json': 'json',
        'application/msword': 'doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'application/vnd.ms-excel': 'xls',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
        'image/png': 'png',
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/gif': 'gif',
        'image/bmp': 'bmp'
    }
    
    @classmethod
    async def extract_text(
        cls,
        content: bytes,
        content_type: str,
        filename: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Extract text from document content"""
        
        format_type = cls.SUPPORTED_FORMATS.get(content_type)
        
        if not format_type:
            # Try to infer from filename
            if filename:
                ext = filename.split('.')[-1].lower()
                format_type = ext
        
        metadata = {
            'content_type': content_type,
            'format': format_type,
            'filename': filename,
            'size_bytes': len(content),
            'extraction_timestamp': datetime.now().isoformat()
        }
        
        try:
            if format_type == 'pdf':
                text, pdf_metadata = cls._extract_pdf(content)
                metadata.update(pdf_metadata)
            elif format_type == 'txt':
                text = content.decode('utf-8', errors='ignore')
                metadata['encoding'] = 'utf-8'
            elif format_type == 'docx':
                text, docx_metadata = cls._extract_docx(content)
                metadata.update(docx_metadata)
            elif format_type in ['csv', 'xls', 'xlsx']:
                text, table_metadata = cls._extract_spreadsheet(content, format_type)
                metadata.update(table_metadata)
            elif format_type == 'json':
                text, json_metadata = cls._extract_json(content)
                metadata.update(json_metadata)
            elif format_type in ['png', 'jpg', 'jpeg', 'gif', 'bmp']:
                text, image_metadata = cls._extract_image_text(content, format_type)
                metadata.update(image_metadata)
            else:
                # Fallback to plain text
                text = content.decode('utf-8', errors='ignore')
                metadata['extraction_method'] = 'fallback_text'
            
            # Clean and normalize text
            text = cls._normalize_text(text)
            
            # Extract additional metadata
            metadata['word_count'] = len(text.split())
            metadata['char_count'] = len(text)
            metadata['line_count'] = len(text.splitlines())
            
            return text, metadata
            
        except Exception as e:
            logger.error(f"Failed to extract text from {format_type}: {e}")
            raise
    
    @staticmethod
    def _extract_pdf(content: bytes) -> Tuple[str, Dict[str, Any]]:
        """Extract text from PDF"""
        pdf_file = io.BytesIO(content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text_parts = []
        metadata = {
            'page_count': len(pdf_reader.pages),
            'pdf_metadata': {}
        }
        
        # Extract PDF metadata
        if pdf_reader.metadata:
            for key, value in pdf_reader.metadata.items():
                metadata['pdf_metadata'][key] = str(value)
        
        # Extract text from each page
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
        
        return '\n\n'.join(text_parts), metadata
    
    @staticmethod
    def _extract_docx(content: bytes) -> Tuple[str, Dict[str, Any]]:
        """Extract text from DOCX"""
        docx_file = io.BytesIO(content)
        doc = docx.Document(docx_file)
        
        text_parts = []
        metadata = {
            'paragraph_count': len(doc.paragraphs),
            'table_count': len(doc.tables)
        }
        
        # Extract paragraphs
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        
        # Extract tables
        for table_idx, table in enumerate(doc.tables):
            table_text = f"\n--- Table {table_idx + 1} ---\n"
            for row in table.rows:
                row_text = ' | '.join(cell.text.strip() for cell in row.cells)
                table_text += row_text + '\n'
            text_parts.append(table_text)
        
        # Extract document properties
        if doc.core_properties:
            metadata['document_properties'] = {
                'author': doc.core_properties.author,
                'title': doc.core_properties.title,
                'subject': doc.core_properties.subject,
                'keywords': doc.core_properties.keywords,
                'created': str(doc.core_properties.created) if doc.core_properties.created else None,
                'modified': str(doc.core_properties.modified) if doc.core_properties.modified else None
            }
        
        return '\n\n'.join(text_parts), metadata
    
    @staticmethod
    def _extract_spreadsheet(content: bytes, format_type: str) -> Tuple[str, Dict[str, Any]]:
        """Extract text from spreadsheet formats"""
        
        if format_type == 'csv':
            text = content.decode('utf-8', errors='ignore')
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            
            metadata = {
                'row_count': len(rows),
                'column_count': max(len(row) for row in rows) if rows else 0
            }
            
            # Format as text table
            text_parts = []
            for row in rows:
                text_parts.append(' | '.join(str(cell) for cell in row))
            
            return '\n'.join(text_parts), metadata
        
        else:  # Excel formats
            excel_file = io.BytesIO(content)
            workbook = openpyxl.load_workbook(excel_file, read_only=True)
            
            text_parts = []
            metadata = {
                'sheet_count': len(workbook.sheetnames),
                'sheets': {}
            }
            
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                sheet_text = f"--- Sheet: {sheet_name} ---\n"
                
                row_count = 0
                for row in sheet.iter_rows(values_only=True):
                    if any(cell is not None for cell in row):
                        row_text = ' | '.join(str(cell) if cell is not None else '' for cell in row)
                        sheet_text += row_text + '\n'
                        row_count += 1
                
                text_parts.append(sheet_text)
                metadata['sheets'][sheet_name] = {'row_count': row_count}
            
            return '\n\n'.join(text_parts), metadata
    
    @staticmethod
    def _extract_json(content: bytes) -> Tuple[str, Dict[str, Any]]:
        """Extract text from JSON"""
        try:
            data = json.loads(content.decode('utf-8'))
            
            # Pretty print the JSON
            text = json.dumps(data, indent=2, ensure_ascii=False)
            
            metadata = {
                'json_type': type(data).__name__,
                'keys_count': len(data) if isinstance(data, dict) else None,
                'items_count': len(data) if isinstance(data, list) else None
            }
            
            return text, metadata
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            # Return raw text if JSON parsing fails
            return content.decode('utf-8', errors='ignore'), {'json_error': str(e)}
    
    @staticmethod
    def _extract_image_text(content: bytes, format_type: str) -> Tuple[str, Dict[str, Any]]:
        """Extract text from images using OCR"""
        try:
            image = Image.open(io.BytesIO(content))
            
            metadata = {
                'image_format': format_type,
                'image_size': image.size,
                'image_mode': image.mode
            }
            
            # Perform OCR
            text = pytesseract.image_to_string(image)
            
            if not text.strip():
                text = "[No text detected in image]"
                metadata['ocr_success'] = False
            else:
                metadata['ocr_success'] = True
                metadata['detected_languages'] = pytesseract.image_to_data(
                    image, output_type=pytesseract.Output.DICT
                ).get('lang', [])
            
            return text, metadata
            
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return "[OCR extraction failed]", {'ocr_error': str(e)}
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize and clean extracted text"""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove null characters
        text = text.replace('\x00', '')
        
        # Normalize line breaks
        text = re.sub(r'\r\n|\r', '\n', text)
        
        # Remove excessive line breaks
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Trim
        text = text.strip()
        
        return text
    
    @classmethod
    def chunk_text(
        cls,
        text: str,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Split text into chunks for processing"""
        
        chunks = []
        text_length = len(text)
        
        if text_length <= chunk_size:
            # Single chunk
            chunks.append({
                'content': text,
                'chunk_id': 'chunk_0',
                'position': 0,
                'metadata': {
                    'chunk_index': 0,
                    'total_chunks': 1,
                    'start_char': 0,
                    'end_char': text_length,
                    **(metadata or {})
                }
            })
            return chunks
        
        # Split into overlapping chunks
        start = 0
        chunk_index = 0
        
        while start < text_length:
            end = min(start + chunk_size, text_length)
            
            # Try to break at sentence boundaries
            if end < text_length:
                # Look for sentence end
                sentence_end = text.rfind('. ', start, end)
                if sentence_end > start:
                    end = sentence_end + 1
            
            chunk_text = text[start:end]
            
            chunks.append({
                'content': chunk_text,
                'chunk_id': f'chunk_{chunk_index}',
                'position': chunk_index,
                'metadata': {
                    'chunk_index': chunk_index,
                    'start_char': start,
                    'end_char': end,
                    'chunk_size': len(chunk_text),
                    **(metadata or {})
                }
            })
            
            # Move start position with overlap
            start = end - chunk_overlap
            chunk_index += 1
        
        # Update total chunks count
        for chunk in chunks:
            chunk['metadata']['total_chunks'] = len(chunks)
        
        return chunks