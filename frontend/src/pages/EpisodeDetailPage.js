import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  CardContent,
  CardMedia,
  Button,
  CircularProgress,
  Alert,
  Chip,
  Divider,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Download as DownloadIcon,
} from '@mui/icons-material';
import { podcastApi } from '../services/api';

const EpisodeDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [episode, setEpisode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    fetchEpisode();
  }, [id]);

  const fetchEpisode = async () => {
    try {
      setLoading(true);
      setError(null);
      const episodeData = await podcastApi.getEpisode(id);
      setEpisode(episodeData);
    } catch (err) {
      setError(err.message || 'Failed to fetch episode details');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    try {
      setDownloading(true);
      await podcastApi.downloadEpisode(id);
      // Refresh episode to update download status
      const updatedEpisode = await podcastApi.getEpisode(id);
      setEpisode(updatedEpisode);
    } catch (err) {
      console.error('Failed to download episode:', err);
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        {error}
      </Alert>
    );
  }

  if (!episode) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        Episode not found
      </Alert>
    );
  }

  return (
    <Box>
      <Box display="flex" alignItems="center" mb={3}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate(`/podcasts/${episode.podcast_id}`)}
        >
          Back to Podcast
        </Button>
      </Box>

      <Card>
        <Box display="flex" flexDirection={{ xs: 'column', md: 'row' }}>
          {episode.image_url && (
            <CardMedia
              component="img"
              sx={{ width: { xs: '100%', md: 300 }, height: { xs: 200, md: 'auto' } }}
              image={episode.image_url}
              alt={episode.title}
            />
          )}
          <CardContent sx={{ flex: 1 }}>
            <Typography variant="h4" gutterBottom>
              {episode.title}
            </Typography>
            <Typography variant="subtitle1" color="textSecondary" gutterBottom>
              {new Date(episode.published_at).toLocaleDateString()}
            </Typography>
            <Typography variant="body1" paragraph>
              {episode.description}
            </Typography>
            <Box display="flex" gap={1} flexWrap="wrap" mb={2}>
              {episode.categories?.map((category) => (
                <Chip key={category} label={category} size="small" />
              ))}
            </Box>
            <Button
              variant="contained"
              startIcon={<DownloadIcon />}
              onClick={handleDownload}
              disabled={episode.downloaded || downloading}
            >
              {episode.downloaded ? 'Downloaded' : 'Download Episode'}
            </Button>
          </CardContent>
        </Box>
      </Card>

      {episode.transcript && (
        <>
          <Divider sx={{ my: 4 }} />
          <Typography variant="h5" gutterBottom>
            Transcript
          </Typography>
          <Card>
            <CardContent>
              <Typography variant="body1" style={{ whiteSpace: 'pre-wrap' }}>
                {episode.transcript}
              </Typography>
            </CardContent>
          </Card>
        </>
      )}
    </Box>
  );
};

export default EpisodeDetailPage; 