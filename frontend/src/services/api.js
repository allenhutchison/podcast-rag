import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Podcast API
export const podcastApi = {
  // Get all podcasts
  getAllPodcasts: async () => {
    const response = await api.get('/podcasts');
    return response.data;
  },

  // Get a single podcast
  getPodcast: async (id) => {
    const response = await api.get(`/podcasts/${id}`);
    return response.data;
  },

  // Create a new podcast
  createPodcast: async (feedUrl) => {
    const response = await api.post('/podcasts', { feed_url: feedUrl });
    return response.data;
  },

  // Update a podcast
  updatePodcast: async (id) => {
    const response = await api.put(`/podcasts/${id}`);
    return response.data;
  },

  // Delete a podcast
  deletePodcast: async (id) => {
    const response = await api.delete(`/podcasts/${id}`);
    return response.data;
  },

  // Get episodes for a podcast
  getEpisodes: async (podcastId) => {
    const response = await api.get(`/podcasts/${podcastId}/episodes`);
    return response.data;
  },

  // Get a single episode
  getEpisode: async (episodeId) => {
    const response = await api.get(`/podcasts/episodes/${episodeId}`);
    return response.data;
  },

  // Download an episode
  downloadEpisode: async (episodeId) => {
    const response = await api.post(`/podcasts/episodes/${episodeId}/download`);
    return response.data;
  },

  // Get episode audio URL
  getEpisodeAudioUrl: (episodeId) => {
    return `${API_URL}/podcasts/episodes/${episodeId}/audio`;
  },

  // Import podcasts from OPML
  importOpml: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/podcasts/import-opml', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Export podcasts to OPML
  exportOpml: async () => {
    const response = await api.get('/podcasts/export-opml', {
      responseType: 'blob',
    });
    return response.data;
  },
};

export default api; 