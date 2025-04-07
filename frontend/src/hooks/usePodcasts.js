import { useState, useCallback } from 'react';
import { podcastApi } from '../services/api';

export const usePodcasts = () => {
  const [podcasts, setPodcasts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchPodcasts = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await podcastApi.getAllPodcasts();
      setPodcasts(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch podcasts');
    } finally {
      setLoading(false);
    }
  }, []);

  const addPodcast = useCallback(async (feedUrl) => {
    try {
      setLoading(true);
      setError(null);
      const newPodcast = await podcastApi.createPodcast(feedUrl);
      setPodcasts(prev => [...prev, newPodcast]);
      return newPodcast;
    } catch (err) {
      setError(err.message || 'Failed to add podcast');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const updatePodcast = useCallback(async (id) => {
    try {
      setLoading(true);
      setError(null);
      const updatedPodcast = await podcastApi.updatePodcast(id);
      setPodcasts(prev => prev.map(podcast => 
        podcast.id === id ? updatedPodcast : podcast
      ));
      return updatedPodcast;
    } catch (err) {
      setError(err.message || 'Failed to update podcast');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const deletePodcast = useCallback(async (id) => {
    try {
      setLoading(true);
      setError(null);
      await podcastApi.deletePodcast(id);
      setPodcasts(prev => prev.filter(podcast => podcast.id !== id));
    } catch (err) {
      setError(err.message || 'Failed to delete podcast');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const importOpml = useCallback(async (file) => {
    try {
      setLoading(true);
      setError(null);
      const importedPodcasts = await podcastApi.importOpml(file);
      setPodcasts(prev => [...prev, ...importedPodcasts]);
      return importedPodcasts;
    } catch (err) {
      setError(err.message || 'Failed to import OPML file');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const exportOpml = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const blob = await podcastApi.exportOpml();
      return blob;
    } catch (err) {
      setError(err.message || 'Failed to export OPML file');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    podcasts,
    loading,
    error,
    fetchPodcasts,
    addPodcast,
    updatePodcast,
    deletePodcast,
    importOpml,
    exportOpml,
  };
}; 