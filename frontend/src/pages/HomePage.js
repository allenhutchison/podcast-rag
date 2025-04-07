import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Grid,
  Paper,
  Container,
} from '@mui/material';
import {
  Podcasts as PodcastsIcon,
  CloudUpload as CloudUploadIcon,
  CloudDownload as CloudDownloadIcon,
} from '@mui/icons-material';

const HomePage = () => {
  const navigate = useNavigate();

  const features = [
    {
      title: 'Manage Podcasts',
      description: 'Add, update, and organize your favorite podcasts in one place.',
      icon: <PodcastsIcon sx={{ fontSize: 40 }} />,
      action: 'View Podcasts',
      path: '/podcasts',
    },
    {
      title: 'Import Podcasts',
      description: 'Import your existing podcast subscriptions from an OPML file.',
      icon: <CloudUploadIcon sx={{ fontSize: 40 }} />,
      action: 'Import OPML',
      path: '/import-export',
    },
    {
      title: 'Export Podcasts',
      description: 'Export your podcast list to share with other podcast apps.',
      icon: <CloudDownloadIcon sx={{ fontSize: 40 }} />,
      action: 'Export OPML',
      path: '/import-export',
    },
  ];

  return (
    <Container maxWidth="lg">
      <Box sx={{ my: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom align="center">
          Welcome to Podcast Manager
        </Typography>
        <Typography variant="h5" component="h2" gutterBottom align="center" color="textSecondary">
          Your all-in-one podcast management solution
        </Typography>

        <Grid container spacing={4} sx={{ mt: 4 }}>
          {features.map((feature) => (
            <Grid item xs={12} md={4} key={feature.title}>
              <Paper
                sx={{
                  p: 3,
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  textAlign: 'center',
                }}
              >
                <Box sx={{ mb: 2, color: 'primary.main' }}>
                  {feature.icon}
                </Box>
                <Typography variant="h6" component="h3" gutterBottom>
                  {feature.title}
                </Typography>
                <Typography variant="body1" color="textSecondary" paragraph>
                  {feature.description}
                </Typography>
                <Button
                  variant="contained"
                  onClick={() => navigate(feature.path)}
                  sx={{ mt: 'auto' }}
                >
                  {feature.action}
                </Button>
              </Paper>
            </Grid>
          ))}
        </Grid>
      </Box>
    </Container>
  );
};

export default HomePage; 