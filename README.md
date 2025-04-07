# Podcast Manager

A full-featured podcast management application with a modern web interface. This application allows you to manage your podcast subscriptions, import/export podcast lists, and download episodes for offline listening.

## Features

- **Podcast Management**
  - Add podcasts by RSS feed URL
  - View podcast details and episodes
  - Update podcast information
  - Delete podcasts
  - Download episodes for offline listening

- **OPML Support**
  - Import podcasts from OPML files
  - Export podcasts to OPML format
  - Compatible with other podcast apps

- **Modern Web Interface**
  - Responsive design
  - Material UI components
  - Intuitive navigation
  - Real-time updates

## Tech Stack

### Backend
- Python
- FastAPI
- SQLite
- SQLAlchemy
- Pydantic

### Frontend
- React
- Material-UI
- React Router
- Axios

## Setup

### Backend Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the backend server:
```bash
uvicorn src.main:app --reload
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm start
```

The application will be available at:
- Backend API: http://localhost:8000
- Frontend: http://localhost:3000

## API Documentation

Once the backend server is running, you can access the API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

### Project Structure

```
podcast-rag/
├── src/
│   ├── api/
│   │   ├── routes/
│   │   └── dependencies.py
│   ├── core/
│   │   ├── config.py
│   │   └── podcast.py
│   ├── db/
│   │   ├── models.py
│   │   └── database.py
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── hooks/
│   │   └── App.js
│   └── package.json
└── README.md
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

