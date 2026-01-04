import logging
import os
import sys

from mcp.server import FastMCP as MCP

from src.argparse_shared import add_log_level_argument, get_base_parser
from src.config import Config
from src.gemini_search import GeminiSearchManager


def main():
    """Initializes and runs the MCP server."""
    logging.debug("Starting MCP server initialization...")

    parser = get_base_parser()
    add_log_level_argument(parser)
    parser.description = "MCP Server for Podcast RAG"
    args = parser.parse_args()

    # Configure logging to ensure it goes to the console
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.info(f"MCP server logging configured at {args.log_level.upper()} level")

    try:
        env_file_path = None
        if args.env_file:
            env_file_path = os.path.expanduser(args.env_file)
            logging.debug(f"Using env file: {env_file_path}")

        logging.debug("Initializing Config...")
        config = Config(env_file=env_file_path)
        logging.info("Config loaded successfully")
    except Exception as e:
        logging.error(f"Failed to initialize Config: {e}")
        sys.exit(1)

    # Initialize the MCP server
    logging.debug("Creating MCP server instance...")
    mcp = MCP(port=5002)
    logging.info("MCP server instance created on port 5002")

    @mcp.tool()
    def get_rag_context(query: str):
        """
        Retrieves relevant context snippets from the podcast vector database based on a query.

        Args:
            query: The search query to find relevant podcast content

        Returns:
            A list of relevant podcast snippets with metadata
        """
        logging.debug("get_rag_context tool registered")

        def _get_rag_context(query: str):
            logging.debug(f"get_rag_context called with query: {query}")

        try:
            logging.debug("Creating GeminiSearchManager...")
            search_manager = GeminiSearchManager(config=config, dry_run=False)
            logging.debug("GeminiSearchManager created successfully")

            logging.debug(f"Searching transcriptions for query: {query}")
            results = search_manager.search_transcriptions(query, print_results=False)
            logging.debug(f"Search completed, got {len(results.get('documents', []))} results")

            response = {
                "query": query,
                "results": results,
                "status": "success"
            }
            logging.debug(f"Returning response: {response}")
            return response
        except Exception as e:
            logging.error(f"Error in get_rag_context: {e}")
            return {
                "query": query,
                "error": str(e),
                "status": "error"
            }

    @mcp.tool()
    def search_podcasts(query: str, limit: int = 5):
        """
        Search for podcast episodes and their transcripts based on a query.

        Args:
            query: The search query to find relevant podcast episodes
            limit: Maximum number of results to return (default: 5)

        Returns:
            A list of matching podcast episodes with their metadata
        """
        logging.info(f"search_podcasts called with query: {query}, limit: {limit}")

        try:
            logging.debug("Creating GeminiSearchManager for search_podcasts...")
            search_manager = GeminiSearchManager(config=config, dry_run=False)
            logging.debug("GeminiSearchManager created successfully")

            logging.debug(f"Searching podcasts with query: {query}, limit: {limit}")
            results = search_manager.search_transcriptions(query, print_results=False)
            logging.debug(f"Search completed, got {len(results.get('documents', []))} results")

            # Limit results if specified
            if limit and 'documents' in results:
                logging.debug(f"Limiting results to {limit}")
                limited_results = {
                    'documents': results['documents'][:limit],
                    'metadatas': results['metadatas'][:limit] if 'metadatas' in results else [],
                    'distances': results['distances'][:limit] if 'distances' in results else []
                }
                results = limited_results
                logging.debug(f"Results limited to {len(results.get('documents', []))} items")

            response = {
                "query": query,
                "limit": limit,
                "results": results,
                "status": "success"
            }
            logging.debug(f"Returning response: {response}")
            return response
        except Exception as e:
            logging.error(f"Error in search_podcasts: {e}")
            return {
                "query": query,
                "error": str(e),
                "status": "error"
            }

    @mcp.tool()
    def get_podcast_info():
        """
        Get information about the podcast database and available content.

        Returns:
            Information about the podcast database including collection details
        """
        logging.info("get_podcast_info called")

        try:
            logging.debug("Creating GeminiSearchManager for get_podcast_info...")
            search_manager = GeminiSearchManager(config=config, dry_run=False)
            logging.debug("GeminiSearchManager created successfully")

            # Get File Search store info
            logging.debug("Getting File Search store info...")
            store_info = search_manager.file_search_manager.get_store_info()
            file_list = search_manager.file_search_manager.list_files()
            logging.debug(f"File count: {len(file_list)}")

            response = {
                "database_info": {
                    "store_name": config.GEMINI_FILE_SEARCH_STORE_NAME,
                    "display_name": store_info.get('display_name', 'N/A'),
                    "total_files": len(file_list)
                },
                "status": "success"
            }
            logging.debug(f"Returning response: {response}")
            return response
        except Exception as e:
            logging.error(f"Error in get_podcast_info: {e}")
            return {
                "error": str(e),
                "status": "error"
            }

    logging.info("All MCP tools registered successfully")
    logging.info("Starting MCP server with podcast RAG tools...")

    try:
        # Run the server with SSE transport
        logging.debug("Calling mcp.run() with sse transport...")
        mcp.run(transport='sse')
        logging.debug("mcp.run() completed")
    except KeyboardInterrupt:
        logging.info("MCP server stopped by user")
    except Exception as e:
        logging.error(f"MCP server error: {e}")
        import traceback
        logging.error(f"Full traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    logging.debug("MCP server script started")
    main()
