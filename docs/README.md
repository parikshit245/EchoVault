I’ll quickly confirm the current documented commands and environment files, then give you a Windows-friendly step-by-step run guide.

Run locally on Windows
1. Configure Neon database
Open the project folder:

C:\7th Semester\Distributed Systems\FA-1-Project

Edit .env and set:


Do not commit .env.

2. Install backend dependencies
Open PowerShell in the project root:


If PowerShell blocks activation, run:


Then activate again.

3. Start the backend
In the same terminal:


Backend URLs:

http://localhost:8000/
http://localhost:8000/health
http://localhost:8000/health/database
http://localhost:8000/docs
4. Start the frontend
Open a second PowerShell terminal:


Open:

http://localhost:3000

You should see the EchoVault initialization page.

Run with Docker
Make sure Docker Desktop is running, then from the project root:


Open:

Frontend: http://localhost:3000
Backend: http://localhost:8000
Stop the containers with:


Docker Compose starts only the frontend and backend. PostgreSQL is not run locally; the backend connects to Neon.

Useful checks


If /health/database returns 503, check that .env contains a valid Neon DATABASE_URL.