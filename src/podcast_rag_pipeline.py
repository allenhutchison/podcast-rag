"""
title: Podcast Rag Pipeline
author: Allen Hutchison
date: 2024-11-16
version: 0.1
license: MIT
description: Retrieve podcast transcriptions data using Chromadb.
requirements: chromadb-client >= 0.5.18, sentence-transformers
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
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

    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass

    def search_transcriptions(self, query):
        results = self.collection.query(
            query_texts=[query],
            n_results=10
        )
        return results

    def pipe(self, user_message: str, model_id: str, messages: List[dict], body: dict) -> Union[str, Generator, Iterator]:
        import chromadb
        from chromadb.utils import embedding_functions
        if self.collection is None:
            self.client = chromadb.HttpClient(host=self.valves.CHROMA_DB_HOST, port=self.valves.CHROMA_DB_PORT, ssl=True)
            sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            self.collection = self.client.get_collection(name=self.valves.CHROMA_DB_COLLECTION, embedding_function=sentence_transformer_ef)
            return self.search_transcriptions(user_message)
        else:
            return self.search_transcriptions(user_message)



async def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )
    pipeline = Pipeline()
    await pipeline.on_startup()
    query = "machine learning"
    results = pipeline.search_transcriptions(query)
    print(results)

if __name__ == "__main__":
    import asyncio
    import logging
    asyncio.run(main())
