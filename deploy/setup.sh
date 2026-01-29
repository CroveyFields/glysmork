#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Starting Deployment Setup..."

# 1. Update and Install Dependencies
echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip python3-dev libpq-dev postgresql postgresql-contrib nginx curl redis-server git

# 2. Start Redis
echo "Starting Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# 3. Setup Project Paths
PROJECT_DIR="/home/ubuntu/chat"
VENV_DIR="$PROJECT_DIR/venv"

# 4. Create Virtual Env
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python Virtual Environment..."
    python3 -m venv $VENV_DIR
fi

# 5. Activate and Install Requirements
echo "Installing Python requirements..."
source $VENV_DIR/bin/activate
pip install -r $PROJECT_DIR/requirements.txt
# Gunicorn is not strictly needed if using Daphne for everything, but good practice to have available usually.
# passing for now as we use daphne in procfile/service.

# 6. Setup Database (Postgres)
echo "Configuring Database..."
# Only create if it doesn't exist (primitive check)
if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw chat; then
    sudo -u postgres psql -c "CREATE DATABASE chat;"
    sudo -u postgres psql -c "CREATE USER chatuser WITH PASSWORD 'password123';"
    sudo -u postgres psql -c "ALTER ROLE chatuser SET client_encoding TO 'utf8';"
    sudo -u postgres psql -c "ALTER ROLE chatuser SET default_transaction_isolation TO 'read committed';"
    sudo -u postgres psql -c "ALTER ROLE chatuser SET timezone TO 'UTC';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE chat TO chatuser;"
    # Grant schema privileges (for Postgres 15+)
    sudo -u postgres psql -c "ALTER DATABASE chat OWNER TO chatuser;"
else
    echo "Database 'chat' likely exists, skipping creation..."
fi

# 7. Create .env file if missing
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Creating .env file..."
    cat <<EOF > $PROJECT_DIR/.env
DEBUG=False
SECRET_KEY=$(openssl rand -base64 32)
DATABASE_URL=postgres://chatuser:password123@localhost/chat
REDIS_URL=redis://localhost:6379
ALLOWED_HOSTS=*
EOF
fi

# 8. Django Commands
echo "Running Django commands..."
python manage.py collectstatic --noinput
python manage.py migrate

# 9. Systemd Setup
echo "Configuring Systemd..."
sudo cp $PROJECT_DIR/deploy/daphne.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable daphne
sudo systemctl restart daphne

# 10. Nginx Setup
echo "Configuring Nginx..."
sudo rm /etc/nginx/sites-enabled/default || true
sudo cp $PROJECT_DIR/deploy/nginx.conf /etc/nginx/sites-available/chat
sudo ln -sf /etc/nginx/sites-available/chat /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# 11. Firewall (UFW) - Optional but recommended
# sudo ufw allow 'Nginx Full'

echo "Deployment Script Finished Successfully!"
echo "Your app should be live. If you have a domain, configuring SSL with Certbot is recommended."
