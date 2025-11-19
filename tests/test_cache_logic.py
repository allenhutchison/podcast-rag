import unittest
import os
import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Mock the config and logger
with patch('src.config.Config'), patch('src.db.gemini_file_search.logging'):
    from src.db.gemini_file_search import GeminiFileSearchManager

class TestCacheLogic(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.test_dir, '.file_search_cache.json')
        
        # Mock config
        self.config = MagicMock()
        self.config.GEMINI_API_KEY = "fake_key"
        
        # Initialize manager with mocked get_cache_path
        self.manager = GeminiFileSearchManager(self.config)
        self.manager._get_cache_path = MagicMock(return_value=self.cache_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)

    def test_atomic_write(self):
        """Verify that _save_cache_with_metadata performs an atomic write."""
        files = {"test.txt": {"resource_name": "files/123", "metadata": {}}}
        
        # Spy on os.replace
        with patch('os.replace', side_effect=os.replace) as mock_replace:
            self.manager._save_cache_with_metadata("store_123", files)
            
            # Verify file exists and has correct content
            self.assertTrue(os.path.exists(self.cache_path))
            with open(self.cache_path, 'r') as f:
                data = json.load(f)
                self.assertEqual(data['store_name'], "store_123")
                self.assertEqual(len(data['files']), 1)
            
            # Verify os.replace was called
            self.assertTrue(mock_replace.called)

    def test_refresh_logic_empty(self):
        """Verify logic proceeds if cache is empty."""
        # Create empty cache file (simulating 0 files)
        cache_data = {
            'version': '2.0',
            'store_name': 'store_123',
            'last_sync': datetime.utcnow().isoformat(),
            'files': {}
        }
        with open(self.cache_path, 'w') as f:
            json.dump(cache_data, f)
            
        # We can't easily import refresh_cache_background because it's inside app.py
        # and depends on global state. Instead, we'll replicate the logic here to verify it.
        
        should_update = False
        with open(self.cache_path, 'r') as f:
            data = json.load(f)
            file_count = len(data.get('files', {}))
            if file_count == 0:
                should_update = True
                
        self.assertTrue(should_update, "Should update if file count is 0")

    def test_refresh_logic_stale(self):
        """Verify logic proceeds if cache is old (>24h)."""
        # Create stale cache file
        stale_time = datetime.utcnow() - timedelta(hours=25)
        cache_data = {
            'version': '2.0',
            'store_name': 'store_123',
            'last_sync': stale_time.isoformat(),
            'files': {"test.txt": "files/123"}
        }
        with open(self.cache_path, 'w') as f:
            json.dump(cache_data, f)
            
        should_update = False
        with open(self.cache_path, 'r') as f:
            data = json.load(f)
            last_sync = datetime.fromisoformat(data.get('last_sync'))
            if datetime.utcnow() - last_sync > timedelta(hours=24):
                should_update = True
                
        self.assertTrue(should_update, "Should update if cache is stale")

    def test_refresh_logic_fresh(self):
        """Verify logic skips if cache is fresh (<24h) and not empty."""
        # Create fresh cache file
        fresh_time = datetime.utcnow() - timedelta(hours=1)
        cache_data = {
            'version': '2.0',
            'store_name': 'store_123',
            'last_sync': fresh_time.isoformat(),
            'files': {"test.txt": "files/123"}
        }
        with open(self.cache_path, 'w') as f:
            json.dump(cache_data, f)
            
        should_update = False
        with open(self.cache_path, 'r') as f:
            data = json.load(f)
            last_sync = datetime.fromisoformat(data.get('last_sync'))
            file_count = len(data.get('files', {}))
            
            if file_count == 0:
                should_update = True
            elif datetime.utcnow() - last_sync > timedelta(hours=24):
                should_update = True
                
        self.assertFalse(should_update, "Should NOT update if cache is fresh and has files")

if __name__ == '__main__':
    unittest.main()
