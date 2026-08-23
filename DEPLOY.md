# Deployment

The root `index.html` is ready for the current Cloudflare deployment.

The backend is intentionally separate because Cloudflare is currently deploying the repository as a Worker/static asset site. The next production step is to deploy `/backend` as an API service and set the frontend API URL to that service.

Do not put API keys into the frontend repository.
