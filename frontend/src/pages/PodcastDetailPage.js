import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  CardContent,
  CardMedia,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Button,
  Divider,
  CircularProgress,
  Alert,
  Chip,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Download as DownloadIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { podcastApi } from '../services/api';

const PodcastDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [podcast, setPodcast] = useState(null);
  const [episodes, setEpisodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchPodcastAndEpisodes();
  }, [id]);

  const fetchPodcastAndEpisodes = async () => {
    try {
      setLoading(true);
      setError(null);
      const [podcastData, episodesData] = await Promise.all([
        podcastApi.getPodcast(id),
        podcastApi.getEpisodes(id),
      ]);
      setPodcast(podcastData);
      setEpisodes(episodesData);
    } catch (err) {
      setError(err.message || 'Failed to fetch podcast details');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadEpisode = async (episodeId) => {
    try {
      await podcastApi.downloadEpisode(episodeId);
      // Refresh episodes to update download status
      const updatedEpisodes = await podcastApi.getEpisodes(id);
      setEpisodes(updatedEpisodes);
    } catch (err) {
      console.error('Failed to download episode:', err);
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

  if (!podcast) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        Podcast not found
      </Alert>
    );
  }

  return (
    <Box>
      <Box display="flex" alignItems="center" mb={3}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/podcasts')}
          sx={{ mr: 2 }}
        >
          Back to Podcasts
        </Button>
        <Button
          startIcon={<RefreshIcon />}
          onClick={fetchPodcastAndEpisodes}
          disabled={loading}
        >
          Refresh
        </Button>
      </Box>

      <Card sx={{ mb: 4 }}>
        <Box display="flex" flexDirection={{ xs: 'column', md: 'row' }}>
          {podcast.image_url && (
            <CardMedia
              component="img"
              sx={{ width: { xs: '100%', md: 200 }, height: { xs: 200, md: 'auto' } }}
              image={podcast.image_url}
              alt={podcast.title}
            />
          )}
          <CardContent sx={{ flex: 1 }}>
            <Typography variant="h4" gutterBottom>
              {podcast.title}
            </Typography>
            <Typography variant="subtitle1" color="textSecondary" gutterBottom>
              {podcast.author}
            </Typography>
            <Typography variant="body1" paragraph>
              {podcast.description}
            </Typography>
            <Box display="flex" gap={1} flexWrap="wrap">
              {podcast.categories?.map((category) => (
                <Chip key={category} label={category} size="small" />
              ))}
            </Box>
          </CardContent>
        </Box>
      </Card>

      <Typography variant="h5" gutterBottom>
        Episodes
      </Typography>

      <List>
        {episodes.map((episode, index) => (
          <React.Fragment key={episode.id}>
            <ListItem>
              <ListItemText
                primary={episode.title}
                secondary={
                  <>
                    <Typography component="span" variant="body2" color="textSecondary">
                      {new Date(episode.published_at).toLocaleDateString()}
                    </Typography>
                    <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
                      {episode.description?.slice(0, 150)}
                      {episode.description?.length > 150 ? '...' : ''}
                    </Typography>
                  </>
                }
              />
              <ListItemSecondaryAction>
                <IconButton
                  edge="end"
                  onClick={() => handleDownloadEpisode(episode.id)}
                  disabled={episode.downloaded}
                >
                  <DownloadIcon />
                </IconButton>
              </ListItemSecondaryAction>
            </ListItem>
            {index < episodes.length - 1 && <Divider />}
          </React.Fragment>
        ))}
      </List>
    </Box>
  );
};

export default PodcastDetailPage; 