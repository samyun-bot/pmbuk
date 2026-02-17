# Deploy to Render

1. Initialize a git repository locally and push to GitHub (or another Git provider):

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

2. On render.com create a new **Web Service** and connect your repository.

3. Set the build and start commands (Render usually autodetects):
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`

4. Ensure any environment variables you need are set in the Render dashboard.

That's it — Render will build and run the service. Visit the service URL Render provides.
# pmbuk
