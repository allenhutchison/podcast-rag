# Test Suite

This directory contains unit tests for the podcast-rag project.

## Test Files

### Existing Tests (Updated)
- **`test_file_manager.py`** - Tests file processing pipeline
  - ✅ Updated to use `skip_vectordb=True` for tests that don't need File Search
- **`test_transcribe_podcasts.py`** - Tests transcription configuration
  - ✅ No changes needed
- **`test_metadatadb.py`** - Tests PostgreSQL metadata database
  - ✅ No changes needed

### New Tests (File Search Migration)
- **`test_gemini_file_search.py`** - Tests Gemini File Search manager
  - Tests store creation in dry_run mode
  - Tests transcript upload (file and text)
  - Tests batch upload functionality
  - Tests metadata conversion
  - Tests error handling

- **`test_rag.py`** - Tests RAG manager with File Search
  - Tests initialization
  - Tests query in dry_run mode
  - Tests citation extraction
  - Tests search snippets
  - Tests with mocked Gemini responses

## Running Tests

### Install Test Dependencies

```bash
pip install pytest
```

### Run All Tests

```bash
pytest tests/
```

### Run Specific Test Files

```bash
# Test File Search functionality
pytest tests/test_gemini_file_search.py -v

# Test RAG functionality
pytest tests/test_rag.py -v

# Test file manager
pytest tests/test_file_manager.py -v
```

### Run with Coverage

```bash
pip install pytest-cov
pytest tests/ --cov=src --cov-report=html
```

## Test Design

### Dry Run Mode
Most new tests use `dry_run=True` to avoid requiring:
- Gemini API credentials
- Network access
- Actual File Search store creation

This allows tests to run locally without API keys and in CI/CD environments.

### Mocking Strategy
Tests use `unittest.mock` to:
- Mock Gemini API client
- Mock API responses with grounding metadata
- Test error handling without making real API calls

### What's Tested
✅ File Search manager initialization
✅ Store creation and caching
✅ Transcript upload (dry run)
✅ Batch upload functionality
✅ Metadata conversion (lists to strings)
✅ RAG query flow
✅ Citation extraction from grounding metadata
✅ Error handling (file not found, etc.)

### What's NOT Tested (Would Require API Key)
⚠️ Actual File Search store creation
⚠️ Real transcript uploads to Google
⚠️ Live Gemini API calls
⚠️ End-to-end RAG queries

## Integration Testing

For integration testing with real API calls, create a separate test file like `test_integration.py` and mark it to be skipped unless explicitly run:

```python
@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"),
                   reason="Requires GEMINI_API_KEY")
def test_real_file_search():
    # Test with actual API
    pass
```

Run integration tests with:
```bash
pytest tests/test_integration.py --run-integration
```

## Migration Notes

The test suite was updated as part of the migration from ChromaDB to Gemini File Search:

- **ChromaDB tests removed**: No tests existed for ChromaDB functionality
- **File Search tests added**: New comprehensive test suite for File Search
- **Existing tests updated**: Modified to work with new File Search architecture
- **Backward compatibility**: Tests maintain the same interface where possible

## CI/CD Considerations

These tests are designed to run in CI/CD without requiring:
- External services (ChromaDB)
- API credentials
- Network access

For full integration testing in CI/CD:
1. Store `GEMINI_API_KEY` as a secret
2. Create a dedicated test File Search store
3. Run integration tests separately from unit tests
4. Clean up test data after runs

## Troubleshooting

### Import Errors
If you see import errors, ensure the src directory is in the Python path:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
pytest tests/
```

### Dry Run Tests Failing
Check that dry_run logic is working correctly in:
- `src/db/gemini_file_search.py`
- `src/rag.py`

### Mock Errors
If mocking isn't working, verify:
- Mock targets match the actual import paths
- Patches are applied in the correct order
- MagicMock objects have required attributes
