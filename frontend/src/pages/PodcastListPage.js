import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  CardContent,
  CardActions,
  Typography,
  Grid,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  CircularProgress,
  Alert,
} from '@mui/material';
import {
  Add as AddIcon,
  Refresh as RefreshIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
} from '@mui/icons-material';
import { usePodcasts } from '../hooks/usePodcasts';

const PodcastListPage = () => {
  const navigate = useNavigate();
  const {
    podcasts,
    loading,
    error,
    fetchPodcasts,
    addPodcast,
    updatePodcast,
    deletePodcast,
  } = usePodcasts();

  const [openAddDialog, setOpenAddDialog] = useState(false);
  const [feedUrl, setFeedUrl] = useState('');
  const [addError, setAddError] = useState('');

  useEffect(() => {
    fetchPodcasts();
  }, [fetchPodcasts]);

  const handleAddPodcast = async () => {
    try {
      setAddError('');
      await addPodcast(feedUrl);
      setOpenAddDialog(false);
      setFeedUrl('');
    } catch (err) {
      setAddError(err.message);
    }
  };

  const handleUpdatePodcast = async (id) => {
    try {
      await updatePodcast(id);
    } catch (err) {
      console.error('Failed to update podcast:', err);
    }
  };

  const handleDeletePodcast = async (id) => {
    if (window.confirm('Are you sure you want to delete this podcast?')) {
      try {
        await deletePodcast(id);
      } catch (err) {
        console.error('Failed to delete podcast:', err);
      }
    }
  };

  if (loading && !podcasts.length) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">My Podcasts</Typography>
        <Box>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setOpenAddDialog(true)}
            sx={{ mr: 1 }}
          >
            Add Podcast
          </Button>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={fetchPodcasts}
            disabled={loading}
          >
            Refresh
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        {podcasts.map((podcast) => (
          <Grid item xs={12} sm={6} md={4} key={podcast.id}>
            <Card>
              <CardContent>
                <Typography variant="h6" noWrap>
                  {podcast.title}
                </Typography>
                <Typography color="textSecondary" gutterBottom>
                  {podcast.author}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  {podcast.description?.slice(0, 150)}
                  {podcast.description?.length > 150 ? '...' : ''}
                </Typography>
              </CardContent>
              <CardActions>
                <Button
                  size="small"
                  onClick={() => navigate(`/podcasts/${podcast.id}`)}
                >
                  View Episodes
                </Button>
                <IconButton
                  size="small"
                  onClick={() => handleUpdatePodcast(podcast.id)}
                  disabled={loading}
                >
                  <EditIcon />
                </IconButton>
                <IconButton
                  size="small"
                  onClick={() => handleDeletePodcast(podcast.id)}
                  disabled={loading}
                >
                  <DeleteIcon />
                </IconButton>
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Dialog open={openAddDialog} onClose={() => setOpenAddDialog(false)}>
        <DialogTitle>Add New Podcast</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Feed URL"
            type="url"
            fullWidth
            value={feedUrl}
            onChange={(e) => setFeedUrl(e.target.value)}
            error={!!addError}
            helperText={addError}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddDialog(false)}>Cancel</Button>
          <Button
            onClick={handleAddPodcast}
            variant="contained"
            disabled={!feedUrl || loading}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default PodcastListPage; 