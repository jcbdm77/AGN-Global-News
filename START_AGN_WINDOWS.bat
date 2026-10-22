@echo off
cd /d "%~dp0infra"
if not exist .env (
 echo First launch: creating local configuration with random secrets...
 powershell -NoProfile -ExecutionPolicy Bypass -Command "$a=-join ((1..48) | ForEach-Object { 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'[(Get-Random -Maximum 62)] });$b=-join ((1..48) | ForEach-Object { 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'[(Get-Random -Maximum 62)] });Set-Content -Path '.env' -Value @('POSTGRES_PASSWORD='+$a,'ADMIN_TOKEN='+$b)"
)
echo.
echo Starting AGN web, API and newsroom dashboard...
echo Once ready, open http://localhost:8000/en
 echo Admin dashboard: http://localhost:8000/studio
 echo Editorial token: open infra\.env and copy the ADMIN_TOKEN value.
echo.
docker compose up --build
pause
