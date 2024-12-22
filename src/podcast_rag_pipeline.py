"""
title: Podcast Rag Pipeline
author: Allen Hutchison
date: 2024-11-16
version: 0.1
license: MIT
description: Retrieve podcast transcriptions data using Chromadb.
requirements: chromadb-client >= 0.5.18, sentence-transformers
"""

import asyncio
import logging
from typing import List, Union, Generator, Iterator
import chromadb
from chromadb.utils import embedding_functions
from tenacity import retry, stop_after_attempt, wait_exponential
import os
from pydantic import BaseModel

class Pipeline:
    class Valves(BaseModel):
        CHROMA_DB_HOST: str
        CHROMA_DB_PORT: str
        CHROMA_DB_COLLECTION: str

    def __init__(self):
        self.client = None
        self.collection = None

        self.valves = self.Valves(
            **{
                "CHROMA_DB_HOST": os.getenv("CHROMA_DB_HOST", "chromadb.hutchistan.org"),
                "CHROMA_DB_PORT": os.getenv("CHROMA_DB_PORT", "443"),
                "CHROMA_DB_COLLECTION": os.getenv("CHROMA_DB_COLLECTION", "podcasts_collection"),
            }
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def initialize_chroma(self):
        try:
            self.client = chromadb.HttpClient(
                host=self.valves.CHROMA_DB_HOST, 
                port=self.valves.CHROMA_DB_PORT,
                ssl=True,
                timeout=30  # Add timeout
            )
            sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self.collection = self.client.get_collection(
                name=self.valves.CHROMA_DB_COLLECTION,
                embedding_function=sentence_transformer_ef
            )
            logging.info("ChromaDB connection established")
        except Exception as e:
            logging.error(f"Failed to initialize ChromaDB: {str(e)}")
            raise

    def search_transcriptions(self, query: str):
        if not self.collection:
            raise RuntimeError("ChromaDB collection not initialized")
            
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=10
            )
            return results
        except Exception as e:
            logging.error(f"Search failed: {str(e)}")
            raise

    async def pipe(self, user_message: str, model_id: str, messages: List[dict], body: dict):
        try:
            if self.collection is None:
                await self.initialize_chroma()
            return self.search_transcriptions(user_message)
        except Exception as e:
            logging.error(f"Pipeline failed: {str(e)}")
            raise

async def main():
    logging.basicConfig(level=logging.INFO)
    pipeline = Pipeline()
    try:
        results = await pipeline.pipe("your query", "model", [], {})
        print(results)
    except Exception as e:
        logging.error(f"Pipeline failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
