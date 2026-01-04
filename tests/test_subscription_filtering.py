"""
Integration tests for subscription-based podcast filtering.

Tests the end-to-end flow of filtering chat queries to user's subscribed podcasts.
"""

import threading
import time

import pytest

from src.agents.podcast_search import (
    escape_filter_value,
    get_episode_filter,
    get_podcast_filter,
    get_podcast_filter_list,
    set_podcast_filter,
)


class TestSubscriptionFilteringIntegration:
    """Integration tests for subscription-based filtering."""

    def setup_method(self):
        """Clear filters before each test."""
        from src.agents.podcast_search import _filter_lock, _session_podcast_filter
        with _filter_lock:
            _session_podcast_filter.clear()

    def test_subscription_filter_workflow(self):
        """Test complete workflow of setting subscription filter."""
        session_id = "user-session-123"
        user_subscriptions = ["Tech Talk Daily", "AI Weekly", "Data Science Podcast"]

        # Step 1: User initiates chat with subscribed_only=True
        # This would trigger setting the podcast_list filter
        set_podcast_filter(session_id, podcast_list=user_subscriptions)

        # Step 2: Verify filter is set correctly
        podcast_list = get_podcast_filter_list(session_id)
        assert podcast_list == user_subscriptions

        # Step 3: Verify single podcast filter is None (mutually exclusive)
        single_podcast = get_podcast_filter(session_id)
        assert single_podcast is None

        # Step 4: Build metadata filter string for File Search
        filter_parts = []
        if podcast_list:
            podcast_or_conditions = []
            for podcast_name in podcast_list:
                escaped = escape_filter_value(podcast_name)
                if escaped:
                    podcast_or_conditions.append(f'podcast="{escaped}"')
            if podcast_or_conditions:
                filter_parts.append(f"({' OR '.join(podcast_or_conditions)})")

        # Verify OR filter structure
        assert len(filter_parts) == 1
        filter_str = filter_parts[0]
        assert filter_str.startswith("(")
        assert filter_str.endswith(")")
        assert filter_str.count("OR") == len(user_subscriptions) - 1

    def test_switching_between_filter_modes(self):
        """Test switching between single podcast and subscription list filters."""
        session_id = "mode-switch-session"

        # Start with subscription filter
        subscriptions = ["Podcast A", "Podcast B", "Podcast C"]
        set_podcast_filter(session_id, podcast_list=subscriptions)

        assert get_podcast_filter_list(session_id) == subscriptions
        assert get_podcast_filter(session_id) is None

        # Switch to single podcast filter
        set_podcast_filter(session_id, podcast_name="Specific Podcast")

        assert get_podcast_filter(session_id) == "Specific Podcast"
        assert get_podcast_filter_list(session_id) is None

        # Switch back to subscription filter
        set_podcast_filter(session_id, podcast_list=["New Podcast"])

        assert get_podcast_filter_list(session_id) == ["New Podcast"]
        assert get_podcast_filter(session_id) is None

    def test_subscription_filter_with_special_characters(self):
        """Test subscription filtering with podcast names containing special characters."""
        session_id = "special-chars-session"
        subscriptions = [
            'The "Tech" Podcast',
            "AI & ML Weekly",
            "Data\\Science",
            "Morning, Noon & Night"
        ]

        set_podcast_filter(session_id, podcast_list=subscriptions)

        # Build filter string
        podcast_list = get_podcast_filter_list(session_id)
        podcast_or_conditions = []
        for podcast_name in podcast_list:
            escaped = escape_filter_value(podcast_name)
            if escaped:
                podcast_or_conditions.append(f'podcast="{escaped}"')

        # Verify all podcasts were escaped correctly
        assert len(podcast_or_conditions) == 4

        # Verify specific escaping
        assert 'podcast="The \\"Tech\\" Podcast"' in podcast_or_conditions
        assert 'podcast="Data\\\\Science"' in podcast_or_conditions

    def test_empty_subscription_list_handling(self):
        """Test handling of empty subscription list."""
        session_id = "empty-subscriptions"

        # User has no subscriptions
        set_podcast_filter(session_id, podcast_list=[])

        podcast_list = get_podcast_filter_list(session_id)
        assert podcast_list == []

        # Empty list should not create any filter conditions
        podcast_or_conditions = []
        if podcast_list:
            for podcast_name in podcast_list:
                escaped = escape_filter_value(podcast_name)
                if escaped:
                    podcast_or_conditions.append(f'podcast="{escaped}"')

        assert len(podcast_or_conditions) == 0

    def test_concurrent_subscription_filters(self):
        """Test concurrent access to subscription filters from multiple sessions."""
        num_sessions = 10
        sessions_data = {}

        for i in range(num_sessions):
            session_id = f"concurrent-session-{i}"
            subscriptions = [f"Podcast_{i}_{j}" for j in range(3)]
            sessions_data[session_id] = subscriptions

        errors = []

        def set_and_verify(session_id, subscriptions):
            try:
                # Set filter
                set_podcast_filter(session_id, podcast_list=subscriptions)
                time.sleep(0.01)  # Simulate processing time

                # Verify filter
                result = get_podcast_filter_list(session_id)
                if result != subscriptions:
                    errors.append(f"Session {session_id}: expected {subscriptions}, got {result}")

                time.sleep(0.01)
            except Exception as e:
                errors.append(f"Session {session_id}: {e}")

        # Run all sessions concurrently
        threads = []
        for session_id, subscriptions in sessions_data.items():
            thread = threading.Thread(target=set_and_verify, args=(session_id, subscriptions))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify no errors
        assert len(errors) == 0, f"Concurrent access errors: {errors}"

        # Verify all sessions have correct filters
        for session_id, expected_subscriptions in sessions_data.items():
            actual = get_podcast_filter_list(session_id)
            assert actual == expected_subscriptions, \
                f"Session {session_id} filter mismatch"

    def test_subscription_filter_cleanup_on_clear(self):
        """Test that clearing filter removes subscription list."""
        session_id = "cleanup-test"
        subscriptions = ["Podcast 1", "Podcast 2"]

        # Set subscription filter
        set_podcast_filter(session_id, podcast_list=subscriptions)
        assert get_podcast_filter_list(session_id) == subscriptions

        # Clear all filters
        set_podcast_filter(session_id)

        # Verify everything is cleared
        assert get_podcast_filter(session_id) is None
        assert get_podcast_filter_list(session_id) is None

    def test_large_subscription_list(self):
        """Test handling of large subscription lists."""
        session_id = "large-list"
        large_subscriptions = [f"Podcast Number {i}" for i in range(100)]

        set_podcast_filter(session_id, podcast_list=large_subscriptions)

        podcast_list = get_podcast_filter_list(session_id)
        assert len(podcast_list) == 100

        # Build OR filter
        podcast_or_conditions = []
        for podcast_name in podcast_list:
            escaped = escape_filter_value(podcast_name)
            if escaped:
                podcast_or_conditions.append(f'podcast="{escaped}"')

        # Verify all were processed
        assert len(podcast_or_conditions) == 100

        # Verify OR structure
        filter_str = f"({' OR '.join(podcast_or_conditions)})"
        assert filter_str.count("OR") == 99

    def test_subscription_filter_with_episode_filter_combination(self):
        """Test combining subscription filter with episode filter."""
        session_id = "combo-filter"
        subscriptions = ["Podcast A", "Podcast B"]
        episode_name = "Special Episode"

        # Set both filters
        set_podcast_filter(session_id, podcast_list=subscriptions, episode_name=episode_name)

        # Verify both are set
        assert get_podcast_filter_list(session_id) == subscriptions
        assert get_episode_filter(session_id) == episode_name

        # Note: In practice, episode filter with subscription list might not be semantically valid,
        # but the API allows it and it's up to the application logic to handle


class TestMetadataFilterBuilding:
    """Test building metadata filter strings for File Search."""

    def test_build_single_podcast_filter(self):
        """Test building filter for single podcast."""
        podcast_name = "Tech Talk"
        escaped = escape_filter_value(podcast_name)

        filter_str = f'podcast="{escaped}"'
        assert filter_str == 'podcast="Tech Talk"'

    def test_build_podcast_list_filter(self):
        """Test building OR filter for podcast list."""
        podcast_list = ["Podcast A", "Podcast B", "Podcast C"]
        podcast_or_conditions = []

        for podcast_name in podcast_list:
            escaped = escape_filter_value(podcast_name)
            if escaped:
                podcast_or_conditions.append(f'podcast="{escaped}"')

        filter_str = f"({' OR '.join(podcast_or_conditions)})"

        assert filter_str == '(podcast="Podcast A" OR podcast="Podcast B" OR podcast="Podcast C")'

    def test_build_combined_filter_with_episode(self):
        """Test building combined filter with podcast list and episode."""
        podcast_list = ["Podcast A", "Podcast B"]
        episode_name = "Episode 42"

        filter_parts = []

        # Build podcast list OR
        podcast_or_conditions = []
        for podcast_name in podcast_list:
            escaped = escape_filter_value(podcast_name)
            if escaped:
                podcast_or_conditions.append(f'podcast="{escaped}"')

        if podcast_or_conditions:
            filter_parts.append(f"({' OR '.join(podcast_or_conditions)})")

        # Add episode filter
        escaped_episode = escape_filter_value(episode_name)
        if escaped_episode:
            filter_parts.append(f'episode="{escaped_episode}"')

        # Combine with AND
        final_filter = " AND ".join(filter_parts)

        assert 'podcast="Podcast A" OR podcast="Podcast B"' in final_filter
        assert 'episode="Episode 42"' in final_filter
        assert " AND " in final_filter

    def test_filter_with_special_characters_integration(self):
        """Test complete filter building with special characters."""
        podcast_list = [
            'The "Morning" Show',
            "Tech & Science",
            "Path\\To\\Knowledge"
        ]

        podcast_or_conditions = []
        for podcast_name in podcast_list:
            escaped = escape_filter_value(podcast_name)
            if escaped:
                podcast_or_conditions.append(f'podcast="{escaped}"')

        filter_str = f"({' OR '.join(podcast_or_conditions)})"

        # Verify proper escaping in final filter
        assert 'podcast="The \\"Morning\\" Show"' in filter_str
        assert 'podcast="Tech & Science"' in filter_str
        assert 'podcast="Path\\\\To\\\\Knowledge"' in filter_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
