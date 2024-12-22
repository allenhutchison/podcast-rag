fetch('/search', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        query: searchQuery,
        env_file: null,
        ai_system: 'gemini'
    })
})
.then(response => response.json())
.then(data => {
    // Handle results
})