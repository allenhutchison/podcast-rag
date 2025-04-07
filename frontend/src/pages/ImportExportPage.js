import React, { useState } from 'react';
import {
  Box,
  Button,
  Typography,
  Paper,
  Alert,
  CircularProgress,
} from '@mui/material';
import {
  CloudUpload as CloudUploadIcon,
  CloudDownload as CloudDownloadIcon,
} from '@mui/icons-material';
import { usePodcasts } from '../hooks/usePodcasts';

const ImportExportPage = () => {
  const { loading, error, importOpml, exportOpml } = usePodcasts();
  const [importError, setImportError] = useState('');
  const [importSuccess, setImportSuccess] = useState(false);

  const handleImport = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    try {
      setImportError('');
      setImportSuccess(false);
      await importOpml(file);
      setImportSuccess(true);
      event.target.value = null; // Reset file input
    } catch (err) {
      setImportError(err.message);
    }
  };

  const handleExport = async () => {
    try {
      const blob = await exportOpml();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'podcasts.opml';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Failed to export OPML:', err);
    }
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Import/Export Podcasts
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Box display="flex" gap={3} flexDirection={{ xs: 'column', sm: 'row' }}>
        <Paper
          sx={{
            p: 3,
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
          }}
        >
          <Typography variant="h6" gutterBottom>
            Import Podcasts
          </Typography>
          <Typography variant="body2" color="textSecondary" align="center" sx={{ mb: 2 }}>
            Import your podcasts from an OPML file
          </Typography>
          <Button
            variant="contained"
            component="label"
            startIcon={<CloudUploadIcon />}
            disabled={loading}
          >
            Choose OPML File
            <input
              type="file"
              hidden
              accept=".opml,application/xml"
              onChange={handleImport}
            />
          </Button>
          {importError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {importError}
            </Alert>
          )}
          {importSuccess && (
            <Alert severity="success" sx={{ mt: 2 }}>
              Podcasts imported successfully!
            </Alert>
          )}
        </Paper>

        <Paper
          sx={{
            p: 3,
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
          }}
        >
          <Typography variant="h6" gutterBottom>
            Export Podcasts
          </Typography>
          <Typography variant="body2" color="textSecondary" align="center" sx={{ mb: 2 }}>
            Export your podcasts to an OPML file
          </Typography>
          <Button
            variant="contained"
            startIcon={<CloudDownloadIcon />}
            onClick={handleExport}
            disabled={loading}
          >
            Export OPML
          </Button>
        </Paper>
      </Box>

      {loading && (
        <Box display="flex" justifyContent="center" mt={3}>
          <CircularProgress />
        </Box>
      )}
    </Box>
  );
};

export default ImportExportPage; 