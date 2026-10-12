# Restart the Ollama tray app cleanly (also stops llama-server runners so none are orphaned).
# Usage: powershell -File scripts\restart_ollama.ps1 [-FlashAttention] [-KvCacheType q8_0]
param([switch]$FlashAttention, [string]$KvCacheType = "")

Get-Process | Where-Object { $_.ProcessName -match '^(ollama|ollama app|llama-server)$' } |
    Stop-Process -Force -Confirm:$false
Start-Sleep 3
if ($FlashAttention) { $env:OLLAMA_FLASH_ATTENTION = "1" } else { Remove-Item Env:OLLAMA_FLASH_ATTENTION -ErrorAction SilentlyContinue }
if ($KvCacheType) { $env:OLLAMA_KV_CACHE_TYPE = $KvCacheType } else { Remove-Item Env:OLLAMA_KV_CACHE_TYPE -ErrorAction SilentlyContinue }
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
for ($i = 0; $i -lt 150; $i++) {
    try { Invoke-RestMethod http://localhost:11434/api/version -TimeoutSec 10 -UseBasicParsing | Out-Null; "Ollama is up"; exit 0 }
    catch { Start-Sleep 1 }
}
"Ollama did not start within 150 s"; exit 1
