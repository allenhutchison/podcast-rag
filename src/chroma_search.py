import json
import logging
from typing import Dict, List, Tuple
import chromadb
from nltk.tokenize import sent_tokenize

from src.config import Config


class VectorDbSearchManager:
    def __init__(self, config: Config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        logging.debug(f"Connecting to Chroma DB at {config.CHROMA_DB_HOST}:{config.CHROMA_DB_PORT}")
        self.client = chromadb.HttpClient(host=config.CHROMA_DB_HOST, port=config.CHROMA_DB_PORT, ssl=True)
        self.collection = self.client.get_collection(config.CHROMA_DB_COLLECTION)

    def pretty_print_chromadb_results(self, results):
        """
        Pretty print the ChromaDB search results.
        
        Args:
            results (list or dict): The search results from ChromaDB.
        """
        logging.debug(json.dumps(results, indent=4, sort_keys=True))

    def combine_overlapping_chunks(self, documents: List[str], metadatas: List[Dict]) -> Tuple[List[str], List[Dict]]:
        """
        Combine overlapping chunks from the same episode into single chunks.
        
        Args:
            documents: List of document chunks
            metadatas: List of metadata dictionaries
            
        Returns:
            Tuple of (combined documents, combined metadatas)
        """
        if not documents:
            return [], []
            
        # Group chunks by podcast and episode
        episode_chunks: Dict[str, List[Tuple[str, Dict]]] = {}
        for doc, meta in zip(documents, metadatas):
            key = f"{meta.get('podcast', '')}_{meta.get('episode', '')}"
            if key not in episode_chunks:
                episode_chunks[key] = []
            episode_chunks[key].append((doc, meta))
        
        combined_docs = []
        combined_metas = []
        
        # Process each episode's chunks
        for chunks in episode_chunks.values():
            if not chunks:
                continue
                
            current_text = chunks[0][0]
            current_meta = chunks[0][1].copy()
            
            for next_text, next_meta in chunks[1:]:
                # Simple overlap detection - if the end of current chunk shares content with start of next
                overlap_size = 0
                min_overlap = 50  # Minimum characters to consider as overlap
                
                for i in range(min(len(current_text), len(next_text))):
                    if current_text[-i:] in next_text[:i+min_overlap]:
                        overlap_size = i
                        break
                
                if overlap_size > min_overlap:
                    # Combine the chunks, removing the overlapping portion
                    current_text = current_text[:-overlap_size] + next_text
                else:
                    # If no significant overlap found, add a space and concatenate
                    current_text = current_text + " " + next_text
                
                # Update metadata to show it's a combined chunk
                current_meta['combined'] = True
                
            combined_docs.append(current_text)
            combined_metas.append(current_meta)
            
        return combined_docs, combined_metas

    def search_transcriptions(self, query, print_results=True):
        # Query the collection using the query embeddings
        results = self.collection.query(
            query_texts=[query],  
            n_results=10  # Number of relevant chunks to return
        )
        
        # Combine overlapping chunks
        combined_docs, combined_metas = self.combine_overlapping_chunks(
            results['documents'][0], 
            results['metadatas'][0]
        )
        
        # Update results with combined chunks
        results['documents'] = [combined_docs]
        results['metadatas'] = [combined_metas]
        
        self.pretty_print_chromadb_results(results)
        
        if print_results:
            for document_list, metadata_list in zip(results['documents'], results['metadatas']):
                for document, metadata in zip(document_list, metadata_list):
                    podcast = metadata.get('podcast', 'Unknown Podcast')
                    episode = metadata.get('episode', 'Unknown Episode')
                    is_combined = metadata.get('combined', False)
                    transcription = document.strip()
                    combined_status = " (Combined Chunks)" if is_combined else ""
                    print(f"Relevant Episode: {podcast} Episode: {episode}{combined_status}\nTranscription Snippet: {transcription[:200]}...\n")
        
        return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Podcast Transcript Search with Chroma")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    parser.add_argument("-l", "--log-level", help="Set log level (DEBUG, INFO, WARNING, ERROR)", default="INFO")
    parser.add_argument("-q", "--query", help="Query to search", required=True)
    args = parser.parse_args()

    # Configure logging based on command-line argument
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),  # Default to INFO if invalid log level
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    config = Config(env_file=args.env_file)
    manager = VectorDbSearchManager(config)
    manager.search_transcriptions(args.query, print_results=True)
    

if __name__ == "__main__":
    main()
