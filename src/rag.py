import logging
import sys
import json

import google.generativeai as genai
from ollama import Client

from argparse_shared import (add_ai_system_argument, add_dry_run_argument,
                             add_log_level_argument, add_query_argument,
                             get_base_parser)
from chroma_search import VectorDbSearchManager
from config import Config
from prompt_manager import PromptManager


class RagManager:
    def __init__(self, config: Config, dry_run=False, print_results=True, ai_system="ollama"):
        self.config = config
        self.dry_run = dry_run
        self.print_results = print_results
        self.ai_system = ai_system
        self.prompt_manager = PromptManager(config=config, print_results=print_results)
        self.vector_db_manager = VectorDbSearchManager(config=config, dry_run=dry_run)
        self.last_query = None
        self.last_vector_db_results = None
        if self.ai_system == "ollama":
            logging.info("Using Ollama for AI system.")
            self.ollama_client = Client(host=config.OLLAMA_HOST)
        elif self.ai_system == "gemini":
            logging.info("Using Gemini for AI system.")
            genai.configure(api_key=self.config.GEMINI_API_KEY)
            self.gemini_client = genai.GenerativeModel(model_name=self.config.GEMINI_MODEL)

    def search_vector_db(self, query):
        results = self.vector_db_manager.search_transcriptions(query, print_results=False)
        return results
    
    def prepare_model_context(self, query):
        vector_db_results = self.search_vector_db(query)
        self.last_vector_db_results = vector_db_results
        document_results = vector_db_results['documents']
        metadata_results = vector_db_results['metadatas']
        return document_results, metadata_results


    def query(self, query):
        self.last_query = query
        refined_query = self.refine_query(query)
        document_results, metadata_results = self.prepare_model_context(refined_query)
        prompt = self.format_prompt(refined_query, document_results, metadata_results)
        self.last_context = "Some transcript text..."
        logging.info(f"Query called with: {query}")
        if self.ai_system == "ollama":
            return self.query_with_ollama(prompt)
        elif self.ai_system == "gemini":
            return self.query_with_gemini(prompt)
        

    
    def query_with_gemini(self, prompt):
        results = self.gemini_client.generate_content(prompt)
        if self.print_results:
            logging.info("Gemini Response: %s", results)
        return results

    def query_with_ollama(self, prompt):
        results = self.ollama_client.chat(model=self.config.OLLAMA_MODEL,
                                    messages=[{"role": "user", "content": prompt}],
                                    options={"num_ctx": 8192})
        if self.print_results:
            logging.info("Ollama Response: %s", results)
        return results

    def refine_query(self, query):
        # Implement logic to refine the query if necessary
        return query

    def format_prompt(self, query, document_results, metadata_results):
        context_documents = ''
        iteration = 1
        for document_list, metadata_list in zip(document_results, metadata_results):
            for document, metadata in zip(document_list, metadata_list):
                snippet = self.prompt_manager.build_prompt(
                    prompt_name = "podcast_snippet",
                    iteration = iteration,
                    podcast = metadata.get('podcast', 'Unknown Podcast'),
                    episode = metadata.get('episode', 'Unknown Episode'),
                    release_date = metadata.get('release_date', 'Unknown Date'),
                    hosts = metadata.get('hosts', 'Unknown Host(s)'),
                    guests = metadata.get('guests', 'Unknown Guest(s)'),
                    transcript = document.strip(),
                    keywords = metadata.get('keywords', ''),
                    timestamp = metadata.get('timestamp', '')
                )
                context_documents += snippet
                iteration += 1
    
        prompt = self.prompt_manager.build_prompt(
            prompt_name = "archive_question",
            context = context_documents,
            query = query
        )
        if self.print_results:
            logging.info("Prompt Prepared: %s", prompt)
            logging.info("Prompt Size: %s", sys.getsizeof(prompt))
        return prompt

    def search_snippets(self, query: str):
        logging.info(f"Searching snippets for: {query}")
        if query != self.last_query:
            logging.info("Note: Query differs from last query stored.")

        if not self.last_vector_db_results:
            return json.dumps([])

        document_results = self.last_vector_db_results['documents']
        metadata_results = self.last_vector_db_results['metadatas']
        final_snippets = []
        for document_list, metadata_list in zip(document_results, metadata_results):
            for document, metadata in zip(document_list, metadata_list):
                snippet = {
                    "text": document.strip(),
                    "source": metadata.get("source", ""),
                    "episode": metadata.get("episode", "")
                }
                final_snippets.append(snippet)
                
        return json.dumps(final_snippets, indent=2)


if __name__ == "__main__":
    import argparse
    parser = get_base_parser()
    parser.description = "Search podcast transcriptions using Ollama or Gemini"

    add_dry_run_argument(parser)
    add_log_level_argument(parser)
    add_ai_system_argument(parser)
    add_query_argument(parser)
    
    args = parser.parse_args()

    # Configure logging based on command-line argument
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), "INFO"),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    config = Config(env_file=args.env_file)
    rag_manager = RagManager(config=config, print_results=True, ai_system=args.ai_system)
    rag_manager.query(args.query)