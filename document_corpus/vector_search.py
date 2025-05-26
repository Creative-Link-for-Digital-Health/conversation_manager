"""
Vector Search Library for RAG Implementation
Supports multiple vector database backends and document processing
"""

import os
import hashlib
import json
import uuid
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
import logging

# Document processing with docling
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

from openai import OpenAI

# Vector stores
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    import faiss
    import numpy as np
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

class DocumentProcessor:
    """Handle document ingestion and text extraction using docling"""
    
    SUPPORTED_EXTENSIONS = {'.txt', '.md', '.pdf', '.docx', '.pptx', '.html', '.xml', '.json'}
    
    def __init__(self):
        if not DOCLING_AVAILABLE:
            raise ImportError("Docling not available. Install with: pip install docling")
        
        # Initialize docling converter with optimized settings
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True  # Enable OCR for scanned documents
        pipeline_options.do_table_structure = True  # Extract table structure
        pipeline_options.table_structure_options.do_cell_matching = True
        
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
    
    def extract_text(self, file_path: Path) -> Dict[str, Any]:
        """Extract text and metadata from various file formats using docling"""
        try:
            # Convert document
            result = self.converter.convert(str(file_path))
            
            # Extract main text content
            main_text = result.document.export_to_markdown()
            
            # Extract metadata
            metadata = {
                'filename': file_path.name,
                'file_path': str(file_path),
                'file_size': file_path.stat().st_size,
                'file_extension': file_path.suffix.lower(),
                'processed_at': datetime.now().isoformat(),
                'page_count': getattr(result.document, 'page_count', 1),
                'char_count': len(main_text),
                'word_count': len(main_text.split()),
            }
            
            # Extract additional structured data if available
            structured_data = {
                'tables': [],
                'headings': [],
                'images': []
            }
            
            # Extract tables
            for table in result.document.tables:
                if hasattr(table, 'export_to_dataframe'):
                    try:
                        df = table.export_to_dataframe()
                        structured_data['tables'].append({
                            'content': df.to_string(),
                            'rows': len(df),
                            'columns': len(df.columns)
                        })
                    except:
                        pass
            
            # Extract headings/sections
            for item in result.document.texts:
                if hasattr(item, 'label') and 'heading' in str(item.label).lower():
                    structured_data['headings'].append({
                        'text': item.text,
                        'level': getattr(item, 'level', 1)
                    })
            
            return {
                'text': main_text,
                'metadata': metadata,
                'structured_data': structured_data,
                'success': True
            }
            
        except Exception as e:
            logging.error(f"Error extracting text from {file_path}: {e}")
            return {
                'text': "",
                'metadata': {
                    'filename': file_path.name,
                    'file_path': str(file_path),
                    'error': str(e)
                },
                'structured_data': {},
                'success': False
            }
    
    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict[str, Any]]:
        """Split text into overlapping chunks with improved boundary detection"""
        if len(text) <= chunk_size:
            return [{'text': text, 'start': 0, 'end': len(text), 'chunk_id': 0}]
        
        chunks = []
        start = 0
        chunk_id = 0
        
        # Split by paragraphs first for better coherence
        paragraphs = text.split('\n\n')
        current_chunk = ""
        current_start = 0
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed chunk size
            if len(current_chunk) + len(paragraph) > chunk_size and current_chunk:
                # Save current chunk
                chunks.append({
                    'text': current_chunk.strip(),
                    'start': current_start,
                    'end': current_start + len(current_chunk),
                    'chunk_id': chunk_id,
                    'word_count': len(current_chunk.split()),
                    'paragraph_count': current_chunk.count('\n\n') + 1
                })
                
                # Start new chunk with overlap
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_text + '\n\n' + paragraph
                current_start = current_start + len(current_chunk) - len(overlap_text) - len(paragraph) - 2
                chunk_id += 1
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += '\n\n' + paragraph
                else:
                    current_chunk = paragraph
                    current_start = start
        
        # Add final chunk if it has content
        if current_chunk.strip():
            chunks.append({
                'text': current_chunk.strip(),
                'start': current_start,
                'end': current_start + len(current_chunk),
                'chunk_id': chunk_id,
                'word_count': len(current_chunk.split()),
                'paragraph_count': current_chunk.count('\n\n') + 1
            })
        
        return chunks
    
    def process_document(self, file_path: Path, chunk_size: int = 1000, overlap: int = 200) -> Dict[str, Any]:
        """Complete document processing pipeline"""
        # Extract text and metadata
        extraction_result = self.extract_text(file_path)
        
        if not extraction_result['success']:
            return extraction_result
        
        # Create chunks
        chunks = self.chunk_text(
            extraction_result['text'],
            chunk_size=chunk_size,
            overlap=overlap
        )
        
        # Generate document ID
        content_hash = hashlib.md5(extraction_result['text'].encode()).hexdigest()
        document_id = f"{file_path.stem}_{content_hash[:8]}"
        
        return {
            'document_id': document_id,
            'text': extraction_result['text'],
            'chunks': chunks,
            'metadata': extraction_result['metadata'],
            'structured_data': extraction_result['structured_data'],
            'success': True,
            'processing_stats': {
                'total_chunks': len(chunks),
                'avg_chunk_size': sum(len(chunk['text']) for chunk in chunks) / len(chunks) if chunks else 0,
                'total_words': sum(chunk['word_count'] for chunk in chunks),
                'extraction_method': 'docling'
            }
        }

class VectorSearchProvider:
    """Base class for vector search providers"""
    
    def __init__(self, config: Dict[str, Any], openai_client: OpenAI):
        self.config = config
        self.openai_client = openai_client
        self.embedding_model = config.get('embedding_model', 'text-embedding-ada-002')
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings from OpenAI"""
        try:
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logging.error(f"Error getting embeddings: {e}")
            raise
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """Add documents to the vector store"""
        raise NotImplementedError
    
    def search(self, query: str, k: int = 3, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search for similar documents"""
        raise NotImplementedError
    
    def clear_collection(self) -> bool:
        """Clear all documents from the collection"""
        raise NotImplementedError

class ChromaProvider(VectorSearchProvider):
    """ChromaDB vector search provider"""
    
    def __init__(self, config: Dict[str, Any], openai_client: OpenAI):
        if not CHROMA_AVAILABLE:
            raise ImportError("ChromaDB not available. Install with: pip install chromadb")
        
        super().__init__(config, openai_client)
        
        # Initialize Chroma client
        self.client = chromadb.PersistentClient(
            path="./chroma_db",
            settings=Settings(anonymized_telemetry=False)
        )
        
        collection_name = config.get('collection_name', 'research_docs')
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Research documents for RAG"}
        )
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """Add documents to ChromaDB"""
        try:
            texts = [doc['content'] for doc in documents]
            embeddings = self.get_embeddings(texts)
            
            ids = [doc['id'] for doc in documents]
            metadatas = [doc['metadata'] for doc in documents]
            
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )
            return True
            
        except Exception as e:
            logging.error(f"Error adding documents to Chroma: {e}")
            return False
    
    def search(self, query: str, k: int = 3, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search ChromaDB for similar documents"""
        try:
            query_embedding = self.get_embeddings([query])[0]
            
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=k
            )
            
            search_results = []
            if results['ids'] and results['ids'][0]:
                for i, doc_id in enumerate(results['ids'][0]):
                    distance = results['distances'][0][i] if results['distances'] else 0
                    similarity = 1 - distance  # Convert distance to similarity
                    
                    if similarity >= threshold:
                        search_results.append({
                            'id': doc_id,
                            'content': results['documents'][0][i],
                            'metadata': results['metadatas'][0][i],
                            'similarity_score': similarity,
                            'distance': distance
                        })
            
            return search_results
            
        except Exception as e:
            logging.error(f"Error searching Chroma: {e}")
            return []
    
    def clear_collection(self) -> bool:
        """Clear ChromaDB collection"""
        try:
            self.client.delete_collection(self.collection.name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection.name,
                metadata={"description": "Research documents for RAG"}
            )
            return True
        except Exception as e:
            logging.error(f"Error clearing Chroma collection: {e}")
            return False

class SimpleInMemoryProvider(VectorSearchProvider):
    """Simple in-memory vector search using cosine similarity"""
    
    def __init__(self, config: Dict[str, Any], openai_client: OpenAI):
        super().__init__(config, openai_client)
        self.documents = []
        self.embeddings = []
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """Add documents to in-memory store"""
        try:
            texts = [doc['content'] for doc in documents]
            embeddings = self.get_embeddings(texts)
            
            for doc, embedding in zip(documents, embeddings):
                self.documents.append(doc)
                self.embeddings.append(embedding)
            
            return True
            
        except Exception as e:
            logging.error(f"Error adding documents to in-memory store: {e}")
            return False
    
    def search(self, query: str, k: int = 3, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search using cosine similarity"""
        try:
            if not self.documents:
                return []
            
            query_embedding = self.get_embeddings([query])[0]
            
            # Calculate cosine similarities
            similarities = []
            for i, doc_embedding in enumerate(self.embeddings):
                similarity = self._cosine_similarity(query_embedding, doc_embedding)
                similarities.append((i, similarity))
            
            # Sort by similarity and filter by threshold
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            results = []
            for i, similarity in similarities[:k]:
                if similarity >= threshold:
                    doc = self.documents[i].copy()
                    doc['similarity_score'] = similarity
                    results.append(doc)
            
            return results
            
        except Exception as e:
            logging.error(f"Error searching in-memory store: {e}")
            return []
    
    def clear_collection(self) -> bool:
        """Clear in-memory store"""
        self.documents = []
        self.embeddings = []
        return True
    
    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        import math
        
        dot_product = sum(ai * bi for ai, bi in zip(a, b))
        magnitude_a = math.sqrt(sum(ai * ai for ai in a))
        magnitude_b = math.sqrt(sum(bi * bi for bi in b))
        
        if magnitude_a == 0 or magnitude_b == 0:
            return 0
        
        return dot_product / (magnitude_a * magnitude_b)

class VectorSearchManager:
    """Main interface for vector search operations"""
    
    def __init__(self, config: Dict[str, Any], openai_client: OpenAI):
        self.config = config
        self.openai_client = openai_client
        self.provider = self._initialize_provider()
        self.document_processor = DocumentProcessor()
        
    def _initialize_provider(self) -> VectorSearchProvider:
        """Initialize the configured vector search provider"""
        provider_name = self.config.get('provider', 'simple')
        
        if provider_name == 'chroma':
            return ChromaProvider(self.config, self.openai_client)
        elif provider_name == 'simple':
            return SimpleInMemoryProvider(self.config, self.openai_client)
        else:
            raise ValueError(f"Unknown vector search provider: {provider_name}")
    
    def ingest_documents(self, documents_path: str) -> Dict[str, Any]:
        """Ingest documents from a directory using docling"""
        documents_path = Path(documents_path)
        if not documents_path.exists():
            return {'success': False, 'error': f'Path does not exist: {documents_path}'}
        
        processed_docs = []
        errors = []
        processing_stats = {
            'total_files': 0,
            'successful_files': 0,
            'failed_files': 0,
            'total_chunks': 0,
            'total_words': 0,
            'file_types': {}
        }
        
        # Get allowed extensions from config
        allowed_extensions = set(self.config.get('allowed_extensions', ['.txt', '.md', '.pdf', '.docx', '.pptx']))
        recursive = self.config.get('recursive_scan', True)
        
        # Find files
        pattern = "**/*" if recursive else "*"
        files = documents_path.glob(pattern)
        
        for file_path in files:
            if file_path.is_file() and file_path.suffix.lower() in allowed_extensions:
                processing_stats['total_files'] += 1
                file_ext = file_path.suffix.lower()
                processing_stats['file_types'][file_ext] = processing_stats['file_types'].get(file_ext, 0) + 1
                
                try:
                    # Process document with docling
                    doc_result = self.document_processor.process_document(
                        file_path,
                        chunk_size=self.config.get('chunk_size', 1000),
                        overlap=self.config.get('chunk_overlap', 200)
                    )
                    
                    if not doc_result['success']:
                        errors.append({
                            'file': str(file_path),
                            'error': doc_result['metadata'].get('error', 'Unknown processing error')
                        })
                        processing_stats['failed_files'] += 1
                        continue
                    
                    # Create document records for each chunk
                    for chunk in doc_result['chunks']:
                        doc_id = f"{doc_result['document_id']}_chunk_{chunk['chunk_id']}"
                        
                        # Enhanced metadata with docling features
                        chunk_metadata = {
                            'document_id': doc_result['document_id'],
                            'source_file': str(file_path),
                            'filename': file_path.name,
                            'chunk_index': chunk['chunk_id'],
                            'chunk_start': chunk['start'],
                            'chunk_end': chunk['end'],
                            'word_count': chunk['word_count'],
                            'paragraph_count': chunk.get('paragraph_count', 1),
                            'file_size': doc_result['metadata']['file_size'],
                            'page_count': doc_result['metadata'].get('page_count', 1),
                            'ingested_at': datetime.now().isoformat(),
                            'file_extension': file_path.suffix.lower(),
                            'extraction_method': 'docling',
                            'char_count': len(chunk['text']),
                            # Add structured data context
                            'has_tables': len(doc_result['structured_data'].get('tables', [])) > 0,
                            'table_count': len(doc_result['structured_data'].get('tables', [])),
                            'heading_count': len(doc_result['structured_data'].get('headings', []))
                        }
                        
                        processed_docs.append({
                            'id': doc_id,
                            'content': chunk['text'],
                            'metadata': chunk_metadata
                        })
                    
                    processing_stats['successful_files'] += 1
                    processing_stats['total_chunks'] += len(doc_result['chunks'])
                    processing_stats['total_words'] += doc_result['processing_stats']['total_words']
                    
                except Exception as e:
                    errors.append({'file': str(file_path), 'error': str(e)})
                    processing_stats['failed_files'] += 1
        
        # Add documents to vector store
        if processed_docs:
            success = self.provider.add_documents(processed_docs)
            if not success:
                return {'success': False, 'error': 'Failed to add documents to vector store'}
        
        return {
            'success': True,
            'documents_processed': len(processed_docs),
            'files_processed': processing_stats['successful_files'],
            'files_failed': processing_stats['failed_files'],
            'total_files_found': processing_stats['total_files'],
            'total_chunks_created': processing_stats['total_chunks'],
            'total_words_processed': processing_stats['total_words'],
            'file_types_processed': processing_stats['file_types'],
            'errors': errors,
            'processing_method': 'docling'
        }
    
    def search(self, query: str, conversation_context: List[str] = None) -> Dict[str, Any]:
        """Search for relevant documents"""
        try:
            # Enhance query with conversation context if provided
            enhanced_query = query
            if conversation_context:
                # Use last few messages for context
                recent_context = conversation_context[-3:] if len(conversation_context) > 3 else conversation_context
                context_text = " ".join(recent_context)
                enhanced_query = f"{context_text} {query}"
            
            # Perform search
            k = self.config.get('retrieval_k', 3)
            threshold = self.config.get('similarity_threshold', 0.7)
            
            results = self.provider.search(enhanced_query, k=k, threshold=threshold)
            
            # Calculate total context length
            total_length = sum(len(result['content']) for result in results)
            max_length = self.config.get('max_context_length', 4000)
            
            # Truncate if necessary
            if total_length > max_length:
                cumulative_length = 0
                truncated_results = []
                
                for result in results:
                    if cumulative_length + len(result['content']) <= max_length:
                        truncated_results.append(result)
                        cumulative_length += len(result['content'])
                    else:
                        # Add partial content if it fits
                        remaining_space = max_length - cumulative_length
                        if remaining_space > 100:  # Only if meaningful space left
                            truncated_content = result['content'][:remaining_space] + "..."
                            result['content'] = truncated_content
                            truncated_results.append(result)
                        break
                
                results = truncated_results
            
            return {
                'success': True,
                'results': results,
                'query': query,
                'enhanced_query': enhanced_query,
                'total_results': len(results),
                'context_length': sum(len(result['content']) for result in results),
                'search_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logging.error(f"Error in vector search: {e}")
            return {
                'success': False,
                'error': str(e),
                'query': query,
                'search_timestamp': datetime.now().isoformat()
            }
    
    def clear_documents(self) -> bool:
        """Clear all documents from the vector store"""
        return self.provider.clear_collection()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store"""
        if hasattr(self.provider, 'collection'):
            # For ChromaDB
            try:
                count = self.provider.collection.count()
                return {
                    'provider': self.config.get('provider'),
                    'document_count': count,
                    'collection_name': self.config.get('collection_name')
                }
            except:
                pass
        elif hasattr(self.provider, 'documents'):
            # For in-memory provider
            return {
                'provider': self.config.get('provider'),
                'document_count': len(self.provider.documents),
                'collection_name': self.config.get('collection_name')
            }
        
        return {
            'provider': self.config.get('provider'),
            'document_count': 'unknown',
            'collection_name': self.config.get('collection_name')
        }