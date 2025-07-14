import logging
import sys
import os
from mcp.server import FastMCP as MCP
from src.config import Config
from src.chroma_search import VectorDbSearchManager
from src.argparse_shared import get_base_parser, add_log_level_argument

def main():
    """Initializes and runs the MCP server."""
    print("DEBUG: Starting MCP server initialization...", file=sys.stderr)
    
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
    
    print(f"DEBUG: Log level set to {args.log_level.upper()}", file=sys.stderr)
    logging.info("DEBUG: MCP server logging configured")

    try:
        env_file_path = None
        if args.env_file:
            env_file_path = os.path.expanduser(args.env_file)
            print(f"DEBUG: Using env file: {env_file_path}", file=sys.stderr)
        
        print("DEBUG: Initializing Config...", file=sys.stderr)
        config = Config(env_file=env_file_path)
        print("DEBUG: Config initialized successfully", file=sys.stderr)
        logging.info("DEBUG: Config loaded successfully")
    except Exception as e:
        print(f"FATAL: Failed to initialize Config: {e}", file=sys.stderr)
        logging.error(f"FATAL: Config initialization failed: {e}")
        sys.exit(1)

    # Initialize the MCP server
    print("DEBUG: Creating MCP server instance...", file=sys.stderr)
    mcp = MCP(port=5002)
    print("DEBUG: MCP server instance created on port 5002", file=sys.stderr)
    logging.info("DEBUG: MCP server instance created")

    @mcp.tool()
    def get_rag_context(query: str):
        """
        Retrieves relevant context snippets from the podcast vector database based on a query.
        
        Args:
            query: The search query to find relevant podcast content
            
        Returns:
            A list of relevant podcast snippets with metadata
        """
        print(f"DEBUG: get_rag_context tool registered", file=sys.stderr)
        logging.info(f"DEBUG: get_rag_context tool registered")
        
        def _get_rag_context(query: str):
            print(f"DEBUG: get_rag_context called with query: {query}", file=sys.stderr)
            logging.info(f"DEBUG: get_rag_context tool called with query: {query}")
        
        try:
            print("DEBUG: Creating VectorDbSearchManager...", file=sys.stderr)
            search_manager = VectorDbSearchManager(config=config, dry_run=False)
            print("DEBUG: VectorDbSearchManager created successfully", file=sys.stderr)
            
            print(f"DEBUG: Searching transcriptions for query: {query}", file=sys.stderr)
            results = search_manager.search_transcriptions(query, print_results=False)
            print(f"DEBUG: Search completed, got {len(results.get('documents', []))} results", file=sys.stderr)
            
            response = {
                "query": query,
                "results": results,
                "status": "success"
            }
            print(f"DEBUG: Returning response: {response}", file=sys.stderr)
            return response
        except Exception as e:
            print(f"ERROR in get_rag_context: {e}", file=sys.stderr)
            logging.error(f"ERROR in get_rag_context: {e}")
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
        print(f"DEBUG: search_podcasts called with query: {query}, limit: {limit}", file=sys.stderr)
        logging.info(f"DEBUG: search_podcasts tool called with query: {query}, limit: {limit}")
        
        try:
            print("DEBUG: Creating VectorDbSearchManager for search_podcasts...", file=sys.stderr)
            search_manager = VectorDbSearchManager(config=config, dry_run=False)
            print("DEBUG: VectorDbSearchManager created successfully", file=sys.stderr)
            
            print(f"DEBUG: Searching podcasts with query: {query}, limit: {limit}", file=sys.stderr)
            results = search_manager.search_transcriptions(query, print_results=False)
            print(f"DEBUG: Search completed, got {len(results.get('documents', []))} results", file=sys.stderr)
            
            # Limit results if specified
            if limit and 'documents' in results:
                print(f"DEBUG: Limiting results to {limit}", file=sys.stderr)
                limited_results = {
                    'documents': results['documents'][:limit],
                    'metadatas': results['metadatas'][:limit] if 'metadatas' in results else [],
                    'distances': results['distances'][:limit] if 'distances' in results else []
                }
                results = limited_results
                print(f"DEBUG: Results limited to {len(results.get('documents', []))} items", file=sys.stderr)
            
            response = {
                "query": query,
                "limit": limit,
                "results": results,
                "status": "success"
            }
            print(f"DEBUG: Returning response: {response}", file=sys.stderr)
            return response
        except Exception as e:
            print(f"ERROR in search_podcasts: {e}", file=sys.stderr)
            logging.error(f"ERROR in search_podcasts: {e}")
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
        print("DEBUG: get_podcast_info called", file=sys.stderr)
        logging.info("DEBUG: get_podcast_info tool called")
        
        try:
            print("DEBUG: Creating VectorDbSearchManager for get_podcast_info...", file=sys.stderr)
            search_manager = VectorDbSearchManager(config=config, dry_run=False)
            print("DEBUG: VectorDbSearchManager created successfully", file=sys.stderr)
            
            # Get collection info
            print("DEBUG: Getting collection info...", file=sys.stderr)
            collection = search_manager.vector_db.get_collection()
            count = collection.count()
            print(f"DEBUG: Collection count: {count}", file=sys.stderr)
            
            response = {
                "database_info": {
                    "collection_name": config.CHROMA_DB_COLLECTION,
                    "host": config.CHROMA_DB_HOST,
                    "port": config.CHROMA_DB_PORT,
                    "total_episodes": count
                },
                "status": "success"
            }
            print(f"DEBUG: Returning response: {response}", file=sys.stderr)
            return response
        except Exception as e:
            print(f"ERROR in get_podcast_info: {e}", file=sys.stderr)
            logging.error(f"ERROR in get_podcast_info: {e}")
            return {
                "error": str(e),
                "status": "error"
            }

    print("DEBUG: All tools registered successfully", file=sys.stderr)
    logging.info("DEBUG: All MCP tools registered successfully")
    logging.info("Starting MCP server with podcast RAG tools...")
    print("DEBUG: About to start MCP server...", file=sys.stderr)
    
    try:
        # Run the server with SSE transport
        print("DEBUG: Calling mcp.run() with sse transport...", file=sys.stderr)
        mcp.run(transport='sse')
        print("DEBUG: mcp.run() completed", file=sys.stderr)
    except KeyboardInterrupt:
        print("DEBUG: KeyboardInterrupt received", file=sys.stderr)
        logging.info("MCP server stopped by user")
    except Exception as e:
        print(f"FATAL: MCP server error: {e}", file=sys.stderr)
        logging.error(f"FATAL: MCP server error: {e}")
        import traceback
        print(f"FATAL: Full traceback: {traceback.format_exc()}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print("DEBUG: MCP server script started", file=sys.stderr)
    main()
