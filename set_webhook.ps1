# set_webhook.ps1
# ----------------------------
# Usage: Open PowerShell, navigate to project folder, run:
# ./set_webhook.ps1
# ----------------------------

# Load environment variables from .env
$env:TELEGRAM_BOT_TOKEN = (Get-Content .env | Select-String "TELEGRAM_BOT_TOKEN" | ForEach-Object { ($_ -split "=")[1].Trim() })
$env:RENDER_URL = "https://telegram-expense-bot-z008.onrender.com"   # Replace with your Render URL if different

# Set the webhook
$token = $env:TELEGRAM_BOT_TOKEN
$url = "$env:RENDER_URL/webhook/$token"

$response = Invoke-WebRequest -Uri "https://api.telegram.org/bot$token/setWebhook" -Method POST -Body @{url=$url}
Write-Host "Webhook set response:"
Write-Host $response.Content
