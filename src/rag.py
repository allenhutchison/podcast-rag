import os
import logging
from config import Config
from chroma_search import VectorDbSearchManager
from ollama import Client
from string import Template
import textwrap
import sys
import google.generativeai as genai




class RagManager:
    def __init__(self, config: Config, dry_run=False, print_results=True, ai_system="ollama"):
        self.config = config
        self.dry_run = dry_run
        self.print_results = print_results
        self.ai_system = ai_system
        self.vector_db_manager = VectorDbSearchManager(config=config, dry_run=dry_run)
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
        document_results = vector_db_results['documents']
        metadata_results = vector_db_results['metadatas']
        return document_results, metadata_results


    def query(self, query):
        refined_query = self.refine_query(query)
        document_results, metadata_results = self.prepare_model_context(refined_query)
        prompt = self.format_prompt(refined_query, document_results, metadata_results)
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
        transcript_template = Template(textwrap.dedent("""
                ----------------------------------------
                Podcast Name: $podcast
                Episode Name: $episode
                Content: $transcript
                ----------------------------------------
                """))
        for document_list, metadata_list in zip(document_results, metadata_results):
            for document, metadata in zip(document_list, metadata_list):
                podcast = metadata.get('podcast', 'Unknown Podcast')
                episode = metadata.get('episode', 'Unknown Episode')
                transcription = document.strip()
                context_documents += transcript_template.substitute(podcast=podcast,
                                                                    episode=episode,
                                                                    transcript=transcription)
        template = Template(textwrap.dedent("""
            Instructions:
            You are a helpful research assistant. Use the context provided to answer the question.
                                            
            Context:
            $context

                                                                    
            Question: 
            What does my archive contain about $query
            
                                            
            Answer:
            """))
        prompt = template.substitute(context=context_documents, query=query)
        if self.print_results:
            logging.info("Prompt Prepared: %s", prompt)
            logging.info("Prompt Size: %s", sys.getsizeof(prompt))
        return prompt


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Search podcast transcriptions using Ollama")
    parser.add_argument("-e", "--env-file", help="Path to a custom .env file", default=None)
    parser.add_argument("-l", "--log-level", help="Set log level (DEBUG, INFO, WARNING, ERROR)", default="INFO")
    parser.add_argument("-ai", "--ai-system", help="AI system to use (ollama or gemini)", default="ollama")
    parser.add_argument("-q", "--query", help="Query to search", required=True)
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